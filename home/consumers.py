
# home/consumers.py
import json
import logging
import html
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from .utils import get_models, convert_path, handle_annotation_to_csv
from django_plotly_dash.consumers import async_send_to_pipe_channel

# Setup logger
logger = logging.getLogger('home')

class ECGConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]  # Access the user from the scope
        if not self.user.is_authenticated:
            await self.close()
        else:
            logger.info(f"\nWebSocket connect called by {self.user.username}.\n")
            # Initialize instance variables: channels extracted from xml files, current file path, reset condition 
            # for consecutive 'undo' or 'refresh' clicks, the consecutive excution count number, and past action.
            self.models_info = None
            self.current_file_path = None
            self.handle_condition = False # Update reset condition on receiving a new file path
            self.count_number = 0
            self.count_auto_label = 0
            self.count_number_empty_channel = 0
            self.past_action = None

            # Join the group that will receive messages from DjangoDash
            self.User_name = self.user.username
            self.User_id = self.user.id

            # Use this later

            # # Initialize instance variables in a dictionary
            # self.user_data = {
            #     'current_file_path': None,
            #     'handle_condition': False,
            #     'count_number': 0,
            #     'past_action': None,
            #     'count_number_empty_channel': 0
            # }

            self.group_name = f"ecg_analysis_{self.User_name}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)

            try:
                await self.accept()
                logger.info(f"\n----- WebSocket accepted for user: {self.User_name}\n")
                # Send user data upon connection
                await self.send(text_data=json.dumps({
                    'type': 'user_data',
                    'User_name': self.User_name,
                    'User_id': self.User_id,
                }))
                logger.info(f"\n----- Django sent to the client: \n\tUser_name: {self.User_name}, \n\tUser_id: {self.User_id}\n")

                # Introduce a delay to ensure the Django Dash side is fully initialized
                await asyncio.sleep(1)  # Delay for 1 second

                # Send the data to the Django Dash pipe, to initialize value to store in dcc.Store(id='store_session_user_data'...)
                Data_to_Send = {'User_id': self.User_name}
                await async_send_to_pipe_channel(
                    channel_name='User_data_channel',  # Fixed channel name for the first pipe
                    label='User_data_Label',  # Fixed label for the first pipe
                    value=Data_to_Send
                )
                logger.info(f"\n+++++ Sent Data to dpd.Pipe: {Data_to_Send} for User: {self.User_name}\n")

            except asyncio.CancelledError:
                await self.close(code=1001)  # Indicates that the server is shutting down

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"\nWebSocket disconnect called with close code {close_code} by {self.user.username}.\n")

    async def receive(self, text_data):
        logger.info(f"\nDjango Received data through WebSocket from {self.user.username}: {text_data}.\n")
        data = json.loads(text_data)
        data_type = data.get('type')

        #______________________________________________________________________________
        if data_type == 'processCSV_getMODELS':
            # Sending message to Pipe in DjangoDash ###################################
            
            # Send the User ID to Pipe
            Data_to_Send = {'User_id': self.User_name}
            await async_send_to_pipe_channel(
                        channel_name = 'User_data_channel',  # Fixed channel name for the first pipe
                        label = 'User_data_Label',  # Fixed label for the first pipe
                        value = Data_to_Send)
            logger.info(f"\n+++++ Django sent Message Channel data to dpd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}\n\tin conditional if data['type'] == 'processCSV_getMODELS'")
            
            # Store the current file path in the instance variable
            logger.info(f"\n+++++ Django received data['RelativefilePath'] : {data['RelativefilePath']}")
            self.current_file_path = convert_path(html.unescape(data['RelativefilePath']))
            logger.info(f"\n+++++ convert_path(html.unescape(data['RelativefilePath']) : {self.current_file_path}")

            Data_to_Send = self.current_file_path
            await async_send_to_pipe_channel(
                        channel_name = 'FilePath_Channel',  # Fixed channel name for the first pipe
                        label = 'FilePath_label',  # Fixed label for the first pipe
                        value = Data_to_Send)
            logger.info(f"\n+++++ Django sent 'FilePath_Channel' Channel data to dpd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}")
            response = get_models()
            if 'error' in response:
                # Log the error and send a specific error message to the client
                logger.error(f"\nFailed to retrieve existing models: {response['error']}\n")
                await self.send(text_data=json.dumps({'error': 'Failed to retrieve existing models'}))
            else:
                # Store the extracted channels in the instance variable
                self.models_info = response
                # Send the successful response back to the client
                logger.info(f"\nget_models ran successfully: \n{json.dumps(response, indent=4)}\n")
                # Extract only model names and remarks to send to the front end
                models_summary = {
                    model_name: {
                        'Remarks': details['Remarks'],
                        'ShortDescription': details['Short Description']
                    } for model_name, details in response.items()}
                logger.info(f"\nShow models_summary to send to front end: \n{json.dumps(models_summary, indent=4)}\n")
                # Send the filtered response back to the client
                await self.send(text_data=json.dumps({
                    'type': 'existing_models',
                    'models': models_summary  # Send the summarized data
                }))
            self.handle_condition = True
            logger.info(f"\nself.handle_condition is set to {self.handle_condition} in if data['type'] == 'processCSV_getMODELS'\n")

        #______________________________________________________________________________
        elif data_type == 'DashDisplayWithAutoLabel':
            path_variable = convert_path(html.unescape(data['RelativefilePath']))
            logger.info(f"\nDjango received \n-relative file path: {path_variable} \n-and selected model: {data['model']}\n")

            if self.handle_condition:
                if self.count_auto_label == 0: 
                    self.count_auto_label += 10
                else:
                    self.count_auto_label = 0

            # Send the User ID to Pipe
            Data_to_Send = {'User_id': self.User_name}
            await async_send_to_pipe_channel(
                        channel_name = 'User_data_channel',  # Fixed channel name for the first pipe
                        label = 'User_data_Label',  # Fixed label for the first pipe
                        value = Data_to_Send)
            logger.info(f"\n+++++ Django sent Message Channel data to dpd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}\n\tin conditional elif data['type'] == 'DashDisplayWithAutoLabel'")

            # Sending message to Pipe in DjangoDash 
            Data_to_Send = {'File-path': path_variable, 'SelectedModel': data['model'], 'Click_Order': self.count_auto_label}
            await async_send_to_pipe_channel(
                        channel_name = 'Receive_Django_Message_Channel',
                        label = 'Path_and_Model_label',
                        value = Data_to_Send)
            logger.info(f"\n+++++ Django sent Message Channel data to ppd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}")

            # Update reset condition on receiving a new file path
            self.handle_condition = True
            logger.info(f"\nself.handle_condition is set to {self.handle_condition} in elif data['type'] == 'DashDisplayWithAutoLabel'\n")
            
        #______________________________________________________________________________
        elif data_type == 'Refresh_Save_Undo_Delete':
            action_var = data['Action_var']
            data_var = data['Data_var']
            logger.info(f"\nDjango received \n\t-Action_var: {action_var}\n\t-Data_var: {data_var}\n")

            Data_to_Send = {'User_id': self.User_name}
            await async_send_to_pipe_channel(
                        channel_name = 'User_data_channel',  # Fixed channel name for the first pipe
                        label = 'User_data_Label',  # Fixed label for the first pipe
                        value = Data_to_Send)
            logger.info(f"\n+++++ Django sent Message Channel data to dpd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}\n\tin conditional elif data['type'] == 'Refresh_Save_Undo_Delete'")

            if action_var in ('refresh', 'undo'):
                logger.info(f"\t\t\tConditional executed:\n\t\t\t\t\t\t-Action_var: {action_var}\n")
                # Only send data if self.handle_condition is True
                if self.handle_condition:
                    if self.count_number == 0: 
                        self.count_number += 10
                    else:
                        self.count_number = 0
                    # Sending message to Pipe in DjangoDash 
                    Data_to_Send = {'Action': action_var, 'Click_Order': self.count_number}
                    await async_send_to_pipe_channel(
                                channel_name = 'This_Action_Channel',  # Fixed channel name for the second pipe
                                label = 'This_Action',  # Fixed label for the second pipe
                                value = Data_to_Send)
                    logger.info(f"\n+++++ Django sent Message Channel data to ppd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}")
                    
            elif action_var == 'delete':
                logger.info(f"\t\t\tConditional executed:\n\t\t\t\t\t\t-Action_var: {action_var}\n")
                if self.handle_condition:
                    Data_to_Send = {'Action': action_var, 'Click_Order': data_var}
                    await async_send_to_pipe_channel(
                                channel_name = 'This_Action_Channel',  # Fixed channel name for the second pipe
                                label = 'This_Action',  # Fixed label for the second pipe
                                value = Data_to_Send)
                    logger.info(f"\n+++++ Django sent Message Channel data to ppd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}")

            elif action_var in ('save', 'SaveAll'):
                logger.info(f"\t\t\tConditional executed:\n\t\t\t\t\t\t-Action_var: {action_var}\n")
                if self.current_file_path:
                    logger.info(f"\tCurrent file path: {self.current_file_path}")
                    message, status = handle_annotation_to_csv(relative_file_path=self.current_file_path, task_to_do=action_var)
                    await self.send(text_data=json.dumps({
                                                        'type': 'Save_Feedback',
                                                        'Message': message,
                                                        'Status': status
                                                    }))
            else:
                logger.info(f"\t\t\tThe received 'Action variable' is not valid. \n\t\t\taction_var = {action_var}\n")

        #______________________________________________________________________________
        elif data_type == 'labels_display_updated':
            label_status = data['updated_labels_status']
            logger.info(f"\nDjango received \n-updated_labels_status: {label_status}\n")

            # Send the User ID to Pipe
            Data_to_Send = {'User_id': self.User_name}
            await async_send_to_pipe_channel(
                        channel_name = 'User_data_channel',  # Fixed channel name for the first pipe
                        label = 'User_data_Label',  # Fixed label for the first pipe
                        value = Data_to_Send)
            logger.info(f"\n+++++ Django sent Message Channel data to dpd.Pipe: {Data_to_Send}\n\tfor self.User_name = {self.User_name}\n\tin conditional elif data['type'] == 'labels_display_updated'")

            # Send the updated_labels_status to DjangoDash
            await async_send_to_pipe_channel(
                        channel_name = 'Labels_status_Channel',
                        label = 'Labels_Display_Status',
                        value = label_status)
            logger.info(f"\n+++++ Django sent Message updated_labels_status data to dpd.Pipe: {label_status}\n\tfor self.User_name = {self.User_name}\n\tin conditional elif data['type'] == 'labels_display_updated'")

        #______________________________________________________________________________
        else:
            logger.error(f"\nUnknown message type received: {data_type}\n")
            await self.send(text_data=json.dumps({'error': 'Unknown message type'}))

    async def retrieved_data(self, event):
        # This method is called when a message of type 'retrieved_data' is sent to the group
        existing_Data = event['Existing_Data']
        logger.info(f"\n+++++ Django Received Retrieved Data: \n\t\tExisting_Data: \n{existing_Data}\n\n")

        # Send the retrieved data to the client
        await self.send(text_data=json.dumps({
            'type': 'DjangoDash_retrieved_data_message',
            'Existing_Data': existing_Data,
        }))
        logger.info(f"\n----- Django sent retrieved_data to the client: \n{existing_Data}\n")

    async def form_submission(self, event):
        # This method is called when a message of type 'form_submission' is sent to the group
        annotation = event['annotation']
        click_indices = event.get('click_indices', ['Start_index', 'End_index'])  # Returns second option as default if first is missing
        item_number = event['item_number']
        segment_color = event['Color']
        logger.info(f"\n+++++ Django Received form submission: \n-annotation: {annotation} \n-click indices: {click_indices} \n-item_number: {item_number}\n-and segment_color: {segment_color}")

        # Send the annotation as a response to the client
        await self.send(text_data=json.dumps({
            'type': 'DjangoDash_message',
            'Annotation_message': annotation,
            'Click_indices': click_indices,
            'Item_number': item_number,
            'Color': segment_color,
        }))
        logger.info(f"\n----- Django sent form submission annotation, click indices and item number to the client: \n{annotation}, \n{click_indices}, \n{item_number}\n")

    async def labels_submission(self, event):
        # This method is called when a message of type 'labels_submission' is sent to the group
        labels_data = event['list_labels_display_status']
        logger.info(f"\n+++++ Django received Labels_Pipe data: \n{labels_data}\n")

        # Send a response to the client, if needed
        await self.send(text_data=json.dumps({
            'type': 'DjangoDash_labels_status',
            'Labels_data': labels_data,
        }))
        logger.info(f"\n----- Django sent Labels_Pipe data to the client: {labels_data}\n")

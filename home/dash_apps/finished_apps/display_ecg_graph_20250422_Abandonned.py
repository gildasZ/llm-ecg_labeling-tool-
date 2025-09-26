
# home/dash_apps/finished_apps/display_ecg_graph.py
import csv
import os
import json
import logging
import dpd_components as dpd
import pandas as pd
from dash import dcc, html, Output, Input, State
from django_plotly_dash import DjangoDash
from dash.exceptions import PreventUpdate
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from home.utils import handle_annotation_to_csv, read_csv_file, plot_with_plotly

# Setup logger
logger = logging.getLogger('home')

# Initial log to see how often the whole code re-runs (should be infrequent)
logger.info(f"display_ecg_graph.py module loaded!")

# Define data_tz globally
data_tz = 'UTC'  # Default timezone

# Define default labels (will be overridden by CSV if it exists)
default_labels_list = [
    {'label': 0, 'value': 'No trend', 'Color': 'black'},
    {'label': 1, 'value': 'Moderate negative trend', 'Color': 'orange'}, # Previously 'yellow'
    {'label': 2, 'value': 'Very strong negative trend', 'Color': 'red'},
    {'label': 3, 'value': 'Moderate positive trend', 'Color': 'green'},
    {'label': 4, 'value': 'Very strong positive trend', 'Color': 'blue'},
]

def get_list_of_labels():
    file_path = "Testing_existence.csv" # Consider making this path configurable or user-specific if needed
    
    # Check if the file exists; if not, create and write default labels
    if not os.path.exists(file_path):
        try:
            with open(file_path, mode='w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=['label', 'value', 'Color'])
                writer.writeheader()
                for label in default_labels_list:
                    writer.writerow(label)
        except IOError as e:
            logger.error(f"Error creating label file '{file_path}': {e}. Using default labels directly.")
            return default_labels_list # Return defaults if file creation fails
    # Read data from the CSV file
    labels_list_read = []
    try:
        with open(file_path, mode='r', newline='') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    labels_list_read.append({
                        'label': int(row['label']),  # Convert to integer
                        'value': row['value'], 
                        'Color': row['Color']
                    })
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping invalid row in '{file_path}': {row}. Error: {e}")
                    continue # Skip malformed rows
        if not labels_list_read: # If file was empty or only had header/invalid rows
             logger.warning(f"Label file '{file_path}' is empty or invalid. Using default labels.")
             return default_labels_list
        return labels_list_read
    except FileNotFoundError: # Should be handled above, but as a fallback
        logger.error(f"Label file '{file_path}' not found during read. Using default labels.")
        return default_labels_list
    except Exception as e:
        logger.error(f"Error reading label file '{file_path}': {e}. Using default labels.")
        return default_labels_list

# Dash app initialization
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
app = DjangoDash('Display_ECG_Graph', external_stylesheets=external_stylesheets)

# ========== Layout Definition ==========
# It's generally better practice to define the layout within the app context
# or as a function, especially if it becomes complex or needs dynamic elements.
# However, for this structure, defining it directly is common.

app.layout = html.Div([
    html.H1(f"Time series data.", style={
        'textAlign': 'center', 'color': 'black', 'font-size': '24px',
        'backgroundColor': '#4fa1ee', 'margin': '0 auto', 'padding': '3px 20px',
        'width': 'max-content', 'display': 'block', 'border-radius': '10px',
        'font-weight': 'bold',
    }),
    dcc.Graph(
        id='ecg-graph', 
        style={"backgroundColor": "#e4451e", 'color': '#ffffff'},
        config={"staticPlot": False},  # Allow hover effects
    ),

    # --- Pipes for Communication (Consumer -> Dash) ---
    # Pipe to receive the initial User ID from the consumer
    dpd.Pipe(id='session_user_id',    # ID in callback
             value = {'User_id': None},
             label='User_data_Label',                 # Label used to identify relevant messages
             channel_name='User_data_channel'), # Channel whose messages are to be examined
    # Pipe to receive the file path
    dpd.Pipe(id='FilePath', value=None, label='FilePath_label', channel_name='FilePath_Channel'),
    # Pipe to receive file path and model for auto-labeling
    dpd.Pipe(id='FilePath_and_Model', value=None, label='Path_and_Model_label', channel_name='Receive_Django_Message_Channel'),
    # Pipe to receive button actions (undo, refresh, delete)
    dpd.Pipe(id='Button_Action', value=None, label='This_Action', channel_name='This_Action_Channel'),
    # Pipe to receive updates on which labels to display
    dpd.Pipe(id='Labels_Pipe', 
             value=[{**label, 'display': 1} for label in get_list_of_labels()], 
             label='Labels_Display_Status', 
             channel_name='Labels_status_Channel'),
    # Note: Removed Channels_Data pipe as it wasn't used in callbacks

    # --- Stores for Internal State ---
    # Store for user identification within this Dash instance
    dcc.Store(id='store_session_user_data', data={'User_name': None, 'Status': 'Empty'}, storage_type='memory'), 
    # Store for tracking annotation clicks
    dcc.Store(id='click-data', data={'Indices': [], 'Manual': None}, storage_type='memory'),
    # Dummy outputs used as triggers/outputs for callbacks that primarily cause side effects
    dcc.Store(id='dummy-output', data=None, storage_type='memory'),
    dcc.Store(id='dummy-output_2', data=None, storage_type='memory'),

    # --- Annotation Modal ---
    html.Div(
        id='input-modal',
        children=[
            html.P("Enter your annotation:"),
            dcc.Dropdown(
                id='annotation-input', 
                options=[{'label': item['value'], 'value': item['value']} for item in get_list_of_labels()],
                placeholder="Select an annotation..."
            ),
            html.Button('Submit', id='submit-button', n_clicks=0),
            html.Button('Cancel', id='cancel-button', n_clicks=0)
        ],
        style={'display': 'none', 'position': 'fixed', 'top': '20%', 'left': '30%', 'width': '40%', 
               'padding': '20px', 'border': '1px solid black', 'background-color': 'white', 'z-index': '1000'}
    ),
])

# ========== Callbacks ==========
#----------------------------------------------------------------------------------------------------------

# This callback is the helping piece to have user specific DjangoDash app updates by the update_graph callback and other callbacks. 
# Otherwise all the instances of the DjangoDash App for all users will be updated anythime the callback is triggered by any user.

# --- Callback to initialize the user store for this Dash instance ---
@app.callback(
    Output('store_session_user_data', 'data'),
    Input('session_user_id', 'value'),
    State('store_session_user_data', 'data'),
    prevent_initial_call=True # Only run when pipe sends value
)
def store_user_specific_info(user_id_pipe_value, stored_user_data, callback_context):    
    if not callback_context.triggered:
        raise PreventUpdate # Should not happen with prevent_initial_call=True
    # Check if store is already updated
    if stored_user_data and stored_user_data.get('Status') == 'Updated':
        logger.debug(f"User store already updated for {stored_user_data.get('User_name')}. Ignoring pipe message.")
        raise PreventUpdate
    # Validate incoming pipe data
    if not user_id_pipe_value or 'User_id' not in user_id_pipe_value:
        logger.warning("Received invalid or empty data on 'session_user_id' pipe.")
        raise PreventUpdate
    
    pipe_user_name = user_id_pipe_value['User_id']
    if not pipe_user_name:
         logger.warning("Received empty User_id in 'session_user_id' pipe.")
         raise PreventUpdate
        
    logger.info(f"Initializing user store for instance with User_name: {pipe_user_name}")
    return {'User_name': pipe_user_name, 'Status': 'Updated'}

# --- Helper function for guard condition in callbacks ---
def check_user_context(callback_context, stored_user_data, pipe_value):
    """Checks if the callback should run based on user context."""
    if not callback_context.triggered:
        logger.debug("Callback triggered without input change. Preventing update.")
        raise PreventUpdate

    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]

    # Check if the store is initialized
    if not stored_user_data or stored_user_data.get('Status') != 'Updated':
        logger.warning(f"Callback triggered by {trigger_id}, but user store not initialized. Preventing update.")
        raise PreventUpdate

    stored_user_name = stored_user_data.get('User_name')
    if not stored_user_name:
        logger.error(f"Callback triggered by {trigger_id}, but stored_user_name is missing after initialization!")
        raise PreventUpdate # Should not happen

    # For pipe inputs, check the target_user_id
    # Assumes pipe inputs are dictionaries with 'target_user_id' key
    is_pipe_trigger = trigger_id in ['FilePath', 'FilePath_and_Model', 'Button_Action', 'Labels_Pipe'] # Add other pipe IDs if necessary

    if is_pipe_trigger:
        if not isinstance(pipe_value, dict) or 'target_user_id' not in pipe_value:
            logger.warning(f"Pipe ({trigger_id}) message received by {stored_user_name} without 'target_user_id'. Value: {pipe_value}")
            raise PreventUpdate # Expect target_user_id from consumer

        target_user_id = pipe_value.get('target_user_id')
        if target_user_id != stored_user_name:
            logger.debug(f"Callback for {stored_user_name} skipped: Message target '{target_user_id}' != Instance user '{stored_user_name}' (Trigger: {trigger_id})")
            raise PreventUpdate
        else:
             # Return the actual payload if the user matches
             logger.debug(f"Callback for {stored_user_name} proceeding: Message target matches. (Trigger: {trigger_id})")
             # The actual payload is everything EXCEPT 'target_user_id'.
             # For simplicity, we might just pass the whole pipe_value and let the callback extract needed keys.
             # Or return a cleaned payload: payload = {k: v for k, v in pipe_value.items() if k != 'target_user_id'}
             return pipe_value # Return the full value for now

    # If not a pipe trigger (e.g., button click, graph click), proceed if user store is initialized
    logger.debug(f"Callback for {stored_user_name} proceeding (Trigger: {trigger_id}, not a targeted pipe).")
    return None # Indicate non-pipe trigger or pass-through

# --- Callback to send initial labels to Django once user is known ---
@app.callback(
    Output('dummy-output_2', 'data'),
    Input('store_session_user_data', 'data'), # Trigger when user data is stored
    State('Labels_Pipe', 'value'), # Get current labels state (might be initial default or from pipe)
    prevent_initial_call=True
)
def send_labels_when_user_available(stored_user_data, current_labels_state):
    # No need for check_user_context here, this reacts to the store update

    if not stored_user_data or stored_user_data.get('Status') != 'Updated':
        logger.debug("send_initial_labels: User store not updated yet.")
        raise PreventUpdate

    stored_user_name = stored_user_data.get('User_name')
    if not stored_user_name:
         logger.error("send_initial_labels: User store updated but User_name missing.")
         raise PreventUpdate
    
    # Determine labels to send (use initial from get_list_of_labels if state is None)
    labels_to_send = current_labels_state
    if labels_to_send is None:
        # If the Labels_Pipe hasn't received anything yet, generate the initial state
        labels_to_send = [{**label, 'display': 1} for label in get_list_of_labels()]
        logger.info(f"send_initial_labels: Using initial labels for {stored_user_name} as Labels_Pipe state is None.")

    logger.info(f"User '{stored_user_name}' available. Sending current labels state to Django.")
    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            f"ecg_analysis_{stored_user_name}",
            {
                "type": "labels_submission",
                "list_labels_display_status": labels_to_send,
            }
        )
        logger.info(f"Labels state sent to Django for user '{stored_user_name}': \n{json.dumps(labels_to_send, indent=2)}\n")
        return {'status': 'initial_labels_sent'} # Update dummy output
    except Exception as e:
        logger.error(f"Error sending initial labels for user '{stored_user_name}': {e}")
        raise PreventUpdate

# --- Callback to handle annotation submission ---
@app.callback(
    Output('dummy-output', 'data'),
    Input('submit-button', 'n_clicks'),
    State('annotation-input', 'value'),
    State('click-data', 'data'),
    State('FilePath', 'value'), # Get file path from the *Pipe's current value*
    State('store_session_user_data', 'data'), # Get user context
    prevent_initial_call=True
)
def handle_form_submission(n_clicks, input_value, clicks, file_path_pipe_value, stored_user_data, callback_context):
    # Use stored_user_data directly, no need for check_user_context as trigger isn't a targeted pipe
    if not stored_user_data or stored_user_data.get('Status') != 'Updated':
        logger.warning("handle_form_submission: User store not initialized.")
        raise PreventUpdate
    stored_user_name = stored_user_data.get('User_name')

    logger.info(f"\n\n******** handle_form_submission callback triggered for user: {stored_user_name}.\n")

    button_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    logger.info(f"Triggered by: {button_id}\n") # Should be 'submit-button'

    # Extract the actual file path from the pipe's value (which might be None or the dict from consumer)
    current_file_path = None
    if isinstance(file_path_pipe_value, dict) and file_path_pipe_value.get('target_user_id') == stored_user_name:
        current_file_path = file_path_pipe_value.get('file_path')

    if not current_file_path:
        logger.error(f"handle_form_submission ({stored_user_name}): Cannot submit, FilePath is not set or invalid.")
        # Maybe provide user feedback here?
        raise PreventUpdate

    if not input_value:
         logger.warning(f"handle_form_submission ({stored_user_name}): No annotation selected/entered.")
         # Optionally provide feedback
         raise PreventUpdate

    if not clicks or not clicks.get('Indices') or len(clicks['Indices']) != 2:
        logger.warning(f"handle_form_submission ({stored_user_name}): Invalid click data for submission.")
        raise PreventUpdate

    # Proceed with submission logic
    logger.info(f"User {stored_user_name} submitted annotation: {input_value}\n")
    sanitized_input = str(input_value) # Ensure it's a string
    click_indices = clicks['Indices']
    logger.info(f"Click indices: {click_indices}\n")
    logger.info(f"\tUsing relative file path: '{current_file_path}'\n")

    segment_color = select_segment_color(sanitized_input)
    annotation_data = {
        'Start Index': click_indices[0],
        'End Index': click_indices[1],
        'Label': sanitized_input,
        'Color': segment_color,
    }

    # Add annotation to CSV
    try:
        handle_annotation_to_csv(relative_file_path=current_file_path, annotation_data=annotation_data, task_to_do='add')
        logger.info(f"Annotation added to CSV for {current_file_path}.")

        # Retrieve updated data to get item number
        existing_values = handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do='retrieve')
        logger.debug(f"Retrieved existing values after add: \n{existing_values}\n")

        if existing_values:
            last_item = existing_values[-1]
            # Basic check if the last item seems to be the one just added
            if (last_item.get('Start Index') == annotation_data['Start Index'] and
                    last_item.get('End Index') == annotation_data['End Index'] and
                    last_item.get('Label') == annotation_data['Label']):
                last_item_number = last_item.get('Item Number', 'N/A')
                logger.info(f"Annotation seems successfully added. Last item number: {last_item_number}")

                # Send confirmation back to consumer
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"ecg_analysis_{stored_user_name}",
                    {
                        "type": "form_submission",
                        "annotation": sanitized_input,
                        "click_indices": click_indices,
                        "item_number": last_item_number,
                        'Color': segment_color
                    }
                )
                logger.info(f"Sent form submission details to consumer for user {stored_user_name}.")
                # Return dummy data to potentially trigger graph update via dummy-output Input
                return {'submitted_annotation': annotation_data, 'timestamp': datetime.datetime.now().isoformat()}
            else:
                logger.warning("Last item in CSV doesn't match submitted data. Group send aborted.")
                raise PreventUpdate # Or handle differently
        else:
            logger.warning("CSV is empty after attempting to add annotation. Group send aborted.")
            raise PreventUpdate # Or handle differently

    except Exception as e:
        logger.error(f"Error during annotation submission or CSV handling for {stored_user_name}: {e}", exc_info=True)
        # Provide user feedback?
        raise PreventUpdate

# --- Callback to clear annotation input ---
@app.callback(
    Output('annotation-input', 'value'),
    Input('submit-button', 'n_clicks'),
    Input('cancel-button', 'n_clicks'),
    Input('click-data', 'data'), # Trigger on click changes too
    State('store_session_user_data', 'data'), # Check user context
    prevent_initial_call=True
)
def clear_input(submit_clicks, cancel_clicks, click_data_state, stored_user_data, callback_context):
     # No need for check_user_context, just ensure the user store is initialized
    if not stored_user_data or stored_user_data.get('Status') != 'Updated':
        raise PreventUpdate
    stored_user_name = stored_user_data.get('User_name')

    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    logger.debug(f"clear_input triggered for user {stored_user_name} by {trigger_id}.")

    # Clear on submit, cancel, or if click data is reset (e.g., only 1 click)
    if trigger_id in ('submit-button', 'cancel-button'):
        logger.info(f"Clearing annotation input for {stored_user_name} due to {trigger_id}.")
        return ""
    elif trigger_id == 'click-data':
        if click_data_state and len(click_data_state.get('Indices', [])) != 2:
             logger.info(f"Clearing annotation input for {stored_user_name} due to click-data reset.")
             return ""
        else:
             raise PreventUpdate # Don't clear if 2 clicks are present
    else:
        raise PreventUpdate
    
# --- Callback to manage annotation modal visibility ---
@app.callback(
    Output('input-modal', 'style'),
    Input('click-data', 'data'),
    Input('submit-button', 'n_clicks'),
    Input('cancel-button', 'n_clicks'),
    State('input-modal', 'style'),
    State('store_session_user_data', 'data'), # Check user context
    prevent_initial_call=True
)
def toggle_modal(clicks, submit_n_clicks, cancel_n_clicks, current_style, stored_user_data, callback_context):
    # No need for check_user_context, just ensure the user store is initialized
    if not stored_user_data or stored_user_data.get('Status') != 'Updated':
        raise PreventUpdate
    stored_user_name = stored_user_data.get('User_name')

    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    logger.debug(f"toggle_modal triggered for user {stored_user_name} by {trigger_id}")

    new_style = current_style.copy() # Important: Modify a copy

    if trigger_id == 'click-data':
        # Show modal only if exactly 2 clicks and it was a manual click sequence
        if clicks and clicks.get('Manual') and len(clicks.get('Indices', [])) == 2:
            logger.info(f"Showing annotation modal for {stored_user_name}.")
            new_style['display'] = 'block'
        else:
            # Hide modal if clicks reset, not manual, or not 2 clicks
            if new_style['display'] != 'none': # Avoid unnecessary updates
                 logger.debug(f"Hiding annotation modal for {stored_user_name} due to click-data change.")
                 new_style['display'] = 'none'
            else:
                 raise PreventUpdate

    elif trigger_id in ('submit-button', 'cancel-button'):
        if new_style['display'] != 'none': # Avoid unnecessary updates
            logger.info(f"Hiding annotation modal for {stored_user_name} due to {trigger_id}.")
            new_style['display'] = 'none'
        else:
            raise PreventUpdate

    return new_style

# --- Callback to update click data store ---
@app.callback(
    Output('click-data', 'data'),
    Input('ecg-graph', 'clickData'),
    Input('FilePath', 'value'),          # Pipe Input
    Input('FilePath_and_Model', 'value'),# Pipe Input
    Input('Button_Action', 'value'),     # Pipe Input
    Input('cancel-button', 'n_clicks'),
    State('click-data', 'data'),
    State('store_session_user_data', 'data'), # Get user context
    prevent_initial_call=True
)
def store_click_data(
    graph_click_data,        # Input 1
    file_path_pipe_value,    # Input 2 (Pipe)
    path_model_pipe_value, # Input 3 (Pipe)
    button_action_pipe_value,# Input 4 (Pipe)
    cancel_clicks,           # Input 5
    current_click_state,     # State 1
    stored_user_data,        # State 2
    callback_context
):
    # --- User Context Check ---
    # Check which input triggered and apply user check if it's a pipe
    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    pipe_value = None
    if trigger_id == 'FilePath': pipe_value = file_path_pipe_value
    elif trigger_id == 'FilePath_and_Model': pipe_value = path_model_pipe_value
    elif trigger_id == 'Button_Action': pipe_value = button_action_pipe_value

    try:
        # check_user_context will raise PreventUpdate if user doesn't match pipe target
        # or if user store isn't initialized. It returns the pipe_value if valid.
        validated_pipe_value = check_user_context(callback_context, stored_user_data, pipe_value)
    except PreventUpdate:
        raise # Re-raise PreventUpdate

    # If we reach here, the user context is valid for the trigger.
    stored_user_name = stored_user_data.get('User_name')
    logger.debug(f"store_click_data triggered for user {stored_user_name} by {trigger_id}")

    # --- Logic based on Trigger ---
    reset_dic = {'Indices': [], 'Manual': False}

    if trigger_id == 'FilePath':
        # Extract payload from validated_pipe_value (which is the full dict here)
        file_path_payload = validated_pipe_value.get('file_path') if validated_pipe_value else None
        logger.info(f"store_click_data ({stored_user_name}): Received new FilePath = {file_path_payload}. Resetting clicks.")
        return reset_dic

    elif trigger_id == 'FilePath_and_Model':
        # Extract payload
        file_path = validated_pipe_value.get('File-path') if validated_pipe_value else None
        selected_model = validated_pipe_value.get('SelectedModel') if validated_pipe_value else None
        logger.info(f"store_click_data ({stored_user_name}): Received FilePath+Model ({file_path}, {selected_model}). Resetting clicks.")
        return reset_dic

    elif trigger_id == 'Button_Action':
        # Extract payload
        action_to_take = validated_pipe_value.get('Action') if validated_pipe_value else None
        data_for_action = validated_pipe_value.get('Click_Order') if validated_pipe_value else None # Contains count or data to delete

        # Need the current file path to perform CSV actions
        # Get it from the *state* of the FilePath pipe, as the trigger wasn't FilePath
        current_file_path = None
        if isinstance(file_path_pipe_value, dict) and file_path_pipe_value.get('target_user_id') == stored_user_name:
             current_file_path = file_path_pipe_value.get('file_path')

        if not current_file_path:
            logger.error(f"store_click_data ({stored_user_name}): Button action '{action_to_take}' received, but FilePath is not set.")
            raise PreventUpdate

        logger.info(f"store_click_data ({stored_user_name}): Processing button action '{action_to_take}' for file {current_file_path}.")
        try:
            if action_to_take == 'delete':
                logger.info(f"Data to delete: {data_for_action}")
                handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do=action_to_take, delete_data=data_for_action)
            elif action_to_take in ('refresh', 'undo'):
                handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do=action_to_take)
            else:
                 logger.warning(f"store_click_data ({stored_user_name}): Unknown button action '{action_to_take}'.")
                 raise PreventUpdate

            # After action, reset click data (no specific indices needed after undo/refresh/delete)
            logger.info(f"store_click_data ({stored_user_name}): Resetting clicks after action '{action_to_take}'.")
            return reset_dic

        except Exception as e:
             logger.error(f"Error handling button action '{action_to_take}' in store_click_data for {stored_user_name}: {e}", exc_info=True)
             raise PreventUpdate

    elif trigger_id == 'cancel-button':
        logger.info(f"store_click_data ({stored_user_name}): Cancel button clicked. Resetting clicks.")
        return reset_dic

    elif trigger_id == 'ecg-graph':
        if graph_click_data:
            new_click_state = current_click_state.copy()
            new_click_state['Manual'] = True
            x_click = graph_click_data['points'][0]['x']
            logger.debug(f"Graph clicked at x={x_click} by user {stored_user_name}")

            if len(new_click_state['Indices']) >= 2:
                logger.debug("Resetting click indices.")
                new_click_state['Indices'] = []

            new_click_state['Indices'].append(x_click)

            if len(new_click_state['Indices']) == 2:
                try:
                    # Ensure data_tz is valid before using it
                    global data_tz
                    if not data_tz: data_tz = 'UTC' # Fallback
                    logger.debug(f"Using timezone '{data_tz}' for click conversion.")
                    # Convert to Timestamps, localize, format, then sort
                    ts_indices = [pd.Timestamp(i).tz_localize(data_tz).isoformat() for i in new_click_state['Indices']]
                    ts_indices.sort()
                    new_click_state['Indices'] = ts_indices
                    logger.info(f"store_click_data ({stored_user_name}): Stored 2 sorted clicks: {new_click_state['Indices']}")
                except Exception as e:
                     logger.error(f"Error converting/sorting click indices for {stored_user_name}: {e}", exc_info=True)
                     # Reset indices on error to prevent inconsistent state
                     new_click_state['Indices'] = []
                     new_click_state['Manual'] = False


            return new_click_state
        else:
            # No click data in the event
            raise PreventUpdate

    # If none of the above triggers caused an update
    logger.debug(f"store_click_data ({stored_user_name}): No relevant trigger or condition met. Preventing update.")
    raise PreventUpdate

# --- Callback to update the main graph ---
@app.callback(
    Output('ecg-graph', 'figure'),
    # --- Inputs ---
    # Pipes (will be checked for user match)
    Input('FilePath', 'value'),
    Input('FilePath_and_Model', 'value'),
    Input('Labels_Pipe', 'value'),
    # Internal state changes & actions
    Input('click-data', 'data'),
    Input('cancel-button', 'n_clicks'),
    Input('dummy-output', 'data'), # Trigger after successful form submission
    # --- States ---
    State('store_session_user_data', 'data'), # User context **MUST BE FIRST STATE**
    State('Button_Action', 'value'), # Need last button action state
    # prevent_initial_call=False # Allow initial call for empty graph
)
def update_graph(
    # --- Input values ---
    file_path_pipe_value,    # Pipe
    path_model_pipe_value, # Pipe
    labels_pipe_value,     # Pipe
    click_data_state,        # Store
    cancel_n_clicks,         # Button
    dummy_output_data,       # Store (after submit)
    # --- State values ---
    stored_user_data,        # Store (User context) **FIRST STATE**
    button_action_pipe_value,# Pipe state
    callback_context
):
    global data_tz # Make sure we use/update the global timezone

    # --- Initial Call Handling ---
    if not callback_context.triggered or (callback_context.triggered[0]['prop_id'].split('.')[0] == 'dummy-output' and dummy_output_data is None):
        # Check if user store is already initialized on initial load (might happen quickly)
        stored_user_name_init = stored_user_data.get('User_name') if stored_user_data else "Unknown"
        logger.info(f"update_graph: Initializing graph for user: {stored_user_name_init}. No data loaded yet.")
        fig = plot_with_plotly(pd.DataFrame(), "Initializing - Select a file", 'grey', [])
        return fig

    # --- User Context Check ---
    trigger_id = callback_context.triggered[0]['prop_id'].split('.')[0]
    pipe_value = None
    if trigger_id == 'FilePath': pipe_value = file_path_pipe_value
    elif trigger_id == 'FilePath_and_Model': pipe_value = path_model_pipe_value
    elif trigger_id == 'Labels_Pipe': pipe_value = labels_pipe_value
    # Note: Button_Action is only used as State here, not checked as trigger pipe

    try:
        # check_user_context will raise PreventUpdate if user doesn't match pipe target
        # or if user store isn't initialized. It returns the pipe_value if valid pipe trigger.
        validated_pipe_value = check_user_context(callback_context, stored_user_data, pipe_value)
    except PreventUpdate:
        raise # Re-raise PreventUpdate

    # If we reach here, the user context is valid for the trigger.
    stored_user_name = stored_user_data.get('User_name')
    logger.info(f"\n\n--- update_graph triggered for user: {stored_user_name} by: {trigger_id} ---")
    logger.debug(f"Current click-data: {click_data_state}")
    logger.debug(f"Current FilePath pipe value: {file_path_pipe_value}")
    logger.debug(f"Current Labels pipe value: {labels_pipe_value}")

    # --- Prepare variables ---
    panda_data_retrieved = pd.DataFrame()
    plot_title = f"No Data Available."
    Title_Color = 'orange'
    existing_values = []
    click_indices_for_plot = None # For highlighting clicks

    # Determine the current file path (needed by most triggers)
    # Use the value from the FilePath pipe's *state* if FilePath wasn't the trigger
    current_file_path = None
    if trigger_id == 'FilePath' and validated_pipe_value:
        current_file_path = validated_pipe_value.get('file_path')
    elif isinstance(file_path_pipe_value, dict) and file_path_pipe_value.get('target_user_id') == stored_user_name:
         # If FilePath wasn't trigger, use its last valid value for this user
         current_file_path = file_path_pipe_value.get('file_path')

    # Determine labels to use for plotting
    current_labels_for_plot = []
    if trigger_id == 'Labels_Pipe' and validated_pipe_value:
        current_labels_for_plot = validated_pipe_value.get('labels', [])
    elif isinstance(labels_pipe_value, dict) and labels_pipe_value.get('target_user_id') == stored_user_name:
        # If Labels_Pipe wasn't trigger, use its last valid value
        current_labels_for_plot = labels_pipe_value.get('labels', [])
    elif current_labels_for_plot is None or not current_labels_for_plot: # Fallback if pipe never received data
        current_labels_for_plot = [{**label, 'display': 1} for label in get_list_of_labels()]


    # --- Logic based on Trigger ---

    if trigger_id == 'FilePath':
        if current_file_path:
            logger.info(f"update_graph ({stored_user_name}): Loading data from new file: {current_file_path}")
            try:
                panda_data_retrieved, data_tz_read = read_csv_file(current_file_path, 3)
                data_tz = data_tz_read # Update global timezone
                existing_values = handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do='retrieve')
                plot_title = f"Loaded: {os.path.basename(current_file_path)}"
                Title_Color = 'green'

                # Send retrieved data back to consumer
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"ecg_analysis_{stored_user_name}",
                    {"type": "retrieved_data", "Existing_Data": existing_values}
                )
            except Exception as e:
                logger.error(f"Error loading file or annotations for {current_file_path}: {e}", exc_info=True)
                plot_title = f"Error loading: {os.path.basename(current_file_path)}"
                Title_Color = 'red'
        else:
             logger.warning(f"update_graph ({stored_user_name}): FilePath trigger but path is invalid.")
             # Keep empty dataframe

    elif trigger_id == 'FilePath_and_Model':
        file_path = validated_pipe_value.get('File-path') if validated_pipe_value else None
        selected_model = validated_pipe_value.get('SelectedModel') if validated_pipe_value else None
        logger.info(f"update_graph ({stored_user_name}): Auto-labeling request for {file_path} with model {selected_model}")
        if file_path and selected_model:
             # Update current_file_path since this implies a file load/change
             current_file_path = file_path
             try:
                 labels_list_for_auto = get_list_of_labels() # Get current definitions
                 existing_values = handle_annotation_to_csv(
                     relative_file_path=current_file_path,
                     selected_model=selected_model,
                     task_to_do='Auto_Label',
                     labels_list=labels_list_for_auto
                 )
                 panda_data_retrieved, data_tz_read = read_csv_file(current_file_path, 3)
                 data_tz = data_tz_read # Update global timezone
                 plot_title = f"Auto-Labeled: {os.path.basename(current_file_path)}"
                 Title_Color = 'blue'

                 # Send retrieved data back to consumer
                 channel_layer = get_channel_layer()
                 async_to_sync(channel_layer.group_send)(
                     f"ecg_analysis_{stored_user_name}",
                     {"type": "retrieved_data", "Existing_Data": existing_values}
                 )
             except Exception as e:
                 logger.error(f"Error during auto-labeling or loading for {current_file_path}: {e}", exc_info=True)
                 plot_title = f"Error auto-labeling: {os.path.basename(current_file_path)}"
                 Title_Color = 'red'
                 existing_values = [] # Clear potentially partial results
                 panda_data_retrieved = pd.DataFrame() # Clear data
        else:
             logger.warning(f"update_graph ({stored_user_name}): FilePath_and_Model trigger but path or model is invalid.")
             # Keep empty dataframe

    elif trigger_id == 'click-data':
        if current_file_path:
            try:
                logger.debug(f"update_graph ({stored_user_name}): Click event detected. Reloading data for {current_file_path}")
                panda_data_retrieved, data_tz_read = read_csv_file(current_file_path, 3)
                data_tz = data_tz_read # Update global timezone
                existing_values = handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do='retrieve')
                plot_title = f"Viewing: {os.path.basename(current_file_path)}"
                Title_Color = 'black'
                # Highlight the clicks if exactly 2 are present
                if click_data_state and len(click_data_state.get('Indices', [])) == 2:
                    click_indices_for_plot = click_data_state['Indices']
                    plot_title += " (Select Annotation)"
                    Title_Color = 'purple'
            except Exception as e:
                logger.error(f"Error reloading file/annotations on click for {current_file_path}: {e}", exc_info=True)
                plot_title = f"Error reloading: {os.path.basename(current_file_path)}"
                Title_Color = 'red'
        else:
             logger.warning(f"update_graph ({stored_user_name}): Click event, but no current file path set.")
             # Keep empty dataframe, maybe prevent update? raise PreventUpdate

    elif trigger_id == 'dummy-output': # Indicates successful annotation submission
        if current_file_path:
            try:
                logger.info(f"update_graph ({stored_user_name}): Annotation submitted. Refreshing graph for {current_file_path}")
                panda_data_retrieved, data_tz_read = read_csv_file(current_file_path, 3)
                data_tz = data_tz_read # Update global timezone
                existing_values = handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do='retrieve')
                plot_title = f"Refreshed: {os.path.basename(current_file_path)}"
                Title_Color = 'green'
                # Send updated data back to consumer
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                     f"ecg_analysis_{stored_user_name}",
                     {"type": "retrieved_data", "Existing_Data": existing_values}
                )
            except Exception as e:
                logger.error(f"Error refreshing graph after submit for {current_file_path}: {e}", exc_info=True)
                plot_title = f"Error refreshing: {os.path.basename(current_file_path)}"
                Title_Color = 'red'
        else:
             logger.warning(f"update_graph ({stored_user_name}): Dummy output trigger, but no current file path set.")
             raise PreventUpdate

    elif trigger_id in ('cancel-button', 'Labels_Pipe'): # Also includes button actions like undo/refresh/delete handled by store_click_data resetting clicks
        if current_file_path:
            try:
                action_label = "Refreshed"
                if trigger_id == 'Labels_Pipe': action_label = "Label visibility changed"
                elif trigger_id == 'cancel-button': action_label = "Annotation cancelled"

                logger.info(f"update_graph ({stored_user_name}): {action_label}. Redrawing graph for {current_file_path}")
                panda_data_retrieved, data_tz_read = read_csv_file(current_file_path, 3)
                data_tz = data_tz_read # Update global timezone
                existing_values = handle_annotation_to_csv(relative_file_path=current_file_path, task_to_do='retrieve')
                plot_title = f"{action_label}: {os.path.basename(current_file_path)}"
                Title_Color = 'blue' # Or green?

                # Send updated data if cancel or button action (label pipe doesn't change data)
                if trigger_id != 'Labels_Pipe':
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                         f"ecg_analysis_{stored_user_name}",
                         {"type": "retrieved_data", "Existing_Data": existing_values}
                    )
            except Exception as e:
                 logger.error(f"Error redrawing graph for {current_file_path} after {trigger_id}: {e}", exc_info=True)
                 plot_title = f"Error redrawing: {os.path.basename(current_file_path)}"
                 Title_Color = 'red'
        else:
             logger.warning(f"update_graph ({stored_user_name}): {trigger_id} trigger, but no current file path set.")
             # If labels pipe triggered without a file, just show empty graph with title
             if trigger_id == 'Labels_Pipe':
                 plot_title = "Label visibility changed (No file loaded)"
                 Title_Color = 'grey'
             else:
                 raise PreventUpdate

    # --- Final Plot Generation ---
    if panda_data_retrieved.empty and not current_file_path:
        plot_title = 'Select a file to begin'
        Title_Color = 'grey'
    elif panda_data_retrieved.empty and current_file_path:
        plot_title = f'Error or no data in: {os.path.basename(current_file_path)}'
        Title_Color = 'red'

    logger.debug(f"update_graph ({stored_user_name}): Calling plot_with_plotly with title '{plot_title}'")
    fig = plot_with_plotly(
        data=panda_data_retrieved,
        title=plot_title,
        Title_Color=Title_Color,
        labels_pipe_value=current_labels_for_plot, # Pass the labels with display status
        existing_values=existing_values,
        click_data=click_indices_for_plot, # Pass click indices for potential highlighting
        save_path=None,
        show_plot=False
    )
    # logger.debug(f"Global data_tz after update_graph ({stored_user_name}): {data_tz}")
    return fig

#----------------------------------------------------------------------------------------------------------
# --- Utility function to select segment color ---
def select_segment_color(sanitized_input: str = ''):
    """
    Retrieve the color associated with the given label from the labels list.
    
    Parameters:
    - sanitized_input (str): The selected label for which the color is to be fetched.

    Returns:
    - str: The color associated with the label, or a default color if not found.
    """
    # Default color
    # default_color = "#4fa1ee"
    default_color = "#9467bd" # purple

    # Fetch the labels list dynamically
    labels = get_list_of_labels()
    
    # Iterate through the labels to find the matching value
    for label in labels:
        if label['value'] == sanitized_input:
            return label['Color']  # Return the color for the matching label
    logger.warning(f"Color not found for label value '{sanitized_input}'. Using default: {default_color}")
    return default_color

    # # List of options
    # options = get_list_of_labels()
    # options = [item['value'] for item in options]
    # logger.info(f"\nList of Options was extracted: \n{options}\n")
    # # List of colors
    # colors = [
    #     "#ff7f0e",  # orange
    #     "#d62728",  # red
    #     "#9467bd",  # purple
    #     "#8c564b",  # brown
    #     "#e377c2",  # pink
    #     "#7f7f7f",  # gray
    #     "#bcbd22",  # yellow-green
    #     "#17becf",  # cyan
    #     "#1a55FF",  # deep blue
    #     "#db7100",  # dark orange
    #     "#ffbb78",  # light orange
    #     "#ff9896",  # light red
    #     "#c5b0d5",  # light purple
    #     "#c49c94",  # light brown
    #     "#f7b6d2",  # light pink
    #     "#c7c7c7",  # light gray
    #     "#dbdb8d",  # light yellow-green
    #     "#9edae5",  # light cyan
    #     "#aec7e8"   # light blue
    # ]

    # # Ensure the list of colors is at least as long as the list of options
    # assert len(colors) >= len(options), "Not enough colors provided for the options"
    # try:
    #     # Get the index of the selected option 
    #     index = options.index(sanitized_input)
    #     # Return the corresponding color
    #     return colors[index]
    # except ValueError:
    #     # If the input is not in the options list, fall back to the default color
    #     return default_color

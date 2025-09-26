
# home/utils.py
from lxml import etree
import html
import re
import os
import csv
import time
import json
import logging
import shutil
import traceback
import mimetypes
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import tkinter as tk
import plotly.graph_objs as go
from tkinter import messagebox
from IPython.display import display
from pathlib import Path
from scipy.ndimage import gaussian_filter1d
from typing import Optional, Dict, Union
from django.conf import settings  # Import Django settings

# Setup logger
logger = logging.getLogger('home')

def handle_annotation_to_csv(relative_file_path=None, selected_model=None, annotation_data=None, task_to_do='', delete_data=None, labels_list=[]):
    """
    Handles various operations on annotation CSV files, including adding, retrieving, saving, 
    and managing annotations, as well as auto-labeling with a selected model.

    Parameters:
    - relative_file_path (str): Relative file path of the CSV file.
    - selected_model (str): The selected model used for auto-labeling annotations (optional, required for 'Auto_Label' task).
    - annotation_data (dict): Data to be added to the CSV file. Expected keys:
        - 'Start Index' (int): Start index of the annotation.
        - 'End Index' (int): End index of the annotation.
        - 'Label' (str): Annotation label or description.
        - 'Color' (str): Color associated with the annotation.
    - task_to_do (str): The task to perform. Supported values:
        - 'add': Add data to the working CSV file.
        - 'delete': Delete specific rows from the working CSV file.
        - 'retrieve': Retrieve existing annotations from the working CSV file.
        - 'save': Save the working CSV file to the saving directory.
        - 'SaveAll': Save all working CSV files in their respective directories.
        - 'refresh': Reset the working CSV file to its initial state.
        - 'undo': Undo the last annotation added to the working CSV file.
        - 'Auto_Label': Perform auto-labeling using the selected model and update the CSV file.
    - delete_data (list): List of dictionaries specifying rows to delete. Each dictionary must contain:
        - 'Item Number' (int): Unique identifier for the annotation.
        - 'Start Index' (int): Start index of the annotation.
        - 'End Index' (int): End index of the annotation.
        - 'Label' (str): Annotation label.
        - 'Color' (str): Color associated with the annotation.
    - labels_list (list[dict]): A list of dictionaries representing label definitions. Each dictionary should include:
        - 'label' (int): Numeric identifier for the label.
        - 'value' (str): Description or value of the label.
        - 'Color' (str): Color associated with the label.

    Returns:
    - For 'retrieve': List of dictionaries containing existing annotation values.
    - For 'save' and 'SaveAll': Tuple (str, bool) with a status message and success flag.
    - For 'Auto_Label': List of dictionaries with auto-labeled annotations.
    - For invalid or unspecified tasks: Empty list.
    """

    working_csv_file_path, saving_csv_file_path, annotations_dir = creating_file_paths(relative_file_path)

    # selected_model, handle this case

    if task_to_do == 'add':
        logger.info(f"Adding data to a working CSV file...\n")
        add_annotation_to_csv(working_csv_file_path, annotation_data)
    elif task_to_do == 'delete':
        logger.info(f"Deleting data from a working CSV file...\n")
        delete_annotation_from_csv(working_csv_file_path, delete_data)
    elif task_to_do == 'retrieve':
        logger.info(f"Retrieving existing annotations from working CSV file...\n")
        existing_values = retrieve_existing_annotations(working_csv_file_path)
        return existing_values
    elif task_to_do == 'save':
        logger.info(f"Saving the working CSV file...\n")
        message, status = save_annotations_to_csv(working_csv_file_path, saving_csv_file_path)
        return message, status
    elif task_to_do == 'SaveAll':
        logger.info(f"Saving All the working CSV files...\n")
        message, status = save_all_annotations_to_csv(annotations_dir)
        return message, status
    elif task_to_do == 'undo':
        logger.info(f"Undoing the last annotation in the working CSV file...\n")
        undo_last_annotation(working_csv_file_path)
    elif task_to_do == 'refresh':
        logger.info(f"Resetting the working CSV file...\n")
        refresh_working_file(working_csv_file_path)
    elif task_to_do == 'Auto_Label':
        logger.info(f"\nRunning auto labeling with the selected model: {selected_model}...")
        run_auto_labeling_of_annotations(relative_file_path=relative_file_path, 
                                         working_csv_file_path=working_csv_file_path, 
                                         selected_model=selected_model,
                                         labels_list=labels_list)
        existing_values = retrieve_existing_annotations(working_csv_file_path)
        logger.info(f"Auto labeling complete with the selected model: {selected_model}!\n")
        return existing_values
    else:
        message = f"Specify a valid task_to_do.\n"
        logger.info(message)
        return []

def creating_file_paths(relative_file_path: str) -> tuple[Path, Path, Path]:
    """
        Creates file paths for working/saving CSV annotations based on a data file's
        path relative to 'MEDIA_ROOT/Raw_Time_Series_Data/'. Annotations are stored
        separately under 'MEDIA_ROOT/Annotations_Output/'. Ensures necessary
        directories exist.

        Parameters:
        - relative_file_path (str): Path of the CSV data file relative to the
                                    'Raw_Time_Series_Data' directory within MEDIA_ROOT.
                                    Example: 'Raw_Time_Series_DataSubFolder/my_data.csv'

        Returns:
        - tuple[Path, Path, Path]: A tuple containing:
            - Path object for the working annotation CSV file.
            - Path object for the saving annotation CSV file.
            - Path object for the specific annotations directory for this file structure
            (e.g., MEDIA_ROOT/Annotations_Output/SubFolder).
        """
    try:
        # Base path from settings
        file_base_path = Path(settings.MEDIA_ROOT)
        # Convert the relative file path to a Path object
        relative_file_path = Path(relative_file_path)
        # Get the top parent directory from the relative file path
        top_parent_dir = relative_file_path.parts[0]
        # Create the new annotations directory name
        annotations_dir_name = f"{top_parent_dir}_CSV_Annotations"
        # Construct the full annotations directory path
        annotations_dir = file_base_path / annotations_dir_name
        # Ensure the directory exists
        annotations_dir.mkdir(parents=True, exist_ok=True)
        # Derive relative path and the subdirectory of the csv file excluding top_parent_dir from the subdirectory
        subdirectory = relative_file_path.relative_to(top_parent_dir).parent

        # Ensure the file extension is '.csv'
        csv_file_name = relative_file_path.with_suffix('.csv').name

        # Create 'Working_Folder' within the subdirectory
        working_csv_file_path = annotations_dir / 'Working_Folder' / subdirectory / csv_file_name
        working_csv_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create 'Saving_Folder' within the subdirectory
        saving_csv_file_path =  annotations_dir / 'Saving_Folder' / subdirectory / csv_file_name
        saving_csv_file_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"\n\nannotations_dir : {annotations_dir}")
        logger.info(f"subdirectory (excluding top_parent_dir): {subdirectory}")
        logger.info(f"working_csv_file_path = {working_csv_file_path}")
        logger.info(f"saving_csv_file_path = {saving_csv_file_path}\n\n")

        return working_csv_file_path, saving_csv_file_path, annotations_dir
    except Exception:
        logger.error(f"Error in handle_annotation_to_csv / creating_file_paths: \n\t{traceback.format_exc()}\n")

def add_annotation_to_csv(working_csv_file_path: Path, annotation_data: list[dict] | dict = None):
    """
    Adds one or multiple annotation rows to a CSV file, creating the file and necessary directories if they don't exist.

    Parameters:
    - working_csv_file_path (Path): Full file path of the working CSV file..
    - annotation_data (list[dict] | dict): A list of dictionaries or a single dictionary containing annotation details. 
      Each dictionary is expected to have the keys:
        - 'Start Index': (str/int) The starting index of the annotation.
        - 'End Index': (str/int) The ending index of the annotation.
        - 'Label': (str) The label or description for the annotation.
        - 'Color': (str) The color to be associated with the annotation (default is '#d604a2' if not provided).

    Description:
    - Creates the specified CSV file with appropriate headers if it does not exist.
    - Reads the existing file and either updates the first empty row or appends new rows for each annotation in the list or single dictionary.
    - Ensures each annotation gets a unique item number for tracking.

    Returns:
    - None
    """
    try:
        # Validate inputs
        if annotation_data is None:
            raise ValueError("annotation_data cannot be None. Please provide a dictionary or a list of dictionaries with annotation details.")
        # Convert a single dictionary to a list of dictionaries
        if isinstance(annotation_data, dict):
            logger.info(f"\n\nannotation_data is a dic: \n{json.dumps(annotation_data, indent=4)}\n")
            annotation_data = [annotation_data]
            logger.info(f"annotation_data is now a list of dic: \n{json.dumps(annotation_data, indent=4)}\n")
        # Create temporary file for manipulation 
        temp_file_path = Path(working_csv_file_path).with_suffix('.tmp')
        with open(temp_file_path, mode='w', newline='') as temp_file:
            pass  # This ensures the file is truncated (emptied) if it exists
        
        # Initialize item number
        item_number = 1

        # Create the CSV file if it doesn't exist
        if not working_csv_file_path.exists():
            with open(working_csv_file_path, mode='w', newline='') as file:
                writer = csv.writer(file)
                # Write header row
                writer.writerow(['Item Number', 'Start Index', 'End Index', 'Label', 'Color'])

        # Open the working CSV file in read mode and the temporary file in write mode
        with open(working_csv_file_path, mode='r', newline='') as csv_file, open(temp_file_path, mode='w', newline='') as temp_file:
            reader = csv.reader(csv_file)
            writer = csv.writer(temp_file)

            headers = next(reader)  # Read the header row
            writer.writerow(headers)  # Write the header to the temporary file

            # Find the indices of the relevant columns
            item_col_index = headers.index('Item Number')
            start_index_col = headers.index('Start Index')
            end_index_col = headers.index('End Index')
            label_col = headers.index('Label')
            color_col = headers.index('Color')

            # Iterate through the rows after the headers row
            for row in reader:
                if not annotation_data:
                    break
                # Check if the row is empty for the current annotation
                if all(not row[idx] for idx in [item_col_index, start_index_col, end_index_col, label_col, color_col]):
                    # Use and remove the first dictionary in the list
                    annotation = annotation_data.pop(0)
                    logger.info(f"annotation_data.pop(0) is \n{annotation}\n\tfor item_number = {item_number}\n")
                    # Update the empty row with the annotation data
                    row[item_col_index] = item_number
                    row[start_index_col] = annotation.get('Start Index', '')
                    row[end_index_col] = annotation.get('End Index', '')
                    row[label_col] = annotation.get('Label', '')
                    row[color_col] = annotation.get('Color', '#d604a2')
                else:
                    # Assign an item number if it is missing or doesn't match the current item number
                    if not row[item_col_index] or int(row[item_col_index]) != item_number:
                        row[item_col_index] = item_number
                writer.writerow(row)
                # Increment the item number for the next iteration
                item_number += 1

            if annotation_data:
                logger.info(f"Current item_number being added: {item_number}\n")
                # If there are any remaining annotations, append them
                for annotation in annotation_data:
                    new_row = [''] * len(headers)
                    new_row[item_col_index] = item_number
                    new_row[start_index_col] = annotation.get('Start Index', '')
                    new_row[end_index_col] = annotation.get('End Index', '')
                    new_row[label_col] = annotation.get('Label', '')
                    new_row[color_col] = annotation.get('Color', '#d604a2')
                    writer.writerow(new_row)
                    item_number += 1

        # Replace the working CSV file with the temporary file
        os.replace(temp_file_path, working_csv_file_path)
        logger.info(f"Working CSV file was updated, and the temporary file was removed.\n")

    except Exception:
        logger.error(f"Unexpected error in handle_annotation_to_csv / add_annotation_to_csv: \n{traceback.format_exc()}\n")

def delete_annotation_from_csv(working_csv_file_path: Path, delete_data: list):
    """
    Deletes specific annotations from the CSV file based on delete_data and ensures that 
    the item numbers are reorganized to be continuous after deletion.

    Parameters:
    - working_csv_file_path (Path): Full file path of the working CSV file.
    - delete_data (list): A list of dictionaries, each containing:
        - 'Item Number': (str) The item number to delete.
        - 'Start Index': (str) The starting index of the annotation.
        - 'End Index': (str) The ending index of the annotation.
        - 'Label': (str) The label of the annotation.
        - 'Color': (str) The color of the annotation.
    
    Returns:
    - None
    """
    try:
        # Check if the file exists
        if not working_csv_file_path.exists():
            logger.info(f"File does not exist: {working_csv_file_path}\n")
            return
        # Early exit if delete_data is empty
        if not delete_data:
            logger.info(f"No rows to delete. {working_csv_file_path} remains unchanged.\n")
            return
        # Create a temporary file for manipulation 
        temp_file_path = Path(working_csv_file_path).with_suffix('.tmp')
        with open(temp_file_path, mode='w', newline='') as temp_file:
            pass  # This ensures the file is truncated (emptied) if it exists
        # Open the working CSV file in read mode and the temporary file in write mode
        with open(working_csv_file_path, mode='r', newline='') as csv_file, open(temp_file_path, mode='w', newline='') as temp_file:
            reader = csv.reader(csv_file)
            writer = csv.writer(temp_file)
            # Read and write headers
            headers = next(reader)
            writer.writerow(headers)
            # Get column indices dynamically
            item_num_col = headers.index('Item Number')
            start_idx_col = headers.index('Start Index')
            end_idx_col = headers.index('End Index')
            label_col = headers.index('Label')
            color_col = headers.index('Color')
            # Log the indices
            logger.info(f"Column indices for annotations:")
            logger.info(f"Item Number Column Index: {item_num_col}")
            logger.info(f"Start Index Column Index: {start_idx_col}")
            logger.info(f"End Index Column Index: {end_idx_col}")
            logger.info(f"Label Column Index: {label_col}")
            logger.info(f"Color Column Index: {color_col}\n")
            # Initialize item number counter
            item_number = 1
            # Iterate through rows to process deletions and reorganization
            for row in reader:
                # Flag to indicate if data should be updated
                match_found = False
                # Check if the current row matches any item in delete_data
                for delete_item in delete_data:
                    if (
                        row[item_num_col] == str(delete_item['Item Number']) and
                        row[start_idx_col] == str(delete_item['Start Index']) and
                        row[end_idx_col] == str(delete_item['End Index']) and
                        row[label_col] == str(delete_item['Label']) and
                        row[color_col] == str(delete_item['Color'])
                    ):
                        logger.info(f"\nDeleting row: {row}")
                        logger.info(f"\nMatching delete_item: Item Number: {delete_item['Item Number']}, Start Index: {delete_item['Start Index']}, "
                                    f"End Index: {delete_item['End Index']}, Label: {delete_item['Label']}, Color: {delete_item['Color']}")
                        logger.info(f"\nMatching row:         Item Number: {row[item_num_col]}, Start Index: {row[start_idx_col]}, "
                                    f"End Index: {row[end_idx_col]}, Label: {row[label_col]}, Color: {row[color_col]}\n\n")
                        delete_data.remove(delete_item)  # Remove matched item from delete_data
                        match_found = True
                        break  # Stop checking further delete_items for this row

                if not match_found:
                    # If the row is not being deleted, reorganize the item number
                    if any(row):  # Ensure the row is not completely empty
                        row[item_num_col] = item_number  # Reassign continuous item numbers
                        writer.writerow(row)
                        logger.info(f"Retained row with updated item number: {row}\n")
                        item_number += 1

        # Replace the original working CSV file with the temporary file. This will delete the temporary file.
        os.replace(temp_file_path, working_csv_file_path)
        if not delete_data:
            logger.info(f"Rows deleted and item numbers reorganized in {working_csv_file_path}, and the temporary file was removed.\n")
        else:
            logger.warning(f"Some rows from delete_data were not found in {working_csv_file_path}. \nRemaining items: \n\t{delete_data}\n")

    except Exception:
        logger.error(f"Error in handle_annotation_to_csv / delete_annotation_from_csv: \n\t{traceback.format_exc()}\n")

def retrieve_existing_annotations(working_csv_file_path: Path) -> list:
    """
    Retrieves existing annotations from a CSV file.

    Parameters:
    - working_csv_file_path (Path): Full file path of the working CSV file.

    Returns:
    - list: A list of dictionaries containing the existing annotation details. Each dictionary includes:
        - 'Item Number': (str) The unique item number.
        - 'Start Index': (str) The starting index of the annotation.
        - 'End Index': (str) The ending index of the annotation.
        - 'Label': (str) The label or description of the annotation.
        - 'Color': (str) The color associated with the annotation.
    """
    try:
        # List to store existing values
        existing_values = []

        if working_csv_file_path.exists():
            with open(working_csv_file_path, mode='r', newline='') as csv_file:
                reader = csv.reader(csv_file)
                headers = next(reader)  # Read the header row

                # Find the column indices dynamically
                item_col_index = headers.index('Item Number')
                start_index_col = headers.index('Start Index')
                end_index_col = headers.index('End Index')
                label_col = headers.index('Label')
                color_col = headers.index('Color')

                # Iterate through rows and collect non-empty rows
                for row in reader:
                    if row[item_col_index]:
                        existing_values.append({
                            'Item Number': row[item_col_index],
                            'Start Index': row[start_index_col],
                            'End Index': row[end_index_col],
                            'Label': row[label_col],
                            'Color': row[color_col],
                        })

        logger.info(f"Retrieved {len(existing_values)} existing annotations from {working_csv_file_path}\n")
        return existing_values
    except Exception:
        logger.error(f"Error in handle_annotation_to_csv / retrieve_existing_annotations: \n\t{traceback.format_exc()}\n")
        return []

def save_annotations_to_csv(working_csv_file_path: Path, saving_csv_file_path: Path):
    """
    Saves the working CSV file to the saving directory.

    Parameters:
    - working_csv_file_path (Path): Full file path of the working CSV file.
    - saving_csv_file_path (Path): Full file path where the CSV file should be saved.
    """
    try:
        # Copy the working CSV file to the saving directory
        if working_csv_file_path.exists():
            shutil.copy2(working_csv_file_path, saving_csv_file_path)
            logger.info(f"CSV file saved \n\tfrom {working_csv_file_path} \n\tto {saving_csv_file_path}\n")
            message = 'Progress Saved successfully!'
            status = True
            return message, status
        else:
            logger.error(f"Working CSV file does not exist: {working_csv_file_path}\n")
            message = 'There is no work to Save!'
            status = False
            return message, status
    except Exception:
        message = f"Error in handle_annotation_to_csv / save_annotations_to_csv: \n\t{traceback.format_exc()}!\n"
        status = False
        logger.error(message)
        return message, status

def save_all_annotations_to_csv(annotations_dir: Path) -> tuple[str, bool]:
    """
    Saves all working CSV files from the 'Working_Folder' structure to the
    corresponding 'Saving_Folder' structure under the provided annotations_dir,
    replicating any subdirectories. Includes retries for PermissionError during copy.

    Parameters:
    - annotations_dir (Path): Path object representing the base directory containing
                              'Working_Folder' and 'Saving_Folder'. Example:
                              '.../media/Raw_Time_Series_Data_CSV_Annotations'

    Returns:
    - tuple[str, bool]: A tuple containing a status message (str) and a success flag (bool).
                        The message summarizes the outcome, including any failures.
    """
    max_retries = 3
    retry_delay = 0.5 # seconds

    try:
        # --- Define Correct Root Paths ---
        if not annotations_dir or not annotations_dir.is_dir():
            message = f"Annotations base directory provided is invalid or does not exist: {annotations_dir}"
            status = False
            logger.error(message)
            return message, status

        working_root = annotations_dir / 'Working_Folder'
        saving_root = annotations_dir / 'Saving_Folder'

        logger.info(f"Starting 'Save All' operation.")
        logger.info(f"Source root (Working): {working_root}")
        logger.info(f"Destination root (Saving): {saving_root}")

        if not working_root.is_dir():
            message = f"Working folder does not exist, nothing to save: {working_root}"
            # This isn't strictly an error, just nothing to do.
            status = True
            logger.info(message)
            return message, status

        # Ensure the base saving directory exists.
        # Subdirectories will be created as needed later.
        saving_root.mkdir(parents=True, exist_ok=True)

        files_copied = 0
        files_failed = []
        files_processed_count = 0

        # --- Iterate, Calculate Paths, and Copy ---
        for working_file in working_root.rglob('*.csv'):
            files_processed_count += 1
            try:
                # Calculate the path relative to the working_root
                relative_path = working_file.relative_to(working_root)
                # Construct the corresponding saving file path
                saving_file = saving_root / relative_path
                # Ensure the specific subdirectory exists in the saving structure
                saving_file.parent.mkdir(parents=True, exist_ok=True)

                # --- Retry Logic ---
                copied_successfully = False
                for attempt in range(max_retries):
                    try:
                        # Attempt to copy the file
                        shutil.copy2(working_file, saving_file)
                        logger.info(f"Copied: {working_file.name} \n\t  to: {saving_file}")
                        copied_successfully = True
                        files_copied += 1
                        break # Exit retry loop on success

                    except PermissionError as pe:
                        if attempt < max_retries - 1:
                            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for '{working_file.name}' due to PermissionError: {pe}. Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                        else:
                            logger.error(f"Failed to copy '{working_file.name}' after {max_retries} attempts due to persistent PermissionError: {pe}")
                            logger.error(f"Source: {working_file}")
                            logger.error(f"Target: {saving_file}")
                            # Optionally log traceback for the last attempt's error
                            # logger.error(f"Traceback:\n{traceback.format_exc()}")
                            files_failed.append(str(relative_path)) # Log relative path of failed file

                    except OSError as oe: # Catch other OS-level errors like disk full etc.
                        logger.error(f"OS error copying '{working_file.name}': {oe}")
                        logger.error(f"Source: {working_file}")
                        logger.error(f"Target: {saving_file}")
                        files_failed.append(str(relative_path))
                        break # No point retrying most OS errors

                    except Exception as e:
                        # Catch any other unexpected errors during copy
                        logger.error(f"Unexpected error copying '{working_file.name}': {e}")
                        logger.error(f"Source: {working_file}")
                        logger.error(f"Target: {saving_file}")
                        logger.error(f"Traceback:\n{traceback.format_exc()}")
                        files_failed.append(str(relative_path))
                        break # Exit retry loop on unexpected error
                # --- End Retry Logic ---

                # If after retries it still failed, it would have been added to files_failed already.

            except ValueError as ve: # Error likely from relative_to if structure is unexpected
                logger.error(f"Error calculating relative path for {working_file} against {working_root}: {ve}")
                files_failed.append(str(working_file) + " (path calculation error)")
            except Exception as path_e:
                logger.error(f"Error processing file {working_file} (path/directory creation): {path_e}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                files_failed.append(str(working_file) + " (processing error)")


        # --- Final Status Reporting ---
        if not files_failed:
            if files_processed_count == 0:
                message = 'No CSV files found in the Working_Folder structure to save.'
                status = True
            else:
                message = f'All {files_copied} working CSV file(s) saved successfully!'
                status = True
        else:
            message = (f'Save All completed. Successfully saved {files_copied}/{files_processed_count} files. '
                       f'Failed to save {len(files_failed)} file(s): {", ".join(files_failed)} '
                       f'(Check logs for details).')
            status = False # Indicate partial or total failure

        logger.info(message) # Log final status
        return message, status

    except Exception as outer_e:
        # Catch errors in setting up paths, initial checks etc.
        message = f"Critical error during 'Save All' operation setup: \n\t{traceback.format_exc()}!\n"
        status = False
        logger.error(message)
        return message, status

def refresh_working_file(working_csv_file_path: Path):
    """
    Refreshes the working CSV file by erasing its content while retaining the header row.

    Parameters:
    - working_csv_file_path (Path): Path to the working CSV file.

    Description:
    - If the file exists, it clears all rows below the header.
    - If the file does not exist, it logs a message and takes no action.

    Returns:
    - None
    """
    try:
        if working_csv_file_path.exists():

            # Create temporary file for manipulation 
            temp_file_path = Path(working_csv_file_path).with_suffix('.tmp')
            with open(temp_file_path, mode='w', newline='') as temp_file:
                pass  # This ensures the file is truncated (emptied) if it exists
                
            with open(working_csv_file_path, mode='r', newline='') as csv_file, open(temp_file_path, mode='w', newline='') as temp_file:
                reader = csv.reader(csv_file)
                writer = csv.writer(temp_file)

                # Retain the header row
                headers = next(reader)  # Read the header row
                writer.writerow(headers)  # Write the header to the temporary file

                # Write blank rows for all rows below the header
                for row in reader:
                    blank_row = [''] * len(headers)  # Create an empty row with the same number of columns
                    writer.writerow(blank_row)

            # Replace the working CSV file with the temporary file
            os.replace(temp_file_path, working_csv_file_path)
            logger.info(f"Working CSV file refreshed: \n\t{working_csv_file_path}\n")
        else:
            logger.info(f"Nothing to reset. The working file does not exist: \n\t{working_csv_file_path}\n")
    except Exception:
        logger.error(f"Error in handle_annotation_to_csv / refresh_working_file: \n\t{traceback.format_exc()}\n")

def undo_last_annotation(working_csv_file_path: Path):
    """
    Undo the last annotation in the working CSV file.

    Parameters:
    - working_csv_file_path (Path): Path to the working CSV file.

    Description:
    - If the file exists, it finds and clears the last non-empty row.
    - If no annotations exist, it logs a message and takes no action.

    Returns:
    - None
    """
    try:
        if working_csv_file_path.exists():
            # Create temporary file for manipulation 
            temp_file_path = Path(working_csv_file_path).with_suffix('.tmp')
            with open(temp_file_path, mode='w', newline='') as temp_file:
                pass  # This ensures the file is truncated (emptied) if it exists
                
            with open(working_csv_file_path, mode='r', newline='') as csv_file, open(temp_file_path, mode='w', newline='') as temp_file:
                reader = csv.reader(csv_file)
                writer = csv.writer(temp_file)

                # Read and write the header row
                headers = next(reader)
                writer.writerow(headers)

                # Find the last non-empty row
                last_non_empty_row_index = None
                rows = list(reader)  # Read all rows into memory
                for i, row in enumerate(rows):
                    if any(row):  # Check if the row is not completely empty
                        last_non_empty_row_index = i

                # If no non-empty row is found, log and exit
                if last_non_empty_row_index is None:
                    logger.info(f"No annotations found in file: {working_csv_file_path}\n")
                    return

                # Rewrite the rows, clearing the last non-empty row
                for i, row in enumerate(rows):
                    if i == last_non_empty_row_index:
                        row = [''] * len(headers)  # Clear the row
                    writer.writerow(row)

            # Replace the working csv file with the temporary file
            os.replace(temp_file_path, working_csv_file_path)
            logger.info(f"Last annotation undone: \n\t{working_csv_file_path}\n")
        else:
            logger.info(f"Nothing to undo. The working file does not exist: \n\t{working_csv_file_path}\n")
    except Exception:
        logger.error(f"Error in undo_last_annotation: \n\t{traceback.format_exc()}\n")

def get_models(): # Working with WebSocket 
    """
    Reads the models file and extracts information about each model.

    Returns:
        dict: A dictionary where each key is a model name and the value is its associated information.
    """
    CSV_FILENAME = "_Models_List.csv"
    models_dir = os.path.join(settings.MEDIA_ROOT, "models_to_use")
    models_path = convert_path(os.path.join(models_dir, CSV_FILENAME))  # Normalize the file path
    logger.info(f"\nmodels_path: {models_path}")
    # Dictionary to store model information
    models_info = {}
    try:
        # Check if the file exists
        if not os.path.exists(models_path):
            logger.error(f"\nModels file not found at {models_path}.\n")
            return {"error": "Models file not found"}
        # Read the CSV file
        with open(models_path, mode='r', newline='') as file:  # No explicit encoding
            reader = csv.DictReader(file)  # Automatically maps headers to values
            for row in reader:
                model_name = row.get('Model Name')
                if model_name:
                    model_file = row.get('Model File')
                    full_path = convert_path(os.path.join(models_dir, model_file))  # Construct full path & Normalize

                    # Check if the file exists
                    if os.path.exists(full_path):
                        models_info[model_name] = {
                            "Model File": full_path,  # Store the full path
                            "Remarks": row.get('Remarks'),
                            "Short Description": row.get('Short Description')
                        }
                    else:
                        logger.warning(f"\nFile not found for model '{model_name}' at path: {full_path}\n")
                else:
                    logger.warning(f"\nSkipped a row due to missing 'Model Name': {row}\n")
        logger.info(f"\nModels loaded successfully from {models_path}.\n")
        logger.info(f"Here are the info: \n{json.dumps(models_info, indent=4)}\n")
        return models_info
    except Exception as e:
        logger.error(f"Error reading models file at {models_path}: {traceback.format_exc()}")
        return {"error": str(e)}

def add_metadata_to_csv(model_name: str, remarks: str, short_description: str, final_filename: str) -> None:
    """
    Appends model metadata as a new row to the _Models_List.csv file
    located within the MEDIA_ROOT/models_to_use directory.

    Creates the file with headers if it doesn't exist. Ensures the
    directory exists.

    Args:
        model_name: The unique name assigned to the model during upload.
        remarks: User-provided remarks about the model.
        short_description: A brief description of the model.
        final_filename: The actual filename (e.g., 'MyModel.pth' or 'MyModel_143522.pth')
                        as it was saved in the 'models_to_use' storage subdirectory.

    Raises:
        IOError: If there's an issue reading or writing the file.
        PermissionError: If file permissions prevent writing.
        csv.Error: If there's an issue with CSV formatting during write.
        Exception: Propagates other unexpected exceptions during the process.
    """

    # Define the expected header order - MUST match get_models logic if it relies on order/names
    CSV_HEADERS = ['Model Name', 'Model File', 'Remarks', 'Short Description']
    CSV_FILENAME = "_Models_List.csv"
    try:
        # Construct the full path to the target directory and the CSV file
        # Uses MEDIA_ROOT configured in settings.py as the base for user media
        models_upload_dir = os.path.join(settings.MEDIA_ROOT, "models_to_use")
        models_csv_path = convert_path(os.path.join(models_upload_dir, CSV_FILENAME))
        os.makedirs(models_upload_dir, exist_ok=True)

        logger.info(f"\nAttempting to add metadata for '{model_name}' to CSV: {models_csv_path}")
        logger.debug(f"\nMetadata details: Name='{model_name}', File='{final_filename}', "
                     f"ShortDesc='{short_description}', Remarks='{remarks[:50]}...'\n") # Log snippet

        # --- Check if file exists to determine if header is needed ---
        file_exists = os.path.exists(models_csv_path)
        # --- Open file in append mode ('a') ---
        # 'a': Appends to the end of the file if it exists, creates it otherwise.
        # newline='': Prevents extra blank rows being written by the csv module.
        # encoding='utf-8': Standard encoding for compatibility.
        with open(models_csv_path, mode='a', newline='', encoding='utf-8') as file:
            # Use csv.writer to write rows
            writer = csv.writer(file)

            # Write header row ONLY if the file is newly created (i.e., did not exist before)
            if not file_exists:
                writer.writerow(CSV_HEADERS)
                logger.info(f"\nModels CSV '{models_csv_path}' not found. Will create new file with headers.")
                logger.debug(f"Wrote headers to new file: {CSV_HEADERS}\n")

            # --- Write the actual metadata row ---
            # Order must match the CSV_HEADERS list
            data_row = [
                model_name,
                final_filename, # Use the final filename passed in
                remarks,
                short_description
            ]
            writer.writerow(data_row)
            logger.info(f"Successfully added metadata row for '{model_name}' to {models_csv_path}")

    # --- Specific Error Handling ---
    except (IOError, PermissionError) as e:
        error_msg = f"\nFile system error writing metadata to CSV at {models_csv_path}: {e}\n"
        logger.error(error_msg)
        logger.error(traceback.format_exc()) # Log full stack trace
        # Re-raise the specific exception so the calling view can potentially handle it
        # (though in this case, the view treats all exceptions similarly by deleting the .pth)
        raise e
    except csv.Error as e:
        error_msg = f"\nCSV writing error for {models_csv_path}: {e}\n"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise e
    # --- Generic Error Handling ---
    except Exception as e:
        error_msg = f"\nAn unexpected error occurred while adding metadata to CSV for model '{model_name}': {e}\n"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        # Re-raise the generic exception
        raise e

def get_directory_structure(scan_path: Path) -> dict:
    """
    Recursively scans a directory and returns its structure as a nested dict.
    Keys are folder names, values are sub-dictionaries. Includes the root folder.
    """
    structure = {}
    # Ensure the base directory exists before scanning
    if not scan_path.is_dir():
        logger.warning(f"\nDirectory to scan does not exist: {scan_path}\n")
        return {} # Return empty if base path doesn't exist

    # Use os.walk for potentially better performance on very large directories
    # and easier handling of the root vs subdirs
    for root, dirs, files in os.walk(scan_path):
        # Calculate path relative to the initial scan_path
        current_rel_path = Path(root).relative_to(scan_path)

        # Navigate the structure dict
        current_level = structure
        # Handle root case (current_rel_path is '.')
        parts = [p for p in current_rel_path.parts if p != '.']

        for part in parts:
            # Ensure parent exists, though os.walk guarantees this order
            if part not in current_level:
                current_level[part] = {} # Should not happen with os.walk structure
            current_level = current_level[part]

        # Add directories found at this level
        # Sort directories for consistent order
        dirs.sort()
        for dir_name in dirs:
            current_level[dir_name] = {} # Add empty dict for subdirectory

        # We don't need files for the target selection tree, but os.walk gives them
        # We only want folders in the structure
        # Because os.walk processes top-down, break after processing immediate dirs
        # or filter dirs to avoid going deeper than needed if only top-level is needed?
        # No, os.walk is designed to go through everything, the structure build handles depth.

    # The structure built above is nested. We might need the root dir name itself.
    # Let's return a dict with the root dir name as the top-level key.
    root_dir_name = scan_path.name
    final_structure = {root_dir_name: structure}
    return final_structure

def get_directory_contents_for_event(scan_path: Path, root_dir_name: str) -> list:
    """
    Scans a directory and returns a flat list of file dictionaries
    matching the 'directorySelected' event detail format.

    Args:
        scan_path (Path): The absolute path to the directory to scan (e.g., MEDIA_ROOT/Raw_Time_Series_Data).
        root_dir_name (str): The desired root directory name to include in the 'path' property.

    Returns:
        list: A list of dictionaries: [{'name': str, 'path': str, 'type': str}, ...].
              Path includes the root_dir_name and uses forward slashes.
    """
    contents = []
    if not scan_path.is_dir():
        logger.warning(f"\nDirectory to scan for event data does not exist: {scan_path}\n")
        return contents

    logger.info(f"Scanning '{scan_path}' for directory contents event data...")
    for root, dirs, files in os.walk(scan_path):
        # Path relative to the *scan_path* (e.g., 'SubFolder' or '.' for root)
        path_relative_to_scan = Path(root).relative_to(scan_path)

        files.sort() # Sort files for consistent order
        for filename in files:
            # Construct the path expected by the frontend event listener
            # Starts with root_dir_name, then subdirs (if any), then filename
            # Ensure forward slashes for web compatibility
            if str(path_relative_to_scan) == '.': # File is directly in scan_path
                 event_path = f"{root_dir_name}/{filename}"
            else:
                 # Convert relative path parts to string and join with forward slashes
                 sub_path = "/".join(path_relative_to_scan.parts)
                 event_path = f"{root_dir_name}/{sub_path}/{filename}"

            # Basic check if it's likely a CSV (can refine this)
            if filename.lower().endswith('.csv'):
                # Guess MIME type - might not be perfect, but mimics original structure
                mime_type, _ = mimetypes.guess_type(filename)
                file_info = {
                    'name': filename,
                    'path': event_path,
                    'type': mime_type or 'text/csv' # Default if guess fails
                }
                contents.append(file_info)
            # Optionally handle/log other file types if needed

    logger.info(f"Found {len(contents)} CSV files for directory contents event.")
    return contents

def file_iterator(file_path, chunk_size=8192):
    """
    A generator that yields chunks of a file and deletes the file afterwards.
    """
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    except FileNotFoundError:
        logger.error(f"Temporary file {file_path} not found during iteration.")
        # Optional: raise an error or yield nothing further
    except Exception as e:
        logger.error(f"Error reading temporary file {file_path}: {e}", exc_info=True)
        # Optional: raise or handle
    finally:
        # This block executes after the generator is exhausted or an error occurs
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Successfully removed temporary file via generator: {file_path}")
            except OSError as clean_err:
                logger.error(f"Error removing temporary file {file_path} via generator: {clean_err}", exc_info=True)

def clean_text(text):
    cleaned_text = re.sub(r'^\W+|\W+$', '', text)
    return cleaned_text

# Function to convert file path to a normalized path
def convert_path(path):
    return '' if not path else os.path.normpath(path) 

def read_csv_file(file_path: str, preview_rows: int = 5, 
                  days_towards_end: int = None, 
                  tz_default: str = "UTC",
                  days_from_start: int = None, description: str = ""):
    """
    Reads a CSV file and returns a pandas DataFrame filtered by date range.

    Args:
        file_path (str): The relative path to the CSV file.
        preview_rows (int): Number of rows to preview (default is 5).
        days_towards_end (int, optional): Number of days from the most recent date to retrieve data.
        days_from_start (int, optional): Number of days from the oldest date of the filtered data to retrieve data.
        tz_default (str): Default time zone if none is detected. Defaults to "UTC".
        description (str): A brief description of the dataset being loaded.
                           Explanation:
                           - To retrieve data from the **end**: Use `days_towards_end`.
                           - To retrieve data from the **start of the filtered range**: Use `days_from_start`.
                           - To retrieve data from the **middle**: Use both:
                             For example, if `days_towards_end=100` and `days_from_start=50`,
                             the function will first filter the last 100 days of the dataset,
                             and then filter the first 50 days from this range.
                             This results in data between the last 100th and the last 50th day.

    Returns:
        DataFrame: The loaded and filtered data from the CSV file.
    """
    try:
        if description:
            logger.info(f"\nDescription: {description}")
        logger.info(f"\nFile path: {file_path}")
        
        # Construct the full file path
        file_path = return_full_file_path(file_path)

        # Read the CSV file
        data = pd.read_csv(file_path, parse_dates=['date'], index_col='date')
        
        if not data.empty:
            # Filter by days towards the end
            if days_towards_end is not None:
                last_date = data.index.max()  # Get the most recent date in the dataset
                end_cutoff_date = last_date - pd.Timedelta(days=days_towards_end)
                data = data[data.index >= end_cutoff_date]
                logger.info(f"\nRetrieving data from the past {days_towards_end} days (from {end_cutoff_date.date()} onwards):")
            
            # Filter by days from the start (from the filtered data)
            if days_from_start is not None:
                first_date = data.index.min()  # Get the earliest date in the filtered dataset
                start_cutoff_date = first_date + pd.Timedelta(days=days_from_start)
                data = data[data.index <= start_cutoff_date]
                logger.info(f"\nRetrieving the first {days_from_start} days from the filtered data (up to {start_cutoff_date.date()}):")

            if preview_rows:
                logger.info(f"\nPreview of the first {preview_rows} rows:")
                display(data.head(preview_rows))
                logger.info(f"\nPreview of the last {preview_rows} rows:")
                display(data.tail(preview_rows))
                logger.info("Task complete!")
                logger.info(f"len(data) = {len(data)}")
            
            # Check if the index has timezone information
            if data.index.tz is not None:
                detected_tz = str(data.index.tz)
                logger.info(f"Detected time zone: {detected_tz} (type: {type(detected_tz)})")
            else:
                data = data.tz_localize(tz_default)
                detected_tz = tz_default
                logger.info(f"Set time zone: {detected_tz} (type: {type(detected_tz)})")

        return data, detected_tz
    except FileNotFoundError:
        logger.error("Error: File not found. Please check the file path. Returning an empty DataFrame.")
    except pd.errors.EmptyDataError:
        logger.error("Error: The file is empty. Returning an empty DataFrame.")
    except pd.errors.ParserError:
        logger.error("Error: The file could not be parsed. Please check the file format. Returning an empty DataFrame.")
    except Exception:
        logger.error(f"An unexpected error occurred: {traceback.format_exc()}. Returning an empty DataFrame.")
    # Return an empty DataFrame in case of any exception
    return pd.DataFrame(), tz_default

def return_full_file_path(relative_file_path=None):
    """
    Returns the full file path by combining the base file path with the relative file path.

    Parameters:
    - relative_file_path (str): The relative file path to be appended to the base path.

    Returns:
    - str: The full file path.
    """
    try:
        # Base path from settings
        # Full_path = os.path.join(os.path.normpath(settings.BASE_FILE_PATH), relative_file_path)
        Full_path = os.path.join(os.path.normpath(settings.MEDIA_ROOT), relative_file_path)
       
        # Log the full path
        logger.info(f"\n\nGenerated full file path: {Full_path}\n\n")
        
        return Full_path
    except Exception:
        # Log the exception
        logger.error(f"\n\nError generating full file path for {relative_file_path}: {e}\n\n")
        raise       

############################
def gaussian_smoothing(data: pd.DataFrame, sigma=2) -> pd.DataFrame:
    """
    Applies Gaussian smoothing to numeric columns in a DataFrame and ensures the index is sorted in ascending order.

    Args:
        data (pd.DataFrame): Input DataFrame.
        sigma (float): Standard deviation for the Gaussian kernel. Defaults to 2.

    Returns:
        pd.DataFrame: A DataFrame with smoothed numeric columns and sorted index.
    """
    # Sort the DataFrame by index in ascending order
    data = data.sort_index(ascending=True).copy()
    for column in data.columns:
        if pd.api.types.is_numeric_dtype(data[column]):  # Only apply to numeric columns
            data[column] = gaussian_filter1d(data[column].values, sigma=sigma)
    return data

def calculate_log_returns_all_columns(data: pd.DataFrame, exclude_columns: list = [], dropna: bool = False, fillna_value: float = 0) -> pd.DataFrame:
    """
    Calculate log returns for all numeric columns in a pandas DataFrame,
    excluding specified columns, and removing excluded columns from the returned DataFrame.

    Args:
        data (pd.DataFrame): Input DataFrame containing numeric data.
        exclude_columns (list): List of columns to exclude from log return calculations and the result.
        dropna (bool): Whether to drop rows with NaN values resulting from the calculation.
        fillna_value (float): Value to replace NaN values in the first row (default is 0).

    Returns:
        pd.DataFrame: DataFrame with log returns for numeric columns,
                      excluding specified columns.
    """
    data = data.copy().drop(columns=exclude_columns)
    columns_to_transform = data.select_dtypes(include=[np.number]).columns
    logger.info(f"columns_to_transform = \n{columns_to_transform}, \nlen(columns_to_transform) = {len(columns_to_transform)}")
    for col in columns_to_transform:
        # Ensure no negative or zero values
        if (data[col] <= 0).any():
            raise ValueError(f"Column '{col}' contains non-positive values. Log returns require strictly positive values.")
        data[col] = np.log(data[col] / data[col].shift(1))
    # Optionally drop rows with NaN values
    data = data.dropna() if dropna else data
    # Fill NaN values resulting from the first row
    data = data.fillna(value=fillna_value)
    return data

def build_GRU_prediction_model(input_size: int, hidden_size: int, output_size: int, num_layers: int, dropout: float = 0.0) -> nn.Module:
    """
    Creates and initializes a GRU-based classification model.

    Args:
        input_size (int): Number of input features.
        hidden_size (int): Number of GRU hidden units.
        output_size (int): Number of output classes.
        num_layers (int): Number of GRU layers.
        dropout (float): Dropout rate for regularization.

    Returns:
        nn.Module: The initialized GRU-based classification model.
    """
    class Classif_GRU_Model(nn.Module):
        def __init__(self, input_size: int, hidden_size: int, output_size: int, num_layers: int, dropout: float = 0.0):
            super(Classif_GRU_Model, self).__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            # GRU Layer
            self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True, dropout=dropout)
            # Fully connected layer to map hidden state to output
            self.fc = nn.Linear(hidden_size, output_size)
            self.init_weights()

        def init_weights(self):
            for name, param in self.named_parameters():
                if 'weight' in name:
                    nn.init.xavier_uniform_(param)  # Xavier initialization
                elif 'bias' in name:
                    nn.init.constant_(param, 0)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # GRU forward pass
            h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)  # Initial hidden state
            out, _ = self.gru(x, h0)
            # Fully connected output layer
            out = self.fc(out)  # Shape: (batch_size, seq_length, output_size)
            return out
    return Classif_GRU_Model(input_size, hidden_size, output_size, num_layers, dropout)

def build_BiGRUWithAttention_model(input_size: int, hidden_size: int, output_size: int, num_layers: int, dropout: float = 0.0) -> nn.Module:
    """
    Creates and initializes a Bi-Directional GRU model with Attention mechanism.

    Args:
        input_size (int): Number of input features.
        hidden_size (int): Number of GRU hidden units.
        output_size (int): Number of output classes.
        num_layers (int): Number of GRU layers.
        dropout (float): Dropout rate for regularization.

    Returns:
        nn.Module: The initialized Bi-Directional GRU with Attention model.
    """

    class BiGRUWithAttention(nn.Module):
        def __init__(self, input_size: int, hidden_size: int, output_size: int, num_layers: int, dropout: float = 0.0):
            super(BiGRUWithAttention, self).__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            # Bi-Directional GRU Layer
            self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True, bidirectional=True, dropout=dropout)
            # Attention layer
            self.attention_fc = nn.Linear(hidden_size * 2, hidden_size * 2)  # Hidden size * 2 for bi-directional
            # Fully connected layer for classification
            self.fc = nn.Linear(hidden_size * 2, output_size)
            self.dropout = nn.Dropout(dropout)  # Apply dropout before the fully connected layer
            self.init_weights()

        def init_weights(self):
            for name, param in self.named_parameters():
                if 'weight' in name:
                    nn.init.xavier_uniform_(param)  # Xavier initialization for weights
                elif 'bias' in name:
                    nn.init.constant_(param, 0)  # Zero initialization for biases

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            h0 = torch.zeros(self.num_layers * 2, x.size(0), self.hidden_size).to(x.device)  # Bi-directional: num_layers * 2
            # Bi-Directional GRU forward pass
            out, _ = self.gru(x, h0)  # Shape: (batch_size, seq_length, hidden_size * 2)

            # Attention mechanism
            attn_weights = torch.tanh(self.attention_fc(out))  # Shape: (batch_size, seq_length, hidden_size * 2)
            out = attn_weights * out  # Element-wise attention application
            out = self.dropout(out)  # Apply dropout

            # Fully connected layer (applied at each time step)
            out = self.fc(out)  # Shape: (batch_size, seq_length, output_size)
            return out

    return BiGRUWithAttention(input_size, hidden_size, output_size, num_layers, dropout)

def detect_time_interval(df: pd.DataFrame) -> pd.Timedelta:
    """
    Detect the most frequent time interval from a DataFrame index.
    """
    index_diff = df.index.to_series().diff().dropna()
    time_interval = index_diff.mode()[0]  # Most frequent difference
    logger.info(f"Detected Time Interval: {time_interval}")
    return time_interval

def construct_prediction_df(df: pd.DataFrame, predictions: np.ndarray, time_interval: pd.Timedelta) -> pd.DataFrame:
    """
    Construct a DataFrame with timestamps and predictions.
    """
    num_rows = len(predictions)
    timestamps = pd.date_range(start=df.index[0], periods=num_rows, freq=time_interval)
    logger.info(f"len(timestamps) = {len(timestamps)}")
    
    predictions_df = pd.DataFrame({
        'date': timestamps,
        'trend': predictions
    })
    return predictions_df

def build_prediction_ranges(predictions_df: pd.DataFrame, 
                            trend_descriptions: dict, 
                            trend_colors: dict) -> list:
    """
    Build a list of continuous prediction ranges from the predictions DataFrame.

    Parameters:
    - predictions_df (pd.DataFrame): A DataFrame containing 'date' and 'trend' columns.
                                     'date' is the timestamp, and 'trend' represents the prediction values.
    - trend_descriptions (dict): A dictionary mapping trend values to descriptive labels.
    - trend_colors (dict): A dictionary mapping trend values to corresponding colors.

    Returns:
    - list: A list of dictionaries, where each dictionary contains:
        - 'Item Number' (int): Sequential number for the range.
        - 'Start Timestamp' (datetime): The start timestamp of the continuous range.
        - 'End Timestamp' (datetime): The end timestamp of the continuous range.
        - 'Label' (str): A descriptive label for the trend.
        - 'Color' (str): A color representing the trend.
    """
    ranges_list = []
    current_value = predictions_df['trend'].iloc[0]
    logger.info(f"current_value type: {type(current_value)}, current_value | predictions_df['trend'].iloc[0]: {current_value}")
    start_index = 0
    for i in range(1, len(predictions_df)):
        # logger.info(f"predictions_df['trend'].iloc[i] type: {type(predictions_df['trend'].iloc[i])}, predictions_df['trend'].iloc[i]: {predictions_df['trend'].iloc[i]}")
        if predictions_df['trend'].iloc[i] != current_value:
            # End of the current range, save the range info
            ranges_list.append({
                'Item Number': len(ranges_list) + 1,
                'Start Index': predictions_df['date'].iloc[start_index].isoformat(),  # Convert to ISO format
                'End Index': predictions_df['date'].iloc[i - 1].isoformat(),          # Convert to ISO format
                'Label': trend_descriptions[int(current_value)],  # Cast to int
                'Color': trend_colors[int(current_value)]         # Cast to int
            })
            # Update start_index and current_value
            start_index = i
            current_value = predictions_df['trend'].iloc[i]
    # Add the last range
    ranges_list.append({
        'Item Number': len(ranges_list) + 1,
        'Start Index': predictions_df['date'].iloc[start_index].isoformat(),  # Convert to ISO format
        'End Index': predictions_df['date'].iloc[-1].isoformat(),             # Convert to ISO format
        'Label': trend_descriptions[int(current_value)],  # Cast to int
        'Color': trend_colors[int(current_value)]         # Cast to int
    })
    logger.info(f"len(ranges_list) = {len(ranges_list)}")
    return ranges_list

def print_ranges(ranges_list: list):
    """
    Print the prediction ranges in a readable format.
    """
    logger.info(f"\nHere are the {len(ranges_list)} predicted labels in ranges_list:")
    for item in ranges_list:
        logger.info(item)
        # print(item)
    logger.info("")

def process_predictions(data: pd.DataFrame, 
                        predictions: np.ndarray, 
                        trend_descriptions: dict, 
                        trend_colors: dict,
                        printing: bool = False) -> list:
    """
    Process predictions to generate continuous trend ranges.

    This function performs the following steps:
    1. Detects the time interval of the input DataFrame's index.
    2. Constructs a new DataFrame combining the input timestamps with predictions.
    3. Groups continuous ranges of identical predictions and maps them to descriptive labels and colors.
    4. Optionally prints the results.

    Parameters:
    - test_sequences_df (pd.DataFrame): Input DataFrame containing the original timestamps and features.
    - predictions (np.ndarray): Array of predictions corresponding to the rows in the input DataFrame.
    - trend_descriptions (dict): A dictionary mapping prediction values to descriptive labels.
    - trend_colors (dict): A dictionary mapping prediction values to colors.
    - printing (bool, optional): If True, prints the generated ranges. Default is False.

    Returns:
    - list: A list of dictionaries, where each dictionary represents a continuous trend range and includes:
        - 'Item Number' (int): A sequential number for the trend range.
        - 'Start Timestamp' (datetime): The starting timestamp of the trend range.
        - 'End Timestamp' (datetime): The ending timestamp of the trend range.
        - 'Label' (str): A descriptive label for the trend.
        - 'Color' (str): A color representing the trend.
    """

    # Step 1: Detect time interval
    time_interval = detect_time_interval(df=data)
    
    # Step 2: Construct prediction DataFrame
    predictions_df = construct_prediction_df(df=data, predictions=predictions, time_interval=time_interval)
    
    # Step 3: Build prediction ranges
    ranges_list = build_prediction_ranges(predictions_df=predictions_df, trend_descriptions=trend_descriptions, trend_colors=trend_colors)
    
    if printing:
        # Step 4: Print the ranges
        print_ranges(ranges_list=ranges_list)

    return ranges_list

# Funtion for auto labeling
def run_auto_labeling_of_annotations(relative_file_path: str, working_csv_file_path: str, selected_model: str, labels_list: list[dict]):# -> list[dict]:
    """
        Automates the labeling process by retrieving and preprocessing data, applying a pre-trained model, 
        and generating predictions with trend analysis.

        Args:
            relative_file_path (str): Path to the source CSV file containing input data.
            working_csv_file_path (str): Path to the working CSV file where predictions and annotations will be saved.
            selected_model (str): Name of the model to be used for generating predictions.
            labels_list (list[dict]): A list of dictionaries representing label definitions. Each dictionary should include:
                - 'label' (int): Numeric identifier for the label.
                - 'value' (str): Description or value of the label.
                - 'Color' (str): Color associated with the label.

        # Returns:
        #     list[dict]: A list of dictionaries where each dictionary represents a continuous prediction range with:
        #         - 'Item Number' (int): Sequential number for the range.
        #         - 'Start Index' (datetime): The start timestamp of the continuous range.
        #         - 'End Index' (datetime): The end timestamp of the continuous range.
        #         - 'Label' (str): A descriptive label for the trend.
        #         - 'Color' (str): A color representing the trend.
    """
    start_time = time.perf_counter()
    # Retrieve the data
    logger.info(f"\nLoading data from file: {relative_file_path}")
    data, _ = read_csv_file(file_path=relative_file_path, preview_rows=0)
    
    if data.empty:
        logger.error(f"Data from {relative_file_path} is empty. Cannot proceed with auto-labeling.")
        # Might need to set a message system to inform front end if labeling was success of failure
        return []

    # Smooth the data
    logger.info(f"Applying Gaussian smoothing with sigma=7 to the data.")
    processed_data = gaussian_smoothing(data, sigma=7)

    # Compute log returns
    logger.info(f"Calculating log returns for smoothed data.")
    try:
        processed_data = calculate_log_returns_all_columns(processed_data, exclude_columns=[], fillna_value=0)
    except ValueError as e:
        logger.error(f"Error calculating log returns: {traceback.format_exc()}")
        # Might need to set a message system to inform front end if labeling was success of failure
        return []

    # Convert to NumPy array
    logger.info(f"Converting log data to numpy array.")
    processed_data = processed_data.to_numpy()

    # Validate data
    logger.info("Validating data format in NumPy array.")
    for ind, feature_set in enumerate(processed_data):
        for feature_idx, feature in enumerate(feature_set):
            if not isinstance(feature, (float, np.float32)):
                logger.error(f"Unexpected type in log_data_np at row {ind}, column {feature_idx}: {type(feature)}")
                raise ValueError("Invalid data type detected in log_data_np.")

    # Load the model
    logger.info(f"Loading models and retrieving path for selected model: {selected_model}")
    model_info = get_models() # Get info for all models
    model_info = model_info.get(selected_model) # Extract info for our target model

    if not model_info:
        logger.error(f"Selected model '{selected_model}' not found in available models.")
        # Might need to set a message system to inform front end if labeling was success of failure
        return []

    model_path = model_info['Model File']
    logger.info(f"Model path retrieved: {model_path}")

    # Define model parameters
    Number_features = data.shape[1] # data same as the log processed data in here.
    input_size = Number_features
    hidden_size = 64
    output_size = 5
    dropout=0.0
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Using device: {device}")

    # Initialize the model
    if re.search(r'\b(GRU\s+model|model\s+GRU)\b', selected_model, re.IGNORECASE):
        num_layers = 2
        logger.info(f"Model parameters: input_size={input_size}, hidden_size={hidden_size}, output_size={output_size}, num_layers={num_layers}, dropout={dropout}")
        prediction_model = build_GRU_prediction_model(input_size=input_size, hidden_size=hidden_size, output_size=output_size, num_layers=num_layers, dropout=dropout)
    else:
        # num_layers = 4
        # logger.info(f"Model parameters: input_size={input_size}, hidden_size={hidden_size}, output_size={output_size}, num_layers={num_layers}, dropout={dropout}")
        # prediction_model = build_BiGRUWithAttention_model(input_size=input_size, hidden_size=hidden_size, output_size=output_size, num_layers=num_layers, dropout=dropout)
        num_layers = 2
        logger.info(f"Model parameters: input_size={input_size}, hidden_size={hidden_size}, output_size={output_size}, num_layers={num_layers}, dropout={dropout}")
        prediction_model = build_GRU_prediction_model(input_size=input_size, hidden_size=hidden_size, output_size=output_size, num_layers=num_layers, dropout=dropout)

    # Load model checkpoint
    checkpoint = torch.load(model_path, map_location=device, weights_only=True)
    if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
        logger.info("Loading model from dictionary checkpoint.")
        prediction_model.load_state_dict(checkpoint['model_state_dict'])
    else:
        logger.info("Loading model directly from state dict.")
        prediction_model.load_state_dict(checkpoint)

    prediction_model.to(device)
    prediction_model.eval() # Set model to evaluation mode

    logger.info(f"prediction_model: \n{prediction_model}")

    # Prepare data tensor
    processed_data = torch.tensor(processed_data, dtype=torch.float32).to(device).unsqueeze(1)

    # Run predictions
    logger.info("Running predictions using the loaded model.")
    with torch.no_grad():
        outputs = prediction_model(processed_data)
        outputs = outputs.view(-1, output_size)
        predictions = torch.argmax(outputs, dim=-1).cpu().numpy()
        logger.info(f"\n outputs. Shape: \n{outputs.shape} \n")
        logger.info(f"\n outputs. Shape: \n{outputs.shape} \n")
        logger.info(f"\n predictions. Shape: \n{predictions.shape} \n")

    logger.info(f"Predictions completed. Shape: {predictions.shape}")

    # Create trend_colors and trend_descriptions based on labels_list
    trend_colors = {label['label']: label['Color'] for label in labels_list}
    trend_descriptions = {label['label']: label['value'] for label in labels_list}

    # Log the mappings with beautiful formatting
    logger.info(f"Trend colors updated:\n{json.dumps(trend_colors, indent=4)}")
    logger.info(f"Trend descriptions updated:\n{json.dumps(trend_descriptions, indent=4)}")

    # Return predictions as a DataFrame
    ranges_list = process_predictions(data=data, 
                                      predictions=predictions, 
                                      trend_descriptions=trend_descriptions, 
                                      trend_colors=trend_colors,
                                      printing=False)
    logger.info(f"Obtained {len(ranges_list)} predictions with our selected {selected_model}.")

    if working_csv_file_path.exists():
        logger.info(f"Deleting the existing CSV file at {working_csv_file_path}")
        os.remove(working_csv_file_path)
    
    logger.info(f"Adding predictions to the emptied working CSV file...")
    add_annotation_to_csv(working_csv_file_path, ranges_list)

    end_time = time.perf_counter()
    inference_time_ms = (end_time - start_time) * 1000 # Calculate inference speed
    logger.info(f"\n\nInference time for auto labeling with selected_model '{selected_model}': {inference_time_ms:.2f} ms\n\n")
    # return ranges_list
############################

# Function to plot pd.DataFrame data using Plotly
def plot_with_plotly(data: pd.DataFrame, 
                     title: str, 
                     save_path: str = None, 
                     show_plot: bool = False,
                     Title_Color: str = None,
                     labels_pipe_value: list[dict] = [],
                     existing_values: list[dict] = [],
                     click_data:dict = None) -> go.Figure:
    """
    Generates an interactive Plotly graph of a DataFrame with optional trend-based annotations 
    and display logic for segments.

    Parameters:
    - data (pd.DataFrame): Input data to plot. Must contain a 'close' column for plotting.
                           Index should ideally represent timestamps or sequential indices.
    - title (str): Title displayed at the top of the plot.
    - save_path (Optional[str]): If provided, saves the plot as an HTML file at the specified location.
    - show_plot (bool): If True, displays the plot. If False, skips plot display.
    - Title_Color (Optional[str]): Color of the title text. Defaults to yellow if not provided.
    - labels_pipe_value (list[dict]): A list of label dictionaries with keys:
                                      - 'value' (label name),
                                      - 'display' (int, 1 for visible, 0 for hidden).
    - existing_values (list[dict]): A list of annotated segments, where each dict contains:
                                    - 'Item Number': Unique identifier for the segment.
                                    - 'Start Index': Starting index or timestamp for the segment.
                                    - 'End Index': Ending index or timestamp for the segment.
                                    - 'Label': Name of the trend or annotation.
                                    - 'Color': Color for the segment line.
    - click_data (dict): A dictionary containing the start and end indices of a newly selected segment 
                         (e.g., from interactive clicks on the graph).

    Returns:
    - go.Figure: The generated Plotly figure object.

    Features:
    1. Plots the entire "close" column as a base line with a neutral gray color.
    2. Adds annotations for existing segments (`existing_values`) with custom colors and labels.
       - Segments are only plotted if their corresponding `display` flag in `labels_pipe_value` is set to 1.
    3. Highlights newly selected segments (via `click_data`) with a green line overlay.
    4. Allows saving the plot to an HTML file and optional display.

    Notes:
    - The function uses a clean white theme (`plotly_white`) with a dark background for better contrast.
    - Custom legends are configured with clear segment names and colors.
    - Segments that are hidden (based on `display` flag) are skipped from rendering.
    """
    
    # Create the Plotly figure
    base_plot_color = '#808080'  # Neutral gray for the base plot (before '#4fa1ee')
    highlight_color = 'yellow' #'green'    # Color for new segments (via click_data)
    annotated_width = 4 # Annotation width for annotated segments

    fig = go.Figure(
        layout={
            'xaxis': {
                'title': 'Date',
                'color': 'yellow',
                'autorange': True,  # Ensure axis range adjusts to fit the data
                # 'uirevision': 'constant'  # Maintain user interactions like zoom/pan
                # 'showgrid': True,   # Show grid lines
                # 'gridcolor': '#404040',  # A dark grey color of the vertical grid lines
                # 'gridwidth': 1,     # Make the grid lines thin
                # 'dtick': 50,       # Smaller grid spacing for ECG
            },
            'yaxis': {
                'title': 'Closing Price (USD)',
                'color': 'lightgreen',
                'autorange': True,  # Ensure axis range adjusts to fit the data
                # 'uirevision': 'constant'  # Maintain user interactions
                # 'showgrid': True,   # Show grid lines
                # 'gridcolor': '#404040',  # A dark grey color of the horizontal grid lines
                # 'gridwidth': 1,     # Make the grid lines thin
                # 'dtick': 10,       # Smaller grid spacing for ECG
            },
            'title': {
                'text': title,
                'font': {
                    'size': 15,
                    'color': Title_Color if Title_Color else 'yellow',  # Use Title_Color here
                    'family': 'Arial, sans-serif'
                }
            },
            'paper_bgcolor': '#27293d',
            'plot_bgcolor': 'rgba(0,0,0,0)',
            'transition': {'duration': 300, 'easing': 'cubic-in-out'},
            'legend': { # Adding legend configuration
                'font': {
                    'color': 'Black',  # Legend text color
                    'size': 14,      # Legend font size
                    'family': 'Arial, sans-serif',  # Font family
                    # 'family': 'Arial Black, sans-serif'  # Choose a bold font family
                },
                # 'bgcolor': 'LightSteelBlue',  # Optional: Legend background color
                'bgcolor': 'white', #'white', # Optional: Legend background color
                'bordercolor': 'Black',  # Optional: Legend border color
                'borderwidth': 2  # Optional: Legend border width
            },
            'legend_title': {'text': 'Trends'},  # Add legend title
            'template': 'plotly_white'           # Add template
        }
    )
    
    # Check for edge cases: Empty data or missing 'close' column
    if len(data)==0 or 'close' not in data.columns:
        logger.info(f"\n\nPlotting empty data\n\n")
        fig.add_trace(go.Scatter(
            x=[],
            y=[],
            mode='lines',
        ))
        return fig

    def get_display_status(label_name):
        for label_data in labels_pipe_value:
            if label_data['value'] == label_name:
                # Retrieve the display status (default to False if 'display' key is missing)
                return label_data.get('display', 0) == 1
        return False

    def plot_segments(existing_values, data, color_override=None):
        for item in existing_values:
            start_time = item['Start Index']
            end_time = item['End Index']
            color = color_override if color_override else item['Color']
            label_name = item.get('Label', 'Unknown trend')
            segment_name = f"Item {item['Item Number']}: {label_name}"  # Use the label from the item for the trace name
            display_status = get_display_status(label_name)  # Retrieve display status for this segment
            # logger.info(f"Display value: {display_status}")
            if display_status:
                # Plot only the annotated segments (they'll overlay on the full plot)
                segment = data.loc[start_time:end_time]
                fig.add_trace(go.Scatter(
                    x=segment.index,
                    y=segment['close'],
                    line=dict(color=color, width=annotated_width),  # Thicker annotated line
                    mode='lines',
                    name=f"<span style='color:{color}'>{segment_name}</span>",  # Custom name with color
                ))
            else:
                logger.info(f"Skipping segment: {segment_name} due to display_status being set to 0")

    # First, plot the entire "close" column as a base waveform
    fig.add_trace(go.Scatter(
        x=data.index,
        y=data['close'],
        line=dict(color=base_plot_color),  # Default color for the entire line (before '#4fa1ee')
        mode='lines',
        # name='Default',  # Custom trace name
        name=f"<span style='color:{base_plot_color}'>{'Default'}</span>"  # Custom name with color
    ))
    
    if existing_values:
        logger.info(f"In plot_with_plotly function, \n\t\t\trebuilding annotations from existing_values\n")
        plot_segments(existing_values, data)

    if click_data:
        x1, x2 = sorted(click_data)
        logger.info(f"In plot_segments function, \n\t\t\tif click_data = True ({click_data})\n")
        # Plot the clicked segment (it will overlay the default line)
        segment = data.loc[x1:x2]
        fig.add_trace(go.Scatter(
            x=segment.index, 
            y=segment['close'], 
            line=dict(color=highlight_color, width=annotated_width),  # Highlight the new segment
            mode='lines',
            name=f"<span style='color:{highlight_color}'>New Segment</span>"
        ))
        logger.info(f"\n\nThe [x1, x2] segment from click_data was updated.\n\n")

    # Save the plot as an HTML file if a save path is provided
    if save_path:
        fig.write_html(save_path)
        logger.info(f"\nPlot saved to: {save_path}\n")

    # Show the plot if requested
    if show_plot:
        fig.show()

    # fig.frames = [go.Frame(data=[go.Scatter(y=data)])] # Looks like this can be removed.
    return fig

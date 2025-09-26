
# Create your views here.

# home/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout as auth_logout
from django.middleware.csrf import get_token # To pass token to template if needed
from django.http import JsonResponse, FileResponse
from django.conf import settings
from django.views.decorators.http import require_POST, require_http_methods
from django.core.files.storage import default_storage
from django.core.exceptions import PermissionDenied, TooManyFilesSent
from datetime import datetime
from .utils import (
    add_metadata_to_csv, get_directory_structure, get_directory_contents_for_event,
    file_iterator
)
from pathlib import Path
import os
import re
import json
import logging
import zipfile
import tempfile # Required for temporary files
# from contextlib import contextmanager

# Setup logger
logger = logging.getLogger('home')

# Existing view
def home(request):
    return redirect('home:login')  # Redirect to the welcome view

def custom_login(request):
    auth_logout(request)
    request.session.flush()
    return auth_views.LoginView.as_view(template_name='home/login.html')(request)

@login_required
def welcome(request):
    """
        Ensure the welcome view context includes the CSRF token if needed by JS directly
        (though fetch usually handles it via cookies if middleware is set up)
    """
    context = {
        # 'base_file_path': settings.BASE_FILE_PATH, # Obsolete for input
        'csrf_token': get_token(request) # Pass CSRF token if needed by JS explicitely
    }
    logger.info("The welcome function ran successfully.\t\t\t\t, and welcome.html is running!\n")
    return render(request, 'home/welcome.html', context)

# Registration view
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'errors': form.errors})
    else:
        form = UserCreationForm()
    return render(request, 'home/register.html', {'form': form})

# custom_logout view, this is the view called when I click on the logout button.
def custom_logout(request):
    auth_logout(request)
    request.session.flush()
    return render(request, 'home/logout.html')  # Render the logout page after logging out

@login_required
@require_POST # Ensures this view only accepts POST requests
def upload_model_view(request):
    try:
        # 1. Extract Data from the request
        model_name = request.POST.get('model_name')
        remarks = request.POST.get('remarks')
        short_description = request.POST.get('short_description')
        model_file = request.FILES.get('model_file') # Key matches formData.append()

        # 2. Perform Server-Side Validation (CRITICAL!)
        # Even though JS validates, always re-validate on the server.
        errors = []
        if not model_name: errors.append("Model name is required.")
        if not remarks: errors.append("Remarks are required.")
        if not short_description: errors.append("Short description is required.")
        if not model_file: errors.append("Model file is required.")
        if errors:
            return JsonResponse({'status': 'error', 'message': " ".join(errors)}, status=400)

        # Further validation
        # Use regex to allow only letters, numbers, and spaces
        model_name_pattern = r'^[a-zA-Z0-9 ]+$' # Pattern: start, 1+ alphanum or space, end
        if not re.fullmatch(model_name_pattern, model_name):
             return JsonResponse({'status': 'error', 'message': 'Invalid model name (only letters, numbers, and spaces allowed).'}, status=400)
        if len(model_name) > 30:
             return JsonResponse({'status': 'error', 'message': 'Model name exceeds 30 characters.'}, status=400)
        if len(short_description) > 30:
             return JsonResponse({'status': 'error', 'message': 'Short description exceeds 30 characters.'}, status=400)
        if len(remarks) > 300:
             return JsonResponse({'status': 'error', 'message': 'Remarks exceed 300 characters.'}, status=400)
        # File specific validation
        if not model_file.name.lower().endswith('.pth'):
            return JsonResponse({'status': 'error', 'message': 'Invalid file type. Only .pth allowed.'}, status=400)
        # Optional: File size validation (example: 50MB limit)
        # MAX_UPLOAD_SIZE = 20 * 1024 * 1024
        MAX_UPLOAD_SIZE = settings.MAX_UPLOAD_SIZE_BYTES # Use the 50MB limit from settings
        if model_file.size > MAX_UPLOAD_SIZE:
           return JsonResponse({'status': 'error', 'message': f'File size exceeds {MAX_UPLOAD_SIZE // 1024 // 1024}MB limit.'}, status=400)

        # 3. Save the File using Django's storage system
        # Define a subdirectory within your MEDIA_ROOT (ensure MEDIA_ROOT is set in settings.py)
        upload_subdir = 'models_to_use'
        final_filename = model_file.name
        file_path_to_check = os.path.join(upload_subdir, final_filename)
        # Check if file already exists
        if default_storage.exists(file_path_to_check):
            logger.info(f"File '{file_path_to_check}' already exists. Appending timestamp.")
            timestamp = datetime.now().strftime('%H%M%S')
            base_filename, file_ext = os.path.splitext(final_filename) # Get base name and extension
            final_filename = f"{base_filename}_{timestamp}{file_ext}"
            final_file_path = os.path.join(upload_subdir, final_filename)
            logger.info(f"New filename will be: '{final_filename}'")
        else:
            final_file_path = file_path_to_check # Use the original path if no collision
        del file_path_to_check

        # Save the File using Django's storage system
        # default_storage handles saving to MEDIA_ROOT by default
        saved_path = default_storage.save(final_file_path, model_file)
        logger.info(f"File '{final_filename}' successfully saved to: {saved_path}\n") # Log the path relative to MEDIA_ROOT

        # 4. Save Metadata (e.g., to Database)
        try:
            add_metadata_to_csv(
                model_name=model_name,
                remarks=remarks,
                short_description=short_description,
                final_filename=final_filename # Pass the actual path where it was saved
            )
            logger.info(f"Metadata for model '{model_name}' added via utility function.")
        except Exception as metadata_error:
            # Important: If metadata save fails, delete the orphaned file
            logger.error(f"Error saving metadata for '{model_name}': {metadata_error}", exc_info=True) # Log full traceback
            if saved_path and default_storage.exists(saved_path):
                  logger.warning(f"Rolling back file save: Deleting orphaned file '{saved_path}'")
                  default_storage.delete(saved_path)
            return JsonResponse({'status': 'error', 'message': 'File uploaded but not saved, because failed to save model metadata.'}, status=500)

        # 5. Return Success Response
        return JsonResponse({
            'status': 'success',
            'message': f'Model "{model_name}" uploaded successfully. \nReload the page.',
            'saved_path': saved_path # Optional: return the path if needed by frontend
        }, status=200)

    except Exception as e:
        # Generic error handler for unexpected issues during processing
        print(f"Unexpected Upload Error: {e}") # Log the full error server-side
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred during upload.'}, status=500)

# --- Updated View ---
@login_required
# Allow both GET (for structure) and POST (for upload)
@require_http_methods(["GET", "POST"])
def upload_directory_view(request):
    """
    Handles fetching directory structure (GET) and
    uploading multiple files (POST).
    """
    target_base_dir_name = 'Raw_Time_Series_Data'
    target_base_full_path = (Path(settings.MEDIA_ROOT) / target_base_dir_name).resolve() # Resolve for robust comparison

    # --- Handle GET Request: Fetch Directory Structure ---
    if request.method == 'GET':
        action = request.GET.get('action') # Check for query parameter

        # --- Action: Get Flat List for Section 3 display ---
        if action == 'list_contents':
            logger.info(f"\nGET request received for FLAT directory contents: {target_base_full_path}\n")
            try:
                if not target_base_full_path.exists(): # Ensure base exists
                    target_base_full_path.mkdir(parents=True, exist_ok=True)
                directory_contents_payload = get_directory_contents_for_event(target_base_full_path, target_base_dir_name)
                return JsonResponse({
                    'status': 'success',
                    'message': f'Retrieved {len(directory_contents_payload)} items.',
                    'directory_contents': directory_contents_payload
                })
            except Exception as e:
                logger.error(f"Error getting flat directory contents: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Could not retrieve directory contents.'}, status=500)

        # --- *** NEW Action: Get Flat List for Download Modal *** ---
        elif action == 'list_downloadable_contents':
            downloadable_dir_name = f'{target_base_dir_name}_CSV_Annotations'
            # This is what the user sees as the top-level folder in the modal tree
            downloadable_root_name_for_path = "Saving_Folder"
            downloadable_scan_path = (target_base_full_path.parent / downloadable_dir_name / downloadable_root_name_for_path).resolve()
            
            logger.info(f"\nGET request received for DOWNLOADABLE contents list: Scan Path='{downloadable_scan_path}', Frontend Root='{downloadable_root_name_for_path}'\n")
            try:
                if not downloadable_scan_path.exists():
                    logger.warning(f"Downloadable directory '{downloadable_scan_path}' not found. Returning empty list.")
                    directory_contents_payload = []
                directory_contents_payload = get_directory_contents_for_event(
                    scan_path=downloadable_scan_path,
                    root_dir_name=downloadable_root_name_for_path # Name shown in frontend paths
                )
                return JsonResponse({
                    'status': 'success',
                    'message': f'Retrieved {len(directory_contents_payload)} downloadable items.',
                    # Use the SAME 'directory_contents' key as the frontend expects this
                    'directory_contents': directory_contents_payload
                })
            except Exception as e:
                logger.error(f"Error getting downloadable directory contents: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Could not retrieve downloadable directory contents.'}, status=500)

        # --- Default GET Action: Get Nested Tree for Modal ---
        else:
            logger.info(f"\nGET request received for MODAL directory tree: {target_base_full_path}\n")
            try:
                if not target_base_full_path.exists():
                    logger.warning(f"Base directory '{target_base_full_path}' not found. Creating it.")
                    target_base_full_path.mkdir(parents=True, exist_ok=True)
                dir_structure = get_directory_structure(target_base_full_path)
                logger.info("Successfully generated directory structure.")
                return JsonResponse({
                    'status': 'success',
                    'directory_structure': dir_structure # Note: Key is different from list action
                })
            except Exception as e:
                logger.error(f"Error getting directory structure for modal: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': 'Could not retrieve directory structure.'}, status=500)

    # --- Handle POST Request: Upload Files ---
    elif request.method == 'POST':
        uploaded_files_count = 0
        skipped_validation_count = 0 # Count files skipped due to validation (size, type, path)
        skipped_exists_count = 0   # Count files skipped because they already exist
        save_errors = []           # List for actual errors during saving
        FILE_UPLOAD_MAX_SIZE = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
        max_files = settings.DATA_UPLOAD_MAX_NUMBER_FILES

        try:
            # Force Django to parse the multipart data now,
            # so if there are too many files it raises immediately:
            _ = request.FILES    # triggers file parsing
            _ = request.POST     # triggers POST parsing

            # --- Get Metadata from POST data ---
            target_path_relative_to_media = request.POST.get('target_path') # e.g., 'Raw_Time_Series_Data/SubFolder'
            keep_root = request.POST.get('keep_root') == 'true' # Convert string to boolean
            is_directory = request.POST.get('is_directory') == 'true' # Convert string to boolean
            intended_paths_json = request.POST.get('intended_paths') # Get the JSON string

            logger.info(f"\nPOST received: Target='{target_path_relative_to_media}', KeepRoot={keep_root}, IsDir={is_directory}\n")

            # --- Validate Target Path ---
            if not target_path_relative_to_media:
                raise ValueError("Missing target_path in POST request.")
            full_target_dir = (Path(settings.MEDIA_ROOT) / target_path_relative_to_media).resolve()
            # Security Check: Ensure target is within the intended base directory
            if not str(full_target_dir).startswith(str(target_base_full_path)):
                logger.error(f"Invalid target path attempted: '{target_path_relative_to_media}' resolved to '{full_target_dir}' which is outside base '{target_base_full_path}'")
                raise PermissionDenied("Invalid target directory specified.")

            # --- Get Uploaded Files and Intended Paths ---
            uploaded_files = request.FILES.getlist('files[]')
            if not uploaded_files:
                return JsonResponse({'status': 'error', 'message': 'No files were uploaded.'}, status=400)
            logger.info(f"Processing {len(uploaded_files)} file(s) for upload.")

            # Parse the intended paths
            if not intended_paths_json:
                raise ValueError("Missing intended_paths in POST request.")
            try:
                intended_paths = json.loads(intended_paths_json)
                logger.debug(f"Parsed intended paths: {intended_paths}")
            except json.JSONDecodeError:
                raise ValueError("Invalid format for intended_paths.")
            
            # --- Check Consistency ---
            if len(uploaded_files) != len(intended_paths):
                logger.error(f"Mismatch between file count ({len(uploaded_files)}) and path count ({len(intended_paths)})")
                raise ValueError("File count and path count mismatch.")

            logger.info(f"Processing {len(uploaded_files)} file(s) for upload.")

            # --- Process Each File using Index ---
            for i, uploaded_file in enumerate(uploaded_files):
                # This name is webkitRelativePath (for dir) or filename (for files)
                original_intended_path_str = intended_paths[i]
                actual_received_filename = uploaded_file.name
                logger.debug(f"  [File {i}] Processing intended path: '{original_intended_path_str}' (received filename: '{actual_received_filename}')")

                # Basic cleaning and security check (prevent escaping target dir)
                # os.path.normpath is good, but Path object handles this better generally
                try:
                    # Treat the path received as relative components
                    path_components = Path(original_intended_path_str).parts
                    # Disallow absolute paths or directory traversal
                    if any(part == '..' or Path(part).is_absolute() for part in path_components):
                         raise ValueError("Invalid characters or path traversal attempt in intended path.")
                    # Reconstruct cleaned relative path
                    clean_relative_path = Path(*path_components) # e.g., Path('OriginalRoot/Sub/file.csv') or Path('file.csv')
                except ValueError as e:
                    logger.warning(f"Skipping invalid path: '{original_intended_path_str}'. Reason: {e}")
                    save_errors.append(f"Skipped invalid path: {original_intended_path_str}")
                    skipped_validation_count += 1
                    continue

                # --- File Type and Size Validation (using uploaded_file object) ---
                # Type check based on the cleaned path's extension
                if not str(clean_relative_path).lower().endswith('.csv'):
                    logger.warning(f"Skipping non-CSV file: '{original_intended_path_str}'")
                    save_errors.append(f"Non-CSV Skipped: {original_intended_path_str}")
                    skipped_validation_count += 1
                    continue
                # Size check using the actual file object
                size_ = uploaded_file.size
                if size_ > FILE_UPLOAD_MAX_SIZE:
                    logger.warning(f"Skipping large file: '{original_intended_path_str}' (size: {size_} bytes)")
                    save_errors.append(f"Skipped large file (> {FILE_UPLOAD_MAX_SIZE // 1024 // 1024}MB): {original_intended_path_str}")
                    skipped_validation_count += 1
                    continue

                # --- Determine Final Path Component based on Options *** USING INTENDED PATH (relative to MEDIA_ROOT) *** ---
                if is_directory:
                    if keep_root:
                        final_path_component = clean_relative_path # Path('OriginalRoot/Sub/file.csv')
                        logger.debug(f"    KeepRoot=True: Using full relative path: {final_path_component}")
                    else:
                        # Remove the first part (original root directory) if it exists
                        if len(clean_relative_path.parts) > 1:
                            final_path_component = Path(*clean_relative_path.parts[1:]) # Path('Sub/file.csv')
                            logger.debug(f"    KeepRoot=False: Using inner path: {final_path_component}")
                        else:
                            # Edge case: file was directly in the root folder selected
                            # (e.g., webkitRelativePath was just 'file.csv')
                            final_path_component = clean_relative_path.name # 'file.csv'
                            logger.debug(f"    KeepRoot=False (root only): Using filename: {final_path_component}")
                else: # Individual file upload
                    final_path_component = clean_relative_path.name # 'file.csv'
                    logger.debug(f"    File Upload: Using filename: {final_path_component}")

                # Combine the validated target path with the final component
                # target_path_relative_to_media is like 'Raw_Time_Series_Data/TargetFolder'
                final_save_path_str = str(Path(target_path_relative_to_media) / final_path_component)
                logger.debug(f"    Checking existence for: '{final_save_path_str}'")

                # --- *** CHECK IF FILE EXISTS *** ---
                if default_storage.exists(final_save_path_str):
                    logger.info(f"    Skipped (already exists): '{final_save_path_str}'")
                    skipped_exists_count += 1
                    continue # Skip to the next file

                # --- Save the File ---
                logger.debug(f"    Attempting to save to (relative to MEDIA_ROOT): '{final_save_path_str}'")
                try:
                    # Use default_storage.save with the string path relative to MEDIA_ROOT & actual uploaded_file object
                    saved_path = default_storage.save(final_save_path_str, uploaded_file)
                    logger.info(f"Successfully saved '{original_intended_path_str}' to MEDIA_ROOT relative path: '{saved_path}'")
                    uploaded_files_count += 1
                except Exception as save_error:
                    logger.error(f"Error saving file '{original_intended_path_str}' to '{final_save_path_str}': {save_error}", exc_info=True)
                    save_errors.append(f"Save Error ({original_intended_path_str}): {save_error}")
                    # Don't increment skipped_files_count here, it's an error during save

            # --- Prepare Response ---
            total_processed = len(uploaded_files)
            final_message_parts = []
            if uploaded_files_count > 0:
                final_message_parts.append(f"Successfully uploaded {uploaded_files_count}")
            if skipped_exists_count > 0:
                final_message_parts.append(f"skipped {skipped_exists_count} (already exist)")
            if skipped_validation_count > 0:
                final_message_parts.append(f"skipped {skipped_validation_count} (validation failed)")
            if save_errors:
                final_message_parts.append(f"{len(save_errors)} save error(s)")

            if uploaded_files_count == total_processed : # All successful
                status = 'success'
                http_status = 200
                message = f"Successfully uploaded all {uploaded_files_count} file(s)."
            elif uploaded_files_count > 0 or skipped_exists_count > 0: # Some success or some just skipped harmlessly
                status = 'partial_success'
                http_status = 207 # Multi-Status
                message = f"Upload processed. " + ", ".join(final_message_parts) + "."
            else: # Only validation skips or save errors
                status = 'error'
                http_status = 400 # Or 500 if save_errors occurred
                if save_errors and not skipped_validation_count: 
                    http_status = 500
                message = "Upload failed. " + ", ".join(final_message_parts) + "."


            # *** ADD DIRECTORY CONTENTS TO RESPONSE ON SUCCESS/PARTIAL SUCCESS ***
            directory_contents_payload = []
            if status in ['success', 'partial_success']:
                try:
                    # Scan the entire base directory after changes are made
                    directory_contents_payload = get_directory_contents_for_event(target_base_full_path, target_base_dir_name)
                except Exception as scan_error:
                    logger.error(f"Error scanning directory contents after upload: {scan_error}", exc_info=True)
                    # Decide if this should change the overall status? Maybe add to errors list.
                    save_errors.append(f"Error retrieving directory contents after upload: {scan_error}")
                    # Optionally change status back to error or keep partial_success? Handle later if need be.
                    # status = 'error'
                    # http_status = 500

            # --- Prepare FINAL Response Data ---
            response_data = {
                'status': status,
                'message': message,
                'uploaded_count': uploaded_files_count,
                'skipped_validation_count': skipped_validation_count,
                'skipped_exists_count': skipped_exists_count,
                'save_errors': save_errors, # List of specific errors/skipped validation messages
                'directory_contents': directory_contents_payload # Add the new payload
            }
            return JsonResponse(response_data, status=http_status)

        except TooManyFilesSent:
            # catch the exception and return a clear JSON error
            return JsonResponse({
                'status': 'error',
                'message': (
                    f'Too many files uploaded. '
                    f'Maximum allowed is {max_files} files per request.'
                )
            }, status=400)
        # Catch specific validation/permission errors
        except (ValueError, PermissionDenied) as e:
             logger.error(f"Upload validation error: {e}", exc_info=True)
             return JsonResponse({'status': 'error', 'message': str(e)}, status=400) # Bad Request or 403 Forbidden
        # Catch general errors
        except Exception as e:
            logger.error(f"Unexpected error during POST directory upload: {e}", exc_info=True)
            return JsonResponse({'status': 'error', 'message': 'An unexpected server error occurred during upload.'}, status=500)

@login_required
@require_POST # This view only accepts POST requests
def download_selected_files_view(request):
    """
    Handles POST requests to download selected files as a zip archive using
    a temporary file on disk for robustness with large files.
    Expects a JSON body like: {"paths": ["Saving_Folder/file1.csv", "Saving_Folder/subdir/file2.csv"]}
    """
    temp_zip_path = None # Initialize path variable for cleanup
    try:
        # 1. --- Parse and Validate Request ---
        try:
            data = json.loads(request.body)
            requested_paths = data.get('paths', [])
            if not isinstance(requested_paths, list):
                logger.error("Invalid 'paths' format received.")
                return JsonResponse({'status': 'error', 'message': 'Invalid request format: paths must be a list.'}, status=400)
            if not requested_paths:
                logger.warning("Download request with no paths.")
                return JsonResponse({'status': 'error', 'message': 'No files selected for download.'}, status=400)
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON body.")
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON format.'}, status=400)

        # 2. --- Security Setup & Path Validation ---
        target_base_dir_name = 'Raw_Time_Series_Data'
        downloadable_dir_name = f'{target_base_dir_name}_CSV_Annotations'
        allowed_download_base_path = (Path(settings.MEDIA_ROOT) / downloadable_dir_name).resolve()
        frontend_path_prefix = "Saving_Folder/"
        logger.info(f"Download request for {len(requested_paths)} paths. Allowed base: {allowed_download_base_path}")

        validated_files_to_zip = [] # List of tuples: (absolute_path_on_server, path_inside_zip)
        for req_path in requested_paths:
            # ...(same path validation logic as before)...
            if not isinstance(req_path, str) or not req_path.startswith(frontend_path_prefix):
                logger.warning(f"Skipping invalid path: {req_path}")
                continue
            # relative_path_str = req_path 
            if not req_path:
                logger.warning(f"Skipping empty relative path: {req_path}")
                continue
            potential_abs_path = (allowed_download_base_path / req_path).resolve()
            try:
                is_safe = potential_abs_path.is_relative_to(allowed_download_base_path)
            except AttributeError:
                is_safe = str(potential_abs_path).startswith(str(allowed_download_base_path))

            if is_safe and potential_abs_path.is_file():
                path_inside_zip = req_path
                validated_files_to_zip.append((potential_abs_path, path_inside_zip))
            else:
                logger.warning(f"Skipping unsafe/non-existent path: {req_path} -> {potential_abs_path}")

        if not validated_files_to_zip:
            logger.error("No valid files found after validation.")
            return JsonResponse({'status': 'error', 'message': 'No valid files selected or found for download.'}, status=404) # Use 404

        # 3. --- Create Temporary Zip File on Disk ---
        # Create a named temporary file. delete=False prevents auto-delete on close,
        # allowing us to pass it to FileResponse. We will delete it manually in finally.

        media_root = Path(settings.MEDIA_ROOT).resolve() # Resolve MEDIA_ROOT once

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False, dir=media_root) as temp_zip_file:
            temp_zip_path = temp_zip_file.name # Store the path for cleanup
            logger.info(f"Creating temporary zip file at: {temp_zip_path}")

            # Write to the zip file using the temporary file's path
            with zipfile.ZipFile(temp_zip_file, 'w', zipfile.ZIP_DEFLATED) as zip_archive:
                for abs_path, path_in_zip in validated_files_to_zip:
                    try:
                        zip_archive.write(abs_path, arcname=path_in_zip)
                        logger.debug(f"Added to zip: {abs_path} as {path_in_zip}")
                    except FileNotFoundError:
                        logger.error(f"File not found during zipping (race condition?): {abs_path}")
                        # Decide how to handle: skip, or fail the whole download?
                        # For now, we'll log and continue, the zip will be missing this file.
                    except Exception as zip_err:
                         logger.error(f"Error adding file {abs_path} to zip: {zip_err}", exc_info=True)
                         # Depending on severity, you might want to raise or return an error here

        # 4. --- Prepare and Return FileResponse ---
        # Create an instance of our generator, passing the path
        streaming_content = file_iterator(temp_zip_path)

        response = FileResponse(
            streaming_content, # Pass the generator here
            content_type='application/zip',
            as_attachment=True,
            # filename='downloaded_annotations.zip'  # Assign the correct filename string
        )
        # --- *** MANUALLY set the entire Content-Disposition header *** ---
        response['Content-Disposition'] = 'attachment; filename="downloaded_annotations.zip"'
        # Still expose the header for JS access
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        logger.info(f"Prepared FileResponse with generator for {temp_zip_path}")
        # The view returns, Django iterates the generator, and the generator's finally block cleans up.
        return response

    except Exception as e:
        # Catch unexpected errors *before* starting the response/generator
        logger.exception(f"Unexpected error during download processing: {e}")
        # *** Attempt cleanup if temp_zip_path was created before the error ***
        if temp_zip_path and os.path.exists(temp_zip_path):
             logger.warning(f"Attempting cleanup for {temp_zip_path} due to unexpected error.")
             try:
                 os.remove(temp_zip_path)
                 logger.info(f"Cleaned up {temp_zip_path} after unexpected error.")
             except OSError as clean_err:
                 logger.error(f"Error cleaning up {temp_zip_path} after unexpected error: {clean_err}")
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred during download.'}, status=500)

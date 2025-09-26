#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for the database to be ready (optional but recommended)
# Requires netcat (nc) to be installed in the container.
# If you need this, add 'netcat-openbsd' to the apt-get install list in Dockerfile
# echo "Waiting for postgres..."
# while ! nc -z $DB_HOST $DB_PORT; do
#   sleep 0.1
# done
# echo "PostgreSQL started"

# Define paths
DEFAULT_FILES_SRC="/default_media_files_in_image/"
MEDIA_DEST="/app/media/"
# Use a simple marker file to check if initialization has run
INIT_MARKER_FILE="${MEDIA_DEST}.initialized_by_entrypoint"

# Check if the destination exists and if the marker file IS NOT present
if [ -d "$MEDIA_DEST" ] && [ ! -f "$INIT_MARKER_FILE" ]; then
  echo "First run detected or marker missing. Copying default media files..."
  # Copy contents, handle potential errors, ensure destination exists
  mkdir -p "$MEDIA_DEST"
  # Use cp -n to avoid overwriting existing files if any somehow exist
  # Use cp -a to preserve attributes if needed (like permissions, timestamps)
  cp -r -n ${DEFAULT_FILES_SRC}* "$MEDIA_DEST"
  echo "Default media files copied."
  # Create the marker file to prevent copying again
  touch "$INIT_MARKER_FILE"
else
  echo "Media directory already initialized or destination doesn't exist yet (should be created by volume mount)."
fi

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# The "$@" executes the command passed as arguments to the script (the CMD from Dockerfile)
exec "$@"

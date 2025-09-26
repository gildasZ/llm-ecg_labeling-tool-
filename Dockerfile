# Use an official Python runtime based on Debian Slim
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
# - postgresql-client for psycopg2
# - build-essential for compiling C extensions if needed by some packages
# - libpq-dev is needed for building psycopg2 from source
# - python3-tk for the tkinter GUI library dependency
# - Use apt-get clean instead of purge for caches
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       postgresql-client \
       python3-tk \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Copy entrypoint script
COPY ./entrypoint.sh /app/entrypoint.sh
# Make script executable
# Run this in terminal (Git Bash, WSL, Linux, macOS): `RUN chmod +x entrypoint.sh` before building.
RUN chmod +x /app/entrypoint.sh

# Copy project code into the container
COPY . /app/

# Collect static files
# This will collect files into the directory specified by STATIC_ROOT in settings.py
# Ensure STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_collected') is uncommented
# /app/staticfiles_collected inside the container
RUN python manage.py collectstatic --noinput

# Expose the port the app runs on (Daphne default is 8000)
EXPOSE 8000

# Copy default media files into a temporary location in the image
COPY ./default_media_files /default_media_files_in_image/

# Specify the entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command to run when the container starts (passed to entrypoint.sh)
# Use Daphne as specified in INSTALLED_APPS and suitable for Channels
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "label_V04.asgi:application"]

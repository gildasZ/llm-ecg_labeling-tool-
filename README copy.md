# Custom_Labeling-Tool (Dockerized)

## Description
This ongoing project is a custom labeling tool based on Django-Plotly-Dash, specifically designed for labeling ECG waveforms. It allows users to annotate ECG waveforms easily through a web-based interface, now packaged with Docker for easy setup and deployment.

## Setup and Running with Docker

This project uses Docker and Docker Compose to create a consistent development environment and simplify setup. You **do not** need to install Python, Redis, or PostgreSQL manually on your system.

### Prerequisites
*   **Docker:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Windows/Mac) or Docker Engine + Docker Compose (for Linux). Ensure Docker is running.
*   **Git:** To clone the repository.

### Setup Steps

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <your-repository-directory> # e.g., cd Custom_Labeling-Tool
    ```

2.  **Create `.env` File:**
    This file stores environment variables for local configuration and secrets. It is **not** committed to Git.
    *   Copy the example file:
        ```bash
        cp .env.example .env
        ```
    *   **Edit the `.env` file:** Review the variables inside. You will need to at least:
        *   Set a unique `SECRET_KEY` (you can generate one easily, e.g., using an online generator or Django's `get_random_secret_key()` function).
        *   Review other variables like `DEBUG` (should be `1` for development), database credentials, etc. The defaults provided in `.env.example` are likely fine for initial local running.

3.  **Build the Docker Image (First time or if Dockerfile/requirements change):**
    This command builds the custom Docker image for the web application based on the `Dockerfile`. It might take some time initially as it downloads base images and installs Python packages. Subsequent builds will be much faster due to caching.
    ```bash
    docker-compose build
    ```
    *(Note: You can also use the newer syntax `docker compose build`)*

4.  **Run the Application Stack:**
    This command starts all the services defined in `docker-compose.yml` (web application, database, Redis) in the foreground.
    ```bash
    docker-compose up
    ```
    *(Note: You can also use the newer syntax `docker compose up`)*

    You will see logs from all the containers:
    *   The database (`db`) initializing.
    *   Redis (`redis`) starting.
    *   The web application (`web`) running migrations (via `entrypoint.sh`) and starting the ASGI server (Uvicorn or Daphne).
    *   If you configured the entrypoint script to copy default media files, you might see a message indicating this during the first run.

5.  **Access the WebApp:**
    Once the services are running (look for a line indicating the server is listening on port 8000 or similar), open your web browser and navigate to:
    [http://localhost:8000/](http://localhost:8000/)
    *(Or `http://localhost:8001/` if you configured this instance to use port 8001)*

### Stopping the Application

*   Press `Ctrl+C` in the terminal where `docker-compose up` is running.
*   To stop and remove the containers entirely (optional cleanup):
    ```bash
    docker-compose down
    ```
    *(Note: Use `docker-compose down -v` to also remove the data volumes like the database and media files - use with caution!)*

### Development Workflow Notes
*   **Volume Mount:** The `web` service uses a volume mount (`.:/app`) to map your project directory into the container.
*   **Template/Static File Changes (.html, .css, .js):** Save the file on your host machine and simply **refresh your browser**. The changes should appear instantly.
*   **Python Code Changes (.py):**
    *   If using the `uvicorn --reload` command (recommended for development, check `docker-compose.yml`), simply save the `.py` file. Uvicorn will detect the change, restart the server automatically (you'll see logs in the terminal), and you can then **refresh your browser**.
    *   If using the `daphne` command, you need to manually restart the web service after saving Python files: `docker-compose restart web`.

## Usage

*(This section assumes the application functionality is the same and that necessary default data/files are available)*

### Prepare Data:
*   Ensure the ECG files you want to label are available within the application's media directory.
*   *(If using the entrypoint script method for defaults):* On the first run (`docker-compose up`), default files from the `default_media_files` project folder should have been copied into the running application's media storage.
*   *(If needing manual copying):* You can copy files into the running container's media volume using `docker cp`. For example, to copy a local folder `My_ECG_Data` into the app:
    ```bash
    # Make sure containers are running (e.g., docker-compose up -d)
    docker cp ./My_ECG_Data/. labelv03_web:/app/media/
    ```

### Using the Tool:
*   Navigate to the main page ([http://localhost:8000/](http://localhost:8000/)).
*   *(Adjust based on your UI)* Select the directory or file containing the ECG data you copied or that was provided by default.
*   Use the dropdown menu to select an ECG lead.
*   The waveform corresponding to the selected lead will be displayed.
*   Click on the waveform where you want to start the annotation, and click again where it ends.
*   An input field will appear. Type in your annotation description.
*   Submit the annotation by clicking 'Submit' or pressing 'Enter'.
*   Your annotation will be displayed below the waveform.

## Contributing
Feel free to fork this project and contribute by submitting a pull request. I appreciate your input!

## License
This project is licensed under the MIT License - see the LICENSE.md file for details.

# 🛠️ Custom_Labeling-Tool with Auto-Labeller

## 📊 Description
This project is a custom time-series labeling tool built using Django, Plotly, and Dash. Originally designed for automated ECG waveform annotation, this version uses financial trading data as a substitute due to the lack of labeled ECG datasets. It serves as a complete **Proof of Concept**, demonstrating the core functionalities of interactive, multi-feature time-series labeling via a web interface.

Future iterations may incorporate LLM-guided rule-based annotation, enabling interactive human-AI teaching workflows for real-time signal interpretation and continual learning. 🧠✨

## ✨ Why This Work Matters:
Time-series labeling is a foundational step in building robust AI models for domains like healthcare ❤️‍🩹 and finance 💰. However, creating large, accurately labeled datasets is often a significant bottleneck, requiring manual effort that is time-consuming and error-prone. This project explores a scalable solution by prototyping a **general-purpose, web-based labeling tool**.

By validating the system and its core interactive labeling features on financial data, we establish a flexible framework that can later be adapted for critical applications like ECG annotation—paving the way for automated, human-guided signal labeling across high-impact fields. 📈

## 🔧 Installation

To get the application running using Docker, follow these steps:

### ✅ Prerequisites
Make sure you have the following installed on your machine:

1.  **Docker:** [Get Docker](https://docs.docker.com/get-docker/)
2.  **Docker Compose:** (Usually comes bundled with Docker Desktop on Windows/macOS. For Linux, follow the instructions specific to your distribution or the Docker documentation). [Install Docker Compose](https://docs.docker.com/compose/install/)

### ⚙️ Steps

1.  **⬇️ Clone the Repository:**
    Clone the project repository:
    ```bash
    git clone https://github.com/gildasZ/automated-time-series-labeler.git
    # Navigate into the project directory
    cd automated-time-series-labeler
    ```

2.  **📄 Set up Environment Variables:**
    The project uses environment variables for configuration (database credentials, Django settings, etc.). A template file `.env-Copy` is provided in the repository.

    Copy this template file to a new file named `.env` in the root directory of the project (the same directory as `docker-compose.yml`):
    ```bash
    cp .env-Copy .env
    ```

    Then, **open and edit the newly created `.env` file** to set your specific configurations. **Crucially, replace placeholder values** like the `SECRET_KEY`, `POSTGRES_PASSWORD`, and `DB_PASSWORD` with your own secure, unique values.

    Here is the content of the `.env-Copy` template for your reference while editing:

    ```env
    # .env-Copy content (copy this to .env and edit)

    # Django Settings
    SECRET_KEY='Replace_with_your_own_secure_key' # <-- CHANGE THIS! Use a unique, unpredictable key!
    DEBUG=1 # Set to 1 for development, 0 for production
    # DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1 web [::1] # Uncomment and adjust for production
    DJANGO_ALLOWED_HOSTS=* # Use * for development, but restrict this in production!
    DJANGO_CSRF_TRUSTED_ORIGINS='http://localhost:8000 http://127.0.0.1:8000' # Add others separated by space

    # Database Settings
    POSTGRES_DB=db_label_v03 # CHANGE THIS TO YOUR DESIRED DB NAME (e.g., my_labeling_db)
    POSTGRES_USER=postgres   # CHANGE THIS TO YOUR DESIRED DB USER (e.g., labeling_user)
    POSTGRES_PASSWORD='Your_Password' # <-- CHANGE THIS! Use a strong password!

    # These variables are used by Django to connect to the DB service within Docker Compose
    # DB_HOST is the service name defined in docker-compose.yml ('db')
    DB_ENGINE=django.db.backends.postgresql
    DB_NAME=${POSTGRES_DB}
    DB_USER=${POSTGRES_USER}
    DB_PASSWORD=${POSTGRES_PASSWORD}
    DB_HOST=db # The service name of the database container in docker-compose
    DB_PORT=5432 # Default PostgreSQL port

    # Redis Settings
    # REDIS_HOST is the service name defined in docker-compose.yml ('redis')
    REDIS_HOST=redis # The service name of the Redis container in docker-compose
    REDIS_PORT=6379 # Default Redis port
    REDIS_DB=0 # Default Redis DB index
    ```
    **Security Note:** Never commit your `.env` file with actual secrets to version control. The `.gitignore` file should prevent this.

3.  **🏗️ Build the Docker Images:**
    Open your terminal or command prompt and **make sure you are in the root directory of the cloned project** (the directory containing `docker-compose.yml`). Then, run the following command to build the images:
    ```bash
    docker compose build
    ```
    This command reads the `Dockerfile` to build the `web` service image (installing Python dependencies from `Pipfile.lock`/`requirements.txt` and collecting static files) and will also pull the necessary pre-built images for the `db` (PostgreSQL) and `redis` services.

## 🚀 Running the Application

Once the Docker images are built, you can start all the application services defined in `docker-compose.yml`:

1.  ▶️ **Start the Services:**
    Open your terminal or command prompt and **make sure you are still in the root directory of the cloned project**. Then, run:
    ```bash
    docker compose up
    ```
    This command starts the `db`, `redis`, and `web` containers in the foreground, showing their logs. The `entrypoint.sh` script for the `web` service will automatically run database migrations (`python manage.py migrate`) and copy default media files on the first run (or if the marker file is missing), waiting for the database to be healthy before proceeding.

    To run the services in the background (detached mode), add the `-d` flag:
    ```bash
    docker compose up -d
    ```
    You can view logs for detached containers using `docker compose logs`.

2.  🌐 **Access the Application:**
    Once the services are up and running (wait a moment for the database and web service to start and for migrations/setup to complete after you run `docker compose up`), the web application should be available. Open your web browser and navigate to:
    [http://localhost:8000/](http://localhost:8000/)

3.  ⏹️ **Stop the Application:**
    To stop the services, press `Ctrl+C` in the terminal where `docker compose up` is running (if not in detached mode). If running in detached mode, use:
    ```bash
    docker compose down
    ```
    This command stops and removes the containers and the default network created by Docker Compose.

### 💾 Data Persistence
Database data (PostgreSQL) and user-uploaded media files are stored in Docker volumes (`postgres_data`, `redis_data`, and `media_volume`) as defined in `docker-compose.yml`. This ensures your data persists on your host machine even if you stop and restart the containers. If you wish to remove the volumes and delete all associated data when bringing down the services, use:
```bash
docker compose down -v
```

## 🖱️ Usage

After successfully running the application using `docker compose up` and navigating to `http://localhost:8000/` in your browser, you can begin labeling time-series data:

### ⬆️ Loading Data:
- Click on the **"Upload CSV Data!"** button.
- A pop-up window will appear, giving you options to either:
    - **Select Directory:** Upload all CSV files from a chosen folder.
    - **Select Files (Multiple files):** Select specific CSV files to upload.
- Choose your desired method and select the financial trading data files you want to label. The application will process and load the data.

### 📁 Selecting a File to View:
- After loading your data, the application's interface will display a list of the available files (either those you just uploaded or ones previously loaded).
- Click on a file name from this list to select it.
- The application will automatically load and display the time-series data from the selected file in the main plot area.
- If you have worked on this file before, any annotations you previously made will be automatically loaded from the persistent working state and displayed on the plot.

### 📈 Viewing Time-Series Plots:
- The interactive plot for the currently selected file's data will be displayed in the main area.

### 🤖 Using Auto-Labeling (Optional):
- If you have pre-trained models available, you can use the auto-labeling feature:
    - Select a model from the **"Select a Model"** dropdown menu.
    - Click the **"Auto-label"** button. The application will generate initial annotations on the currently viewed time-series plot based on the selected model.
- **Adding New Models:** To add a new pre-trained model (.pth file), click the **"+"** button inside to the "Select a Model" dropdown. Follow the prompts to upload your model file. Ensure your `.pth` file contains a dictionary with the expected format by the application's backend.

### 📝 Adding or Editing Annotations:
- **Manually Adding:** To add a new annotation manually, click on the plot where you want the annotation segment to start, and click again where it ends. An input field will appear below the plot. Type in your annotation description for the segment and click **'Submit'** or press **'Enter'**.
- **Editing Auto-Generated Labels:** You can modify the auto-generated labels. Select the annotation segment(s) through the table of annotations, and click the **'Delete'** button to remove it. You can also manually add new annotations alongside or instead of the auto-generated ones.

### 💾 Saving Your Work:
- As you add or edit annotations, they are automatically saved to a persistent working state in the background. This ensures your progress is not lost, even if the application closes unexpectedly.
- The **"Save"** button saves the annotations for the *currently viewed file* from the persistent working state into a designated "saving directory".
- The **"Save All"** button saves the annotations for *all loaded files* that have unsaved changes from the persistent working state into the "saving directory".
- Clicking "Save" or "Save All" is necessary to make your annotations available for download.

### 📦⬇️ Downloading Labeled Data:
- **Important:** Before initiating a download, ensure you have clicked **"Save All"** to guarantee that all your latest annotations across all files you've worked on are copied to the saving directory and included in the download.
- When you are finished labeling and have clicked "Save All", click the **"Download Outputs"** button.
- A pop-up will appear, allowing you to multi-select the labeled data files available in the saving directory that you wish to download as a ZIP archive.
- After selecting the files, click the download confirmation button, and a zip file containing your selected labeled data will be downloaded locally.

## 🔒 License
This project is patented. The code contained within this repository is not provided under a free or open-source license.

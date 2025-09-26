# Code State for README Update

---

## File: `Dockerfile`

```dockerfile
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

```

---

## File: `docker-compose.yml`

```yaml
version: '3.9' # Use a more recent version compatible with your Docker install

services:
  # PostgreSQL Database Service
  db:
    image: postgres:15-alpine # Use a specific version, alpine is smaller
    container_name: labelv03_db
    volumes:
      - postgres_data:/var/lib/postgresql/data/ # Persist data
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-db_label_v04} # Use env var with default
      POSTGRES_USER: ${POSTGRES_USER:-postgres} # Use env var with default
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD?Variable not set} # Require from .env
    # ports:
    #   # Expose port 5432 locally if you need direct access for debugging (optional)
    #   - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d db_label_v04"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis Service
  redis:
    image: redis:alpine # Use alpine for smaller size
    container_name: labelv03_redis
    volumes:
      - redis_data:/data # Optional persistence for Redis data
    # ports:
    #   # Expose port 6379 locally if needed for debugging (optional)
    #   - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Django Web Application Service
  web:
    build: . # Build from Dockerfile in the current directory
    container_name: labelv03_web
    # The command is now defined in the Dockerfile's CMD via ENTRYPOINT
    # command: daphne -b 0.0.0.0 -p 8000 label_V04.asgi:application
    env_file:
        - .env # Load variables from .env file
    volumes:
      # Mount code for development (reflects changes without rebuild)
      # Remove this line for production to use code baked into the image
      - .:/app
      # Mount volume for user-uploaded media files
      # Ensure '/app/media' matches MEDIA_ROOT in settings.py
      - media_volume:/app/media
      # Static files are collected into the image by the Dockerfile.
      # WhiteNoise will serve them from /app/staticfiles_collected inside the container.
      # No separate static volume mount needed here for the web service itself.
    ports:
      - "8000:8000" # Map host port 8000 to container port 8000
    environment:
      # Django Settings
      - DJANGO_SETTINGS_MODULE=label_V04.settings
      - SECRET_KEY=your_development_secret_key # <-- CHANGE THIS! Use .env file ideally
      - DEBUG=1 # Set to 0 in production
      - DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1 web [::1] # Add 'web' service name

      # The following variables are now expected to be loaded from the .env file:
      # - SECRET_KEY
      # - DEBUG
      # - DJANGO_ALLOWED_HOSTS
      # - DJANGO_CSRF_TRUSTED_ORIGINS (if you use it in settings.py)
      # - DB_ENGINE (if not using DATABASE_URL)
      # - DB_NAME   (if not using DATABASE_URL)
      # - DB_USER   (if not using DATABASE_URL)
      # - DB_PASSWORD (if not using DATABASE_URL)
      # - DB_HOST   (if not using DATABASE_URL)
      # - DB_PORT   (if not using DATABASE_URL)
      # - REDIS_HOST
      # - REDIS_PORT
      # - REDIS_DB

    depends_on:
      # Wait for db and redis to be healthy before starting web
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

# Docker Volumes for Data Persistence
volumes:
  postgres_data:
  redis_data:
  media_volume:

```

---

## File: `entrypoint.sh`

```bash
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

```

---

## File: `Pipfile`

```toml
[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[packages]
absl-py = "==2.1.0"
aiofiles = "==23.2.1"
anyio = "==4.6.2.post1"
asgiref = "==3.8.1"
asttokens = "==3.0.0"
astunparse = "==1.6.3"
attrs = "==23.2.0"
autobahn = "==23.6.2"
automat = "==22.10.0"
backtrader = "==1.9.78.123"
bleach = "==6.2.0"
blinker = "==1.7.0"
bokeh = "==3.6.1"
certifi = "==2024.2.2"
cffi = "==1.16.0"
channels = "==4.1.0"
channels-redis = "==4.2.0"
charset-normalizer = "==3.3.2"
click = "==8.1.7"
cloudpickle = "==3.1.0"
colorama = "==0.4.6"
colorcet = "==3.1.0"
comm = "==0.2.2"
constantly = "==23.10.4"
contourpy = "==1.3.1"
cryptography = "==42.0.5"
cycler = "==0.12.1"
daphne = "==4.1.2"
dash = "==2.9.3"
dash-bootstrap-components = "==1.6.0"
dash-core-components = "==2.0.0"
dash-html-components = "==2.0.0"
dash-table = "==5.0.0"
dask = "==2024.11.2"
datashader = "==0.16.3"
debugpy = "==1.8.9"
decorator = "==5.1.1"
django = "==5.0.4"
django-debug-toolbar = "==4.3.0"
django-plotly-dash = "==2.3.1"
django-redis = "==5.4.0"
docutils = "==0.21.2"
dpd-static-support = "==0.0.5"
dpd-components = "==0.1.0"
et-xmlfile = "==2.0.0"
eventkit = "==1.0.3"
executing = "==2.1.0"
filelock = "==3.16.1"
flask = "==3.0.3"
flatbuffers = "==24.3.25"
fonttools = "==4.55.0"
fsspec = "==2024.10.0"
gast = "==0.6.0"
google-pasta = "==0.2.0"
grpcio = "==1.68.0"
h11 = "==0.14.0"
h5py = "==3.12.1"
holoviews = "==1.20.0"
httpcore = "==1.0.7"
httpx = "==0.28.0"
hyperlink = "==21.0.0"
ib-insync = "==0.9.86"
idna = "==3.7"
importlib-metadata = "==7.1.0"
incremental = "==22.10.0"
ipykernel = "==6.29.5"
ipython = "==8.30.0"
itsdangerous = "==2.2.0"
jedi = "==0.19.2"
jinja2 = "==3.1.3"
jupyter-client = "==8.6.3"
jupyter-core = "==5.7.2"
kiwisolver = "==1.4.7"
libclang = "==18.1.1"
linkify-it-py = "==2.0.3"
llvmlite = "==0.43.0"
locket = "==1.0.0"
lxml = "==5.2.1"
markdown = "==3.7"
markdown-it-py = "==3.0.0"
markupsafe = "==2.1.5"
matplotlib = "==3.9.3"
matplotlib-inline = "==0.1.7"
mdit-py-plugins = "==0.4.2"
mdurl = "==0.1.2"
ml-dtypes = "==0.4.1"
mpl-interactions = "==0.24.2"
mpmath = "==1.3.0"
msgpack = "==1.0.8"
multipledispatch = "==1.0.0"
namex = "==0.0.8"
nest-asyncio = "==1.6.0"
networkx = "==3.4.2"
numba = "==0.60.0"
numpy = "==2.0.2"
openpyxl = "==3.1.5"
opt-einsum = "==3.4.0"
optree = "==0.13.1"
packaging = "==24.0"
pandas = "==2.2.3"
panel = "==1.5.4"
param = "==2.1.1"
parso = "==0.8.4"
partd = "==1.4.2"
pillow = "==11.0.0"
platformdirs = "==4.3.6"
plotly = "==5.20.0"
polygon = "==1.2.5"
prompt-toolkit = "==3.0.48"
protobuf = "==5.29.0"
psutil = "==6.1.0"
psycopg2 = "==2.9.9"
pure-eval = "==0.2.3"
pyasn1 = "==0.6.0"
pyasn1-modules = "==0.4.0"
pycparser = "==2.22"
pyct = "==0.5.0"
pygments = "==2.18.0"
pyopenssl = "==24.1.0"
pyparsing = "==3.2.0"
python-dateutil = "==2.9.0.post0"
pytz = "==2024.2"
pyviz-comms = "==3.0.3"
pywin32 = "==308"
pyyaml = "==6.0.2"
pyzmq = "==26.2.0"
redis = "==5.0.4"
requests = "==2.31.0"
retrying = "==1.3.4"
rich = "==13.9.4"
scipy = "==1.14.1"
service-identity = "==24.1.0"
six = "==1.16.0"
sniffio = "==1.3.1"
sqlparse = "==0.5.0"
stack-data = "==0.6.3"
statistics = "==1.0.3.5"
sympy = "==1.13.1"
ta = "==0.11.0"
tenacity = "==8.2.3"
termcolor = "==2.5.0"
toolz = "==1.0.0"
torchaudio = "*"
torchvision = "*"
tornado = "==6.4.2"
tqdm = "==4.67.1"
traitlets = "==5.14.3"
twisted = "==24.3.0"
twisted-iocpsupport = "==1.0.4"
txaio = "==23.1.1"
typing-extensions = "==4.11.0"
tzdata = "==2024.1"
tzlocal = "==5.2"
uc-micro-py = "==1.0.3"
urllib3 = "==2.2.1"
wcwidth = "==0.2.13"
webencodings = "==0.5.1"
websocket-client = "==1.8.0"
websockets = "==14.1"
werkzeug = "==3.0.2"
whitenoise = "==6.6.0"
wrapt = "==1.17.0"
xarray = "==2024.11.0"
xyzservices = "==2024.9.0"
zipp = "==3.18.1"
"zope.interface" = "==6.3"
nbformat = "*"
torch = "*"
chardet = "*"
dj-database-url = "*"

[dev-packages]

[requires]
python_version = "3.12"

```

---

## File: `Pipfile.lock`

```json
{
    "_meta": {
        "hash": {
            "sha256": "1b501aa77d90105af3fbce9724bf5703c25d9c250988eff90e561c0733201e8d"
        },
        "pipfile-spec": 6,
        "requires": {
            "python_version": "3.12"
        },
        "sources": [
            {
                "name": "pypi",
                "url": "https://pypi.org/simple",
                "verify_ssl": true
            }
        ]
    },
    "default": {
        "absl-py": {
            "hashes": [
                "sha256:526a04eadab8b4ee719ce68f204172ead1027549089702d99b9059f129ff1308",
                "sha256:7820790efbb316739cde8b4e19357243fc3608a152024288513dd968d7d959ff"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==2.1.0"
        },
        "aiofiles": {
            "hashes": [
                "sha256:19297512c647d4b27a2cf7c34caa7e405c0d60b5560618a29a9fe027b18b0107",
                "sha256:84ec2218d8419404abcb9f0c02df3f34c6e0a68ed41072acfb1cef5cbc29051a"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==23.2.1"
        },
        "anyio": {
            "hashes": [
                "sha256:4c8bc31ccdb51c7f7bd251f51c609e038d63e34219b44aa86e47576389880b4c",
                "sha256:6d170c36fba3bdd840c73d3868c1e777e33676a69c3a72cf0a0d5d6d8009b61d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==4.6.2.post1"
        },
        "asgiref": {
            "hashes": [
                "sha256:3e1e3ecc849832fe52ccf2cb6686b7a55f82bb1d6aee72a58826471390335e47",
                "sha256:c343bd80a0bec947a9860adb4c432ffa7db769836c64238fc34bdc3fec84d590"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.8.1"
        },
        "asttokens": {
            "hashes": [
                "sha256:0dcd8baa8d62b0c1d118b399b2ddba3c4aff271d0d7a9e0d4c1681c79035bbc7",
                "sha256:e3078351a059199dd5138cb1c706e6430c05eff2ff136af5eb4790f9d28932e2"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.0.0"
        },
        "astunparse": {
            "hashes": [
                "sha256:5ad93a8456f0d084c3456d059fd9a92cce667963232cbf763eac3bc5b7940872",
                "sha256:c2652417f2c8b5bb325c885ae329bdf3f86424075c4fd1a128674bc6fba4b8e8"
            ],
            "index": "pypi",
            "version": "==1.6.3"
        },
        "attrs": {
            "hashes": [
                "sha256:935dc3b529c262f6cf76e50877d35a4bd3c1de194fd41f47a2b7ae8f19971f30",
                "sha256:99b87a485a5820b23b879f04c2305b44b951b502fd64be915879d77a7e8fc6f1"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==23.2.0"
        },
        "autobahn": {
            "hashes": [
                "sha256:ec9421c52a2103364d1ef0468036e6019ee84f71721e86b36fe19ad6966c1181"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==23.6.2"
        },
        "automat": {
            "hashes": [
                "sha256:c3164f8742b9dc440f3682482d32aaff7bb53f71740dd018533f9de286b64180",
                "sha256:e56beb84edad19dcc11d30e8d9b895f75deeb5ef5e96b84a467066b3b84bb04e"
            ],
            "index": "pypi",
            "version": "==22.10.0"
        },
        "backtrader": {
            "hashes": [
                "sha256:9a07a516b0de9155539a35c56e9404d8711dd7020b3d37b30495e83e1b9d5dfd"
            ],
            "index": "pypi",
            "version": "==1.9.78.123"
        },
        "bleach": {
            "hashes": [
                "sha256:117d9c6097a7c3d22fd578fcd8d35ff1e125df6736f554da4e432fdd63f31e5e",
                "sha256:123e894118b8a599fd80d3ec1a6d4cc7ce4e5882b1317a7e1ba69b56e95f991f"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==6.2.0"
        },
        "blinker": {
            "hashes": [
                "sha256:c3f865d4d54db7abc53758a01601cf343fe55b84c1de4e3fa910e420b438d5b9",
                "sha256:e6820ff6fa4e4d1d8e2747c2283749c3f547e4fee112b98555cdcdae32996182"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.7.0"
        },
        "bokeh": {
            "hashes": [
                "sha256:04d3fb5fac871423f38e4535838164cd90c3d32e707bcb74c8bf991ed28878fc",
                "sha256:6a97271bd4cc5b32c5bc7aa9c1c0dbe0beb0a8da2a22193e57c73f0c88d2075a"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==3.6.1"
        },
        "certifi": {
            "hashes": [
                "sha256:0569859f95fc761b18b45ef421b1290a0f65f147e92a1e5eb3e635f9a5e4e66f",
                "sha256:dc383c07b76109f368f6106eee2b593b04a011ea4d55f652c6ca24a754d1cdd1"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==2024.2.2"
        },
        "cffi": {
            "hashes": [
                "sha256:0c9ef6ff37e974b73c25eecc13952c55bceed9112be2d9d938ded8e856138bcc",
                "sha256:131fd094d1065b19540c3d72594260f118b231090295d8c34e19a7bbcf2e860a",
                "sha256:1b8ebc27c014c59692bb2664c7d13ce7a6e9a629be20e54e7271fa696ff2b417",
                "sha256:2c56b361916f390cd758a57f2e16233eb4f64bcbeee88a4881ea90fca14dc6ab",
                "sha256:2d92b25dbf6cae33f65005baf472d2c245c050b1ce709cc4588cdcdd5495b520",
                "sha256:31d13b0f99e0836b7ff893d37af07366ebc90b678b6664c955b54561fc36ef36",
                "sha256:32c68ef735dbe5857c810328cb2481e24722a59a2003018885514d4c09af9743",
                "sha256:3686dffb02459559c74dd3d81748269ffb0eb027c39a6fc99502de37d501faa8",
                "sha256:582215a0e9adbe0e379761260553ba11c58943e4bbe9c36430c4ca6ac74b15ed",
                "sha256:5b50bf3f55561dac5438f8e70bfcdfd74543fd60df5fa5f62d94e5867deca684",
                "sha256:5bf44d66cdf9e893637896c7faa22298baebcd18d1ddb6d2626a6e39793a1d56",
                "sha256:6602bc8dc6f3a9e02b6c22c4fc1e47aa50f8f8e6d3f78a5e16ac33ef5fefa324",
                "sha256:673739cb539f8cdaa07d92d02efa93c9ccf87e345b9a0b556e3ecc666718468d",
                "sha256:68678abf380b42ce21a5f2abde8efee05c114c2fdb2e9eef2efdb0257fba1235",
                "sha256:68e7c44931cc171c54ccb702482e9fc723192e88d25a0e133edd7aff8fcd1f6e",
                "sha256:6b3d6606d369fc1da4fd8c357d026317fbb9c9b75d36dc16e90e84c26854b088",
                "sha256:748dcd1e3d3d7cd5443ef03ce8685043294ad6bd7c02a38d1bd367cfd968e000",
                "sha256:7651c50c8c5ef7bdb41108b7b8c5a83013bfaa8a935590c5d74627c047a583c7",
                "sha256:7b78010e7b97fef4bee1e896df8a4bbb6712b7f05b7ef630f9d1da00f6444d2e",
                "sha256:7e61e3e4fa664a8588aa25c883eab612a188c725755afff6289454d6362b9673",
                "sha256:80876338e19c951fdfed6198e70bc88f1c9758b94578d5a7c4c91a87af3cf31c",
                "sha256:8895613bcc094d4a1b2dbe179d88d7fb4a15cee43c052e8885783fac397d91fe",
                "sha256:88e2b3c14bdb32e440be531ade29d3c50a1a59cd4e51b1dd8b0865c54ea5d2e2",
                "sha256:8f8e709127c6c77446a8c0a8c8bf3c8ee706a06cd44b1e827c3e6a2ee6b8c098",
                "sha256:9cb4a35b3642fc5c005a6755a5d17c6c8b6bcb6981baf81cea8bfbc8903e8ba8",
                "sha256:9f90389693731ff1f659e55c7d1640e2ec43ff725cc61b04b2f9c6d8d017df6a",
                "sha256:a09582f178759ee8128d9270cd1344154fd473bb77d94ce0aeb2a93ebf0feaf0",
                "sha256:a6a14b17d7e17fa0d207ac08642c8820f84f25ce17a442fd15e27ea18d67c59b",
                "sha256:a72e8961a86d19bdb45851d8f1f08b041ea37d2bd8d4fd19903bc3083d80c896",
                "sha256:abd808f9c129ba2beda4cfc53bde801e5bcf9d6e0f22f095e45327c038bfe68e",
                "sha256:ac0f5edd2360eea2f1daa9e26a41db02dd4b0451b48f7c318e217ee092a213e9",
                "sha256:b29ebffcf550f9da55bec9e02ad430c992a87e5f512cd63388abb76f1036d8d2",
                "sha256:b2ca4e77f9f47c55c194982e10f058db063937845bb2b7a86c84a6cfe0aefa8b",
                "sha256:b7be2d771cdba2942e13215c4e340bfd76398e9227ad10402a8767ab1865d2e6",
                "sha256:b84834d0cf97e7d27dd5b7f3aca7b6e9263c56308ab9dc8aae9784abb774d404",
                "sha256:b86851a328eedc692acf81fb05444bdf1891747c25af7529e39ddafaf68a4f3f",
                "sha256:bcb3ef43e58665bbda2fb198698fcae6776483e0c4a631aa5647806c25e02cc0",
                "sha256:c0f31130ebc2d37cdd8e44605fb5fa7ad59049298b3f745c74fa74c62fbfcfc4",
                "sha256:c6a164aa47843fb1b01e941d385aab7215563bb8816d80ff3a363a9f8448a8dc",
                "sha256:d8a9d3ebe49f084ad71f9269834ceccbf398253c9fac910c4fd7053ff1386936",
                "sha256:db8e577c19c0fda0beb7e0d4e09e0ba74b1e4c092e0e40bfa12fe05b6f6d75ba",
                "sha256:dc9b18bf40cc75f66f40a7379f6a9513244fe33c0e8aa72e2d56b0196a7ef872",
                "sha256:e09f3ff613345df5e8c3667da1d918f9149bd623cd9070c983c013792a9a62eb",
                "sha256:e4108df7fe9b707191e55f33efbcb2d81928e10cea45527879a4749cbe472614",
                "sha256:e6024675e67af929088fda399b2094574609396b1decb609c55fa58b028a32a1",
                "sha256:e70f54f1796669ef691ca07d046cd81a29cb4deb1e5f942003f401c0c4a2695d",
                "sha256:e715596e683d2ce000574bae5d07bd522c781a822866c20495e52520564f0969",
                "sha256:e760191dd42581e023a68b758769e2da259b5d52e3103c6060ddc02c9edb8d7b",
                "sha256:ed86a35631f7bfbb28e108dd96773b9d5a6ce4811cf6ea468bb6a359b256b1e4",
                "sha256:ee07e47c12890ef248766a6e55bd38ebfb2bb8edd4142d56db91b21ea68b7627",
                "sha256:fa3a0128b152627161ce47201262d3140edb5a5c3da88d73a1b790a959126956",
                "sha256:fcc8eb6d5902bb1cf6dc4f187ee3ea80a1eba0a89aba40a5cb20a5087d961357"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.16.0"
        },
        "channels": {
            "hashes": [
                "sha256:a3c4419307f582c3f71d67bfb6eff748ae819c2f360b9b141694d84f242baa48",
                "sha256:e0ed375719f5c1851861f05ed4ce78b0166f9245ca0ecd836cb77d4bb531489d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.1.0"
        },
        "channels-redis": {
            "hashes": [
                "sha256:01c26c4d5d3a203f104bba9e5585c0305a70df390d21792386586068162027fd",
                "sha256:2c5b944a39bd984b72aa8005a3ae11637bf29b5092adeb91c9aad4ab819a8ac4"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.2.0"
        },
        "chardet": {
            "hashes": [
                "sha256:1b3b6ff479a8c414bc3fa2c0852995695c4a026dcd6d0633b2dd092ca39c1cf7",
                "sha256:e1cf59446890a00105fe7b7912492ea04b6e6f06d4b742b2c788469e34c82970"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==5.2.0"
        },
        "charset-normalizer": {
            "hashes": [
                "sha256:06435b539f889b1f6f4ac1758871aae42dc3a8c0e24ac9e60c2384973ad73027",
                "sha256:06a81e93cd441c56a9b65d8e1d043daeb97a3d0856d177d5c90ba85acb3db087",
                "sha256:0a55554a2fa0d408816b3b5cedf0045f4b8e1a6065aec45849de2d6f3f8e9786",
                "sha256:0b2b64d2bb6d3fb9112bafa732def486049e63de9618b5843bcdd081d8144cd8",
                "sha256:10955842570876604d404661fbccbc9c7e684caf432c09c715ec38fbae45ae09",
                "sha256:122c7fa62b130ed55f8f285bfd56d5f4b4a5b503609d181f9ad85e55c89f4185",
                "sha256:1ceae2f17a9c33cb48e3263960dc5fc8005351ee19db217e9b1bb15d28c02574",
                "sha256:1d3193f4a680c64b4b6a9115943538edb896edc190f0b222e73761716519268e",
                "sha256:1f79682fbe303db92bc2b1136016a38a42e835d932bab5b3b1bfcfbf0640e519",
                "sha256:2127566c664442652f024c837091890cb1942c30937add288223dc895793f898",
                "sha256:22afcb9f253dac0696b5a4be4a1c0f8762f8239e21b99680099abd9b2b1b2269",
                "sha256:25baf083bf6f6b341f4121c2f3c548875ee6f5339300e08be3f2b2ba1721cdd3",
                "sha256:2e81c7b9c8979ce92ed306c249d46894776a909505d8f5a4ba55b14206e3222f",
                "sha256:3287761bc4ee9e33561a7e058c72ac0938c4f57fe49a09eae428fd88aafe7bb6",
                "sha256:34d1c8da1e78d2e001f363791c98a272bb734000fcef47a491c1e3b0505657a8",
                "sha256:37e55c8e51c236f95b033f6fb391d7d7970ba5fe7ff453dad675e88cf303377a",
                "sha256:3d47fa203a7bd9c5b6cee4736ee84ca03b8ef23193c0d1ca99b5089f72645c73",
                "sha256:3e4d1f6587322d2788836a99c69062fbb091331ec940e02d12d179c1d53e25fc",
                "sha256:42cb296636fcc8b0644486d15c12376cb9fa75443e00fb25de0b8602e64c1714",
                "sha256:45485e01ff4d3630ec0d9617310448a8702f70e9c01906b0d0118bdf9d124cf2",
                "sha256:4a78b2b446bd7c934f5dcedc588903fb2f5eec172f3d29e52a9096a43722adfc",
                "sha256:4ab2fe47fae9e0f9dee8c04187ce5d09f48eabe611be8259444906793ab7cbce",
                "sha256:4d0d1650369165a14e14e1e47b372cfcb31d6ab44e6e33cb2d4e57265290044d",
                "sha256:549a3a73da901d5bc3ce8d24e0600d1fa85524c10287f6004fbab87672bf3e1e",
                "sha256:55086ee1064215781fff39a1af09518bc9255b50d6333f2e4c74ca09fac6a8f6",
                "sha256:572c3763a264ba47b3cf708a44ce965d98555f618ca42c926a9c1616d8f34269",
                "sha256:573f6eac48f4769d667c4442081b1794f52919e7edada77495aaed9236d13a96",
                "sha256:5b4c145409bef602a690e7cfad0a15a55c13320ff7a3ad7ca59c13bb8ba4d45d",
                "sha256:6463effa3186ea09411d50efc7d85360b38d5f09b870c48e4600f63af490e56a",
                "sha256:65f6f63034100ead094b8744b3b97965785388f308a64cf8d7c34f2f2e5be0c4",
                "sha256:663946639d296df6a2bb2aa51b60a2454ca1cb29835324c640dafb5ff2131a77",
                "sha256:6897af51655e3691ff853668779c7bad41579facacf5fd7253b0133308cf000d",
                "sha256:68d1f8a9e9e37c1223b656399be5d6b448dea850bed7d0f87a8311f1ff3dabb0",
                "sha256:6ac7ffc7ad6d040517be39eb591cac5ff87416c2537df6ba3cba3bae290c0fed",
                "sha256:6b3251890fff30ee142c44144871185dbe13b11bab478a88887a639655be1068",
                "sha256:6c4caeef8fa63d06bd437cd4bdcf3ffefe6738fb1b25951440d80dc7df8c03ac",
                "sha256:6ef1d82a3af9d3eecdba2321dc1b3c238245d890843e040e41e470ffa64c3e25",
                "sha256:753f10e867343b4511128c6ed8c82f7bec3bd026875576dfd88483c5c73b2fd8",
                "sha256:7cd13a2e3ddeed6913a65e66e94b51d80a041145a026c27e6bb76c31a853c6ab",
                "sha256:7ed9e526742851e8d5cc9e6cf41427dfc6068d4f5a3bb03659444b4cabf6bc26",
                "sha256:7f04c839ed0b6b98b1a7501a002144b76c18fb1c1850c8b98d458ac269e26ed2",
                "sha256:802fe99cca7457642125a8a88a084cef28ff0cf9407060f7b93dca5aa25480db",
                "sha256:80402cd6ee291dcb72644d6eac93785fe2c8b9cb30893c1af5b8fdd753b9d40f",
                "sha256:8465322196c8b4d7ab6d1e049e4c5cb460d0394da4a27d23cc242fbf0034b6b5",
                "sha256:86216b5cee4b06df986d214f664305142d9c76df9b6512be2738aa72a2048f99",
                "sha256:87d1351268731db79e0f8e745d92493ee2841c974128ef629dc518b937d9194c",
                "sha256:8bdb58ff7ba23002a4c5808d608e4e6c687175724f54a5dade5fa8c67b604e4d",
                "sha256:8c622a5fe39a48f78944a87d4fb8a53ee07344641b0562c540d840748571b811",
                "sha256:8d756e44e94489e49571086ef83b2bb8ce311e730092d2c34ca8f7d925cb20aa",
                "sha256:8f4a014bc36d3c57402e2977dada34f9c12300af536839dc38c0beab8878f38a",
                "sha256:9063e24fdb1e498ab71cb7419e24622516c4a04476b17a2dab57e8baa30d6e03",
                "sha256:90d558489962fd4918143277a773316e56c72da56ec7aa3dc3dbbe20fdfed15b",
                "sha256:923c0c831b7cfcb071580d3f46c4baf50f174be571576556269530f4bbd79d04",
                "sha256:95f2a5796329323b8f0512e09dbb7a1860c46a39da62ecb2324f116fa8fdc85c",
                "sha256:96b02a3dc4381e5494fad39be677abcb5e6634bf7b4fa83a6dd3112607547001",
                "sha256:9f96df6923e21816da7e0ad3fd47dd8f94b2a5ce594e00677c0013018b813458",
                "sha256:a10af20b82360ab00827f916a6058451b723b4e65030c5a18577c8b2de5b3389",
                "sha256:a50aebfa173e157099939b17f18600f72f84eed3049e743b68ad15bd69b6bf99",
                "sha256:a981a536974bbc7a512cf44ed14938cf01030a99e9b3a06dd59578882f06f985",
                "sha256:a9a8e9031d613fd2009c182b69c7b2c1ef8239a0efb1df3f7c8da66d5dd3d537",
                "sha256:ae5f4161f18c61806f411a13b0310bea87f987c7d2ecdbdaad0e94eb2e404238",
                "sha256:aed38f6e4fb3f5d6bf81bfa990a07806be9d83cf7bacef998ab1a9bd660a581f",
                "sha256:b01b88d45a6fcb69667cd6d2f7a9aeb4bf53760d7fc536bf679ec94fe9f3ff3d",
                "sha256:b261ccdec7821281dade748d088bb6e9b69e6d15b30652b74cbbac25e280b796",
                "sha256:b2b0a0c0517616b6869869f8c581d4eb2dd83a4d79e0ebcb7d373ef9956aeb0a",
                "sha256:b4a23f61ce87adf89be746c8a8974fe1c823c891d8f86eb218bb957c924bb143",
                "sha256:bd8f7df7d12c2db9fab40bdd87a7c09b1530128315d047a086fa3ae3435cb3a8",
                "sha256:beb58fe5cdb101e3a055192ac291b7a21e3b7ef4f67fa1d74e331a7f2124341c",
                "sha256:c002b4ffc0be611f0d9da932eb0f704fe2602a9a949d1f738e4c34c75b0863d5",
                "sha256:c083af607d2515612056a31f0a8d9e0fcb5876b7bfc0abad3ecd275bc4ebc2d5",
                "sha256:c180f51afb394e165eafe4ac2936a14bee3eb10debc9d9e4db8958fe36afe711",
                "sha256:c235ebd9baae02f1b77bcea61bce332cb4331dc3617d254df3323aa01ab47bd4",
                "sha256:cd70574b12bb8a4d2aaa0094515df2463cb429d8536cfb6c7ce983246983e5a6",
                "sha256:d0eccceffcb53201b5bfebb52600a5fb483a20b61da9dbc885f8b103cbe7598c",
                "sha256:d965bba47ddeec8cd560687584e88cf699fd28f192ceb452d1d7ee807c5597b7",
                "sha256:db364eca23f876da6f9e16c9da0df51aa4f104a972735574842618b8c6d999d4",
                "sha256:ddbb2551d7e0102e7252db79ba445cdab71b26640817ab1e3e3648dad515003b",
                "sha256:deb6be0ac38ece9ba87dea880e438f25ca3eddfac8b002a2ec3d9183a454e8ae",
                "sha256:e06ed3eb3218bc64786f7db41917d4e686cc4856944f53d5bdf83a6884432e12",
                "sha256:e27ad930a842b4c5eb8ac0016b0a54f5aebbe679340c26101df33424142c143c",
                "sha256:e537484df0d8f426ce2afb2d0f8e1c3d0b114b83f8850e5f2fbea0e797bd82ae",
                "sha256:eb00ed941194665c332bf8e078baf037d6c35d7c4f3102ea2d4f16ca94a26dc8",
                "sha256:eb6904c354526e758fda7167b33005998fb68c46fbc10e013ca97f21ca5c8887",
                "sha256:eb8821e09e916165e160797a6c17edda0679379a4be5c716c260e836e122f54b",
                "sha256:efcb3f6676480691518c177e3b465bcddf57cea040302f9f4e6e191af91174d4",
                "sha256:f27273b60488abe721a075bcca6d7f3964f9f6f067c8c4c605743023d7d3944f",
                "sha256:f30c3cb33b24454a82faecaf01b19c18562b1e89558fb6c56de4d9118a032fd5",
                "sha256:fb69256e180cb6c8a894fee62b3afebae785babc1ee98b81cdf68bbca1987f33",
                "sha256:fd1abc0d89e30cc4e02e4064dc67fcc51bd941eb395c502aac3ec19fab46b519",
                "sha256:ff8fa367d09b717b2a17a052544193ad76cd49979c805768879cb63d9ca50561"
            ],
            "index": "pypi",
            "markers": "python_full_version >= '3.7.0'",
            "version": "==3.3.2"
        },
        "click": {
            "hashes": [
                "sha256:ae74fb96c20a0277a1d615f1e4d73c8414f5a98db8b799a7931d1582f3390c28",
                "sha256:ca9853ad459e787e2192211578cc907e7594e294c7ccc834310722b41b9ca6de"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==8.1.7"
        },
        "cloudpickle": {
            "hashes": [
                "sha256:81a929b6e3c7335c863c771d673d105f02efdb89dfaba0c90495d1c64796601b",
                "sha256:fe11acda67f61aaaec473e3afe030feb131d78a43461b718185363384f1ba12e"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.1.0"
        },
        "colorama": {
            "hashes": [
                "sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44",
                "sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6"
            ],
            "index": "pypi",
            "markers": "python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6'",
            "version": "==0.4.6"
        },
        "colorcet": {
            "hashes": [
                "sha256:2921b3cd81a2288aaf2d63dbc0ce3c26dcd882e8c389cc505d6886bf7aa9a4eb",
                "sha256:2a7d59cc8d0f7938eeedd08aad3152b5319b4ba3bcb7a612398cc17a384cb296"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==3.1.0"
        },
        "comm": {
            "hashes": [
                "sha256:3fd7a84065306e07bea1773df6eb8282de51ba82f77c72f9c85716ab11fe980e",
                "sha256:e6fb86cb70ff661ee8c9c14e7d36d6de3b4066f1441be4063df9c5009f0a64d3"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.2.2"
        },
        "constantly": {
            "hashes": [
                "sha256:3fd9b4d1c3dc1ec9757f3c52aef7e53ad9323dbe39f51dfd4c43853b68dfa3f9",
                "sha256:aa92b70a33e2ac0bb33cd745eb61776594dc48764b06c35e0efd050b7f1c7cbd"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==23.10.4"
        },
        "contourpy": {
            "hashes": [
                "sha256:041b640d4ec01922083645a94bb3b2e777e6b626788f4095cf21abbe266413c1",
                "sha256:05e806338bfeaa006acbdeba0ad681a10be63b26e1b17317bfac3c5d98f36cda",
                "sha256:08d9d449a61cf53033612cb368f3a1b26cd7835d9b8cd326647efe43bca7568d",
                "sha256:0ffa84be8e0bd33410b17189f7164c3589c229ce5db85798076a3fa136d0e509",
                "sha256:113231fe3825ebf6f15eaa8bc1f5b0ddc19d42b733345eae0934cb291beb88b6",
                "sha256:14c102b0eab282427b662cb590f2e9340a9d91a1c297f48729431f2dcd16e14f",
                "sha256:174e758c66bbc1c8576992cec9599ce8b6672b741b5d336b5c74e35ac382b18e",
                "sha256:19c1555a6801c2f084c7ddc1c6e11f02eb6a6016ca1318dd5452ba3f613a1751",
                "sha256:19d40d37c1c3a4961b4619dd9d77b12124a453cc3d02bb31a07d58ef684d3d86",
                "sha256:1bf98051f1045b15c87868dbaea84f92408337d4f81d0e449ee41920ea121d3b",
                "sha256:20914c8c973f41456337652a6eeca26d2148aa96dd7ac323b74516988bea89fc",
                "sha256:287ccc248c9e0d0566934e7d606201abd74761b5703d804ff3df8935f523d546",
                "sha256:2ba94a401342fc0f8b948e57d977557fbf4d515f03c67682dd5c6191cb2d16ec",
                "sha256:31c1b55c1f34f80557d3830d3dd93ba722ce7e33a0b472cba0ec3b6535684d8f",
                "sha256:36987a15e8ace5f58d4d5da9dca82d498c2bbb28dff6e5d04fbfcc35a9cb3a82",
                "sha256:3a04ecd68acbd77fa2d39723ceca4c3197cb2969633836ced1bea14e219d077c",
                "sha256:3e8b974d8db2c5610fb4e76307e265de0edb655ae8169e8b21f41807ccbeec4b",
                "sha256:3ea9924d28fc5586bf0b42d15f590b10c224117e74409dd7a0be3b62b74a501c",
                "sha256:4318af1c925fb9a4fb190559ef3eec206845f63e80fb603d47f2d6d67683901c",
                "sha256:44a29502ca9c7b5ba389e620d44f2fbe792b1fb5734e8b931ad307071ec58c53",
                "sha256:47734d7073fb4590b4a40122b35917cd77be5722d80683b249dac1de266aac80",
                "sha256:4d76d5993a34ef3df5181ba3c92fabb93f1eaa5729504fb03423fcd9f3177242",
                "sha256:4dbbc03a40f916a8420e420d63e96a1258d3d1b58cbdfd8d1f07b49fcbd38e85",
                "sha256:500360b77259914f7805af7462e41f9cb7ca92ad38e9f94d6c8641b089338124",
                "sha256:523a8ee12edfa36f6d2a49407f705a6ef4c5098de4f498619787e272de93f2d5",
                "sha256:573abb30e0e05bf31ed067d2f82500ecfdaec15627a59d63ea2d95714790f5c2",
                "sha256:5b75aa69cb4d6f137b36f7eb2ace9280cfb60c55dc5f61c731fdf6f037f958a3",
                "sha256:61332c87493b00091423e747ea78200659dc09bdf7fd69edd5e98cef5d3e9a8d",
                "sha256:805617228ba7e2cbbfb6c503858e626ab528ac2a32a04a2fe88ffaf6b02c32bc",
                "sha256:841ad858cff65c2c04bf93875e384ccb82b654574a6d7f30453a04f04af71342",
                "sha256:89785bb2a1980c1bd87f0cb1517a71cde374776a5f150936b82580ae6ead44a1",
                "sha256:8eb96e79b9f3dcadbad2a3891672f81cdcab7f95b27f28f1c67d75f045b6b4f1",
                "sha256:974d8145f8ca354498005b5b981165b74a195abfae9a8129df3e56771961d595",
                "sha256:9ddeb796389dadcd884c7eb07bd14ef12408aaae358f0e2ae24114d797eede30",
                "sha256:a045f341a77b77e1c5de31e74e966537bba9f3c4099b35bf4c2e3939dd54cdab",
                "sha256:a0cffcbede75c059f535725c1680dfb17b6ba8753f0c74b14e6a9c68c29d7ea3",
                "sha256:a761d9ccfc5e2ecd1bf05534eda382aa14c3e4f9205ba5b1684ecfe400716ef2",
                "sha256:a7895f46d47671fa7ceec40f31fae721da51ad34bdca0bee83e38870b1f47ffd",
                "sha256:a9fa36448e6a3a1a9a2ba23c02012c43ed88905ec80163f2ffe2421c7192a5d7",
                "sha256:ab29962927945d89d9b293eabd0d59aea28d887d4f3be6c22deaefbb938a7277",
                "sha256:abbb49fb7dac584e5abc6636b7b2a7227111c4f771005853e7d25176daaf8453",
                "sha256:ac4578ac281983f63b400f7fe6c101bedc10651650eef012be1ccffcbacf3697",
                "sha256:adce39d67c0edf383647a3a007de0a45fd1b08dedaa5318404f1a73059c2512b",
                "sha256:ade08d343436a94e633db932e7e8407fe7de8083967962b46bdfc1b0ced39454",
                "sha256:b2bdca22a27e35f16794cf585832e542123296b4687f9fd96822db6bae17bfc9",
                "sha256:b2f926efda994cdf3c8d3fdb40b9962f86edbc4457e739277b961eced3d0b4c1",
                "sha256:b457d6430833cee8e4b8e9b6f07aa1c161e5e0d52e118dc102c8f9bd7dd060d6",
                "sha256:c414fc1ed8ee1dbd5da626cf3710c6013d3d27456651d156711fa24f24bd1291",
                "sha256:cb76c1a154b83991a3cbbf0dfeb26ec2833ad56f95540b442c73950af2013750",
                "sha256:dfd97abd83335045a913e3bcc4a09c0ceadbe66580cf573fe961f4a825efa699",
                "sha256:e914a8cb05ce5c809dd0fe350cfbb4e881bde5e2a38dc04e3afe1b3e58bd158e",
                "sha256:ece6df05e2c41bd46776fbc712e0996f7c94e0d0543af1656956d150c4ca7c81",
                "sha256:efa874e87e4a647fd2e4f514d5e91c7d493697127beb95e77d2f7561f6905bd9",
                "sha256:f611e628ef06670df83fce17805c344710ca5cde01edfdc72751311da8585375"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==1.3.1"
        },
        "cryptography": {
            "hashes": [
                "sha256:0270572b8bd2c833c3981724b8ee9747b3ec96f699a9665470018594301439ee",
                "sha256:111a0d8553afcf8eb02a4fea6ca4f59d48ddb34497aa8706a6cf536f1a5ec576",
                "sha256:16a48c23a62a2f4a285699dba2e4ff2d1cff3115b9df052cdd976a18856d8e3d",
                "sha256:1b95b98b0d2af784078fa69f637135e3c317091b615cd0905f8b8a087e86fa30",
                "sha256:1f71c10d1e88467126f0efd484bd44bca5e14c664ec2ede64c32f20875c0d413",
                "sha256:2424ff4c4ac7f6b8177b53c17ed5d8fa74ae5955656867f5a8affaca36a27abb",
                "sha256:2bce03af1ce5a5567ab89bd90d11e7bbdff56b8af3acbbec1faded8f44cb06da",
                "sha256:329906dcc7b20ff3cad13c069a78124ed8247adcac44b10bea1130e36caae0b4",
                "sha256:37dd623507659e08be98eec89323469e8c7b4c1407c85112634ae3dbdb926fdd",
                "sha256:3eaafe47ec0d0ffcc9349e1708be2aaea4c6dd4978d76bf6eb0cb2c13636c6fc",
                "sha256:5e6275c09d2badf57aea3afa80d975444f4be8d3bc58f7f80d2a484c6f9485c8",
                "sha256:6fe07eec95dfd477eb9530aef5bead34fec819b3aaf6c5bd6d20565da607bfe1",
                "sha256:7367d7b2eca6513681127ebad53b2582911d1736dc2ffc19f2c3ae49997496bc",
                "sha256:7cde5f38e614f55e28d831754e8a3bacf9ace5d1566235e39d91b35502d6936e",
                "sha256:9481ffe3cf013b71b2428b905c4f7a9a4f76ec03065b05ff499bb5682a8d9ad8",
                "sha256:98d8dc6d012b82287f2c3d26ce1d2dd130ec200c8679b6213b3c73c08b2b7940",
                "sha256:a011a644f6d7d03736214d38832e030d8268bcff4a41f728e6030325fea3e400",
                "sha256:a2913c5375154b6ef2e91c10b5720ea6e21007412f6437504ffea2109b5a33d7",
                "sha256:a30596bae9403a342c978fb47d9b0ee277699fa53bbafad14706af51fe543d16",
                "sha256:b03c2ae5d2f0fc05f9a2c0c997e1bc18c8229f392234e8a0194f202169ccd278",
                "sha256:b6cd2203306b63e41acdf39aa93b86fb566049aeb6dc489b70e34bcd07adca74",
                "sha256:b7ffe927ee6531c78f81aa17e684e2ff617daeba7f189f911065b2ea2d526dec",
                "sha256:b8cac287fafc4ad485b8a9b67d0ee80c66bf3574f655d3b97ef2e1082360faf1",
                "sha256:ba334e6e4b1d92442b75ddacc615c5476d4ad55cc29b15d590cc6b86efa487e2",
                "sha256:ba3e4a42397c25b7ff88cdec6e2a16c2be18720f317506ee25210f6d31925f9c",
                "sha256:c41fb5e6a5fe9ebcd58ca3abfeb51dffb5d83d6775405305bfa8715b76521922",
                "sha256:cd2030f6650c089aeb304cf093f3244d34745ce0cfcc39f20c6fbfe030102e2a",
                "sha256:cd65d75953847815962c84a4654a84850b2bb4aed3f26fadcc1c13892e1e29f6",
                "sha256:e4985a790f921508f36f81831817cbc03b102d643b5fcb81cd33df3fa291a1a1",
                "sha256:e807b3188f9eb0eaa7bbb579b462c5ace579f1cedb28107ce8b48a9f7ad3679e",
                "sha256:f12764b8fffc7a123f641d7d049d382b73f96a34117e0b637b80643169cec8ac",
                "sha256:f8837fe1d6ac4a8052a9a8ddab256bc006242696f03368a4009be7ee3075cdb7"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==42.0.5"
        },
        "cycler": {
            "hashes": [
                "sha256:85cef7cff222d8644161529808465972e51340599459b8ac3ccbac5a854e0d30",
                "sha256:88bb128f02ba341da8ef447245a9e138fae777f6a23943da4540077d3601eb1c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.12.1"
        },
        "daphne": {
            "hashes": [
                "sha256:618d1322bb4d875342b99dd2a10da2d9aae7ee3645f765965fdc1e658ea5290a",
                "sha256:fcbcace38eb86624ae247c7ffdc8ac12f155d7d19eafac4247381896d6f33761"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.1.2"
        },
        "dash": {
            "hashes": [
                "sha256:47392f8d6455dc989a697407eb5941f3bad80604df985ab1ac9d4244568ffb34",
                "sha256:a749ae1ea9de3fe7b785353a818ec9b629d39c6b7e02462954203bd1e296fd0e"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==2.9.3"
        },
        "dash-bootstrap-components": {
            "hashes": [
                "sha256:960a1ec9397574792f49a8241024fa3cecde0f5930c971a3fc81f016cbeb1095",
                "sha256:97f0f47b38363f18863e1b247462229266ce12e1e171cfb34d3c9898e6e5cd1e"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8' and python_version < '4'",
            "version": "==1.6.0"
        },
        "dash-core-components": {
            "hashes": [
                "sha256:52b8e8cce13b18d0802ee3acbc5e888cb1248a04968f962d63d070400af2e346",
                "sha256:c6733874af975e552f95a1398a16c2ee7df14ce43fa60bb3718a3c6e0b63ffee"
            ],
            "index": "pypi",
            "version": "==2.0.0"
        },
        "dash-html-components": {
            "hashes": [
                "sha256:8703a601080f02619a6390998e0b3da4a5daabe97a1fd7a9cebc09d015f26e50",
                "sha256:b42cc903713c9706af03b3f2548bda4be7307a7cf89b7d6eae3da872717d1b63"
            ],
            "index": "pypi",
            "version": "==2.0.0"
        },
        "dash-table": {
            "hashes": [
                "sha256:18624d693d4c8ef2ddec99a6f167593437a7ea0bf153aa20f318c170c5bc7308",
                "sha256:19036fa352bb1c11baf38068ec62d172f0515f73ca3276c79dee49b95ddc16c9"
            ],
            "index": "pypi",
            "version": "==5.0.0"
        },
        "dask": {
            "hashes": [
                "sha256:6115c4b76015e8d9d9c2922b6a0a1c850e283fb7fee74eebbd2e28e9c117c30d",
                "sha256:9a72bee3f149ff89bc492340d4bcba33d5dd3e3a9d471d2b4b3872f2d71ddaae"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==2024.11.2"
        },
        "datashader": {
            "hashes": [
                "sha256:90e7425f17b5dc597ab50facca1d16df53c4893708500ad89d4e64b6eb7238aa",
                "sha256:9d0040c7887f7a5a5edd374c297402fd208a62bf6845e87631b54f03b9ae479d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==0.16.3"
        },
        "debugpy": {
            "hashes": [
                "sha256:1339e14c7d980407248f09824d1b25ff5c5616651689f1e0f0e51bdead3ea13e",
                "sha256:17c5e0297678442511cf00a745c9709e928ea4ca263d764e90d233208889a19e",
                "sha256:1efbb3ff61487e2c16b3e033bc8595aea578222c08aaf3c4bf0f93fadbd662ee",
                "sha256:365e556a4772d7d0d151d7eb0e77ec4db03bcd95f26b67b15742b88cacff88e9",
                "sha256:3d9755e77a2d680ce3d2c5394a444cf42be4a592caaf246dbfbdd100ffcf7ae5",
                "sha256:3e59842d6c4569c65ceb3751075ff8d7e6a6ada209ceca6308c9bde932bcef11",
                "sha256:472a3994999fe6c0756945ffa359e9e7e2d690fb55d251639d07208dbc37caea",
                "sha256:54a7e6d3014c408eb37b0b06021366ee985f1539e12fe49ca2ee0d392d9ceca5",
                "sha256:5e565fc54b680292b418bb809f1386f17081d1346dca9a871bf69a8ac4071afe",
                "sha256:62d22dacdb0e296966d7d74a7141aaab4bec123fa43d1a35ddcb39bf9fd29d70",
                "sha256:66eeae42f3137eb428ea3a86d4a55f28da9bd5a4a3d369ba95ecc3a92c1bba53",
                "sha256:6953b335b804a41f16a192fa2e7851bdcfd92173cbb2f9f777bb934f49baab65",
                "sha256:7c4d65d03bee875bcb211c76c1d8f10f600c305dbd734beaed4077e902606fee",
                "sha256:7e646e62d4602bb8956db88b1e72fe63172148c1e25c041e03b103a25f36673c",
                "sha256:7e8b079323a56f719977fde9d8115590cb5e7a1cba2fcee0986ef8817116e7c1",
                "sha256:8138efff315cd09b8dcd14226a21afda4ca582284bf4215126d87342bba1cc66",
                "sha256:8e99c0b1cc7bf86d83fb95d5ccdc4ad0586d4432d489d1f54e4055bcc795f693",
                "sha256:957363d9a7a6612a37458d9a15e72d03a635047f946e5fceee74b50d52a9c8e2",
                "sha256:957ecffff80d47cafa9b6545de9e016ae8c9547c98a538ee96ab5947115fb3dd",
                "sha256:ada7fb65102a4d2c9ab62e8908e9e9f12aed9d76ef44880367bc9308ebe49a0f",
                "sha256:b74a49753e21e33e7cf030883a92fa607bddc4ede1aa4145172debc637780040",
                "sha256:c36856343cbaa448171cba62a721531e10e7ffb0abff838004701454149bc037",
                "sha256:cc37a6c9987ad743d9c3a14fa1b1a14b7e4e6041f9dd0c8abf8895fe7a97b899",
                "sha256:cfe1e6c6ad7178265f74981edf1154ffce97b69005212fbc90ca22ddfe3d017e",
                "sha256:e46b420dc1bea64e5bbedd678148be512442bc589b0111bd799367cde051e71a",
                "sha256:ff54ef77ad9f5c425398efb150239f6fe8e20c53ae2f68367eba7ece1e96226d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.8.9"
        },
        "decorator": {
            "hashes": [
                "sha256:637996211036b6385ef91435e4fae22989472f9d571faba8927ba8253acbc330",
                "sha256:b8c3f85900b9dc423225913c5aace94729fe1fa9763b38939a95226f02d37186"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.5'",
            "version": "==5.1.1"
        },
        "dj-database-url": {
            "hashes": [
                "sha256:ae52e8e634186b57e5a45e445da5dc407a819c2ceed8a53d1fac004cc5288787",
                "sha256:bb0d414ba0ac5cd62773ec7f86f8cc378a9dbb00a80884c2fc08cc570452521e"
            ],
            "index": "pypi",
            "version": "==2.3.0"
        },
        "django": {
            "hashes": [
                "sha256:4bd01a8c830bb77a8a3b0e7d8b25b887e536ad17a81ba2dce5476135c73312bd",
                "sha256:916423499d75d62da7aa038d19aef23d23498d8df229775eb0a6309ee1013775"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==5.0.4"
        },
        "django-debug-toolbar": {
            "hashes": [
                "sha256:0b0dddee5ea29b9cb678593bc0d7a6d76b21d7799cb68e091a2148341a80f3c4",
                "sha256:e09b7dcb8417b743234dfc57c95a7c1d1d87a88844abd13b4c5387f807b31bf6"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.3.0"
        },
        "django-plotly-dash": {
            "hashes": [
                "sha256:1a0da2a1547ab394076febc16802ddc9aa8f21fbfd2ba1b41a2093f5c4a31551",
                "sha256:715a827a5d02d1d6e646a9ea415bd27c3ba06c45f1c300f48f89c0a6301dc551"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.3.1"
        },
        "django-redis": {
            "hashes": [
                "sha256:6a02abaa34b0fea8bf9b707d2c363ab6adc7409950b2db93602e6cb292818c42",
                "sha256:ebc88df7da810732e2af9987f7f426c96204bf89319df4c6da6ca9a2942edd5b"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==5.4.0"
        },
        "docutils": {
            "hashes": [
                "sha256:3a6b18732edf182daa3cd12775bbb338cf5691468f91eeeb109deff6ebfa986f",
                "sha256:dafca5b9e384f0e419294eb4d2ff9fa826435bf15f15b7bd45723e8ad76811b2"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==0.21.2"
        },
        "dpd-components": {
            "hashes": [
                "sha256:613a6b17d3d7dd449be060e739e4ce36692b46fa012c3a86ee947f6337d09548"
            ],
            "index": "pypi",
            "version": "==0.1.0"
        },
        "dpd-static-support": {
            "hashes": [
                "sha256:34037d342a27e3f183f36150c5956e26fb17de7ee8c4a5b651f7c4edaa6c465d",
                "sha256:ba03e2fde126b45b20df63e3c5eb162d1e9c2ca83868ef37b6f5482abe6f81aa"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.5'",
            "version": "==0.0.5"
        },
        "et-xmlfile": {
            "hashes": [
                "sha256:7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa",
                "sha256:dab3f4764309081ce75662649be815c4c9081e88f0837825f90fd28317d4da54"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.0.0"
        },
        "eventkit": {
            "hashes": [
                "sha256:0e199527a89aff9d195b9671ad45d2cc9f79ecda0900de8ecfb4c864d67ad6a2",
                "sha256:99497f6f3c638a50ff7616f2f8cd887b18bbff3765dc1bd8681554db1467c933"
            ],
            "index": "pypi",
            "version": "==1.0.3"
        },
        "executing": {
            "hashes": [
                "sha256:8d63781349375b5ebccc3142f4b30350c0cd9c79f921cde38be2be4637e98eaf",
                "sha256:8ea27ddd260da8150fa5a708269c4a10e76161e2496ec3e587da9e3c0fe4b9ab"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.1.0"
        },
        "fastjsonschema": {
            "hashes": [
                "sha256:794d4f0a58f848961ba16af7b9c85a3e88cd360df008c59aac6fc5ae9323b5d4",
                "sha256:c9e5b7e908310918cf494a434eeb31384dd84a98b57a30bcb1f535015b554667"
            ],
            "version": "==2.21.1"
        },
        "filelock": {
            "hashes": [
                "sha256:2082e5703d51fbf98ea75855d9d5527e33d8ff23099bec374a134febee6946b0",
                "sha256:c249fbfcd5db47e5e2d6d62198e565475ee65e4831e2561c8e313fa7eb961435"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.16.1"
        },
        "flask": {
            "hashes": [
                "sha256:34e815dfaa43340d1d15a5c3a02b8476004037eb4840b34910c6e21679d288f3",
                "sha256:ceb27b0af3823ea2737928a4d99d125a06175b8512c445cbd9a9ce200ef76842"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.0.3"
        },
        "flatbuffers": {
            "hashes": [
                "sha256:8dbdec58f935f3765e4f7f3cf635ac3a77f83568138d6a2311f524ec96364812",
                "sha256:de2ec5b203f21441716617f38443e0a8ebf3d25bf0d9c0bb0ce68fa00ad546a4"
            ],
            "index": "pypi",
            "version": "==24.3.25"
        },
        "fonttools": {
            "hashes": [
                "sha256:00f7cf55ad58a57ba421b6a40945b85ac7cc73094fb4949c41171d3619a3a47e",
                "sha256:01124f2ca6c29fad4132d930da69158d3f49b2350e4a779e1efbe0e82bd63f6c",
                "sha256:12db5888cd4dd3fcc9f0ee60c6edd3c7e1fd44b7dd0f31381ea03df68f8a153f",
                "sha256:161d1ac54c73d82a3cded44202d0218ab007fde8cf194a23d3dd83f7177a2f03",
                "sha256:1f0e115281a32ff532118aa851ef497a1b7cda617f4621c1cdf81ace3e36fb0c",
                "sha256:23bbbb49bec613a32ed1b43df0f2b172313cee690c2509f1af8fdedcf0a17438",
                "sha256:2863555ba90b573e4201feaf87a7e71ca3b97c05aa4d63548a4b69ea16c9e998",
                "sha256:2b3ab90ec0f7b76c983950ac601b58949f47aca14c3f21eed858b38d7ec42b05",
                "sha256:31d00f9852a6051dac23294a4cf2df80ced85d1d173a61ba90a3d8f5abc63c60",
                "sha256:33b52a9cfe4e658e21b1f669f7309b4067910321757fec53802ca8f6eae96a5a",
                "sha256:37dbb3fdc2ef7302d3199fb12468481cbebaee849e4b04bc55b77c24e3c49189",
                "sha256:3e569711464f777a5d4ef522e781dc33f8095ab5efd7548958b36079a9f2f88c",
                "sha256:3f901cef813f7c318b77d1c5c14cf7403bae5cb977cede023e22ba4316f0a8f6",
                "sha256:51c029d4c0608a21a3d3d169dfc3fb776fde38f00b35ca11fdab63ba10a16f61",
                "sha256:5435e5f1eb893c35c2bc2b9cd3c9596b0fcb0a59e7a14121562986dd4c47b8dd",
                "sha256:553bd4f8cc327f310c20158e345e8174c8eed49937fb047a8bda51daf2c353c8",
                "sha256:55718e8071be35dff098976bc249fc243b58efa263768c611be17fe55975d40a",
                "sha256:61dc0a13451143c5e987dec5254d9d428f3c2789a549a7cf4f815b63b310c1cc",
                "sha256:636caaeefe586d7c84b5ee0734c1a5ab2dae619dc21c5cf336f304ddb8f6001b",
                "sha256:6c99b5205844f48a05cb58d4a8110a44d3038c67ed1d79eb733c4953c628b0f6",
                "sha256:7208856f61770895e79732e1dcbe49d77bd5783adf73ae35f87fcc267df9db81",
                "sha256:732a9a63d6ea4a81b1b25a1f2e5e143761b40c2e1b79bb2b68e4893f45139a40",
                "sha256:7636acc6ab733572d5e7eec922b254ead611f1cdad17be3f0be7418e8bfaca71",
                "sha256:7dd91ac3fcb4c491bb4763b820bcab6c41c784111c24172616f02f4bc227c17d",
                "sha256:8118dc571921dc9e4b288d9cb423ceaf886d195a2e5329cc427df82bba872cd9",
                "sha256:81ffd58d2691f11f7c8438796e9f21c374828805d33e83ff4b76e4635633674c",
                "sha256:838d2d8870f84fc785528a692e724f2379d5abd3fc9dad4d32f91cf99b41e4a7",
                "sha256:8c9679fc0dd7e8a5351d321d8d29a498255e69387590a86b596a45659a39eb0d",
                "sha256:9ce4ba6981e10f7e0ccff6348e9775ce25ffadbee70c9fd1a3737e3e9f5fa74f",
                "sha256:a656652e1f5d55b9728937a7e7d509b73d23109cddd4e89ee4f49bde03b736c6",
                "sha256:a7ad1f1b98ab6cb927ab924a38a8649f1ffd7525c75fe5b594f5dab17af70e18",
                "sha256:aa046f6a63bb2ad521004b2769095d4c9480c02c1efa7d7796b37826508980b6",
                "sha256:abe62987c37630dca69a104266277216de1023cf570c1643bb3a19a9509e7a1b",
                "sha256:b2e526b325a903868c62155a6a7e24df53f6ce4c5c3160214d8fe1be2c41b478",
                "sha256:b5263d8e7ef3c0ae87fbce7f3ec2f546dc898d44a337e95695af2cd5ea21a967",
                "sha256:b7ef9068a1297714e6fefe5932c33b058aa1d45a2b8be32a4c6dee602ae22b5c",
                "sha256:bca35b4e411362feab28e576ea10f11268b1aeed883b9f22ed05675b1e06ac69",
                "sha256:ca7fd6987c68414fece41c96836e945e1f320cda56fc96ffdc16e54a44ec57a2",
                "sha256:d12081729280c39d001edd0f4f06d696014c26e6e9a0a55488fabc37c28945e4",
                "sha256:dd2820a8b632f3307ebb0bf57948511c2208e34a4939cf978333bc0a3f11f838",
                "sha256:e198e494ca6e11f254bac37a680473a311a88cd40e58f9cc4dc4911dfb686ec6",
                "sha256:e7e6a352ff9e46e8ef8a3b1fe2c4478f8a553e1b5a479f2e899f9dc5f2055880",
                "sha256:e8e67974326af6a8879dc2a4ec63ab2910a1c1a9680ccd63e4a690950fceddbe",
                "sha256:f0a4b52238e7b54f998d6a56b46a2c56b59c74d4f8a6747fb9d4042190f37cd3",
                "sha256:f27526042efd6f67bfb0cc2f1610fa20364396f8b1fc5edb9f45bb815fb090b2",
                "sha256:f307f6b5bf9e86891213b293e538d292cd1677e06d9faaa4bf9c086ad5f132f6",
                "sha256:f46b863d74bab7bb0d395f3b68d3f52a03444964e67ce5c43ce43a75efce9246",
                "sha256:f50a1f455902208486fbca47ce33054208a4e437b38da49d6721ce2fef732fcf",
                "sha256:f8c8c76037d05652510ae45be1cd8fb5dd2fd9afec92a25374ac82255993d57c",
                "sha256:fa34aa175c91477485c44ddfbb51827d470011e558dfd5c7309eb31bef19ec51"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.55.0"
        },
        "fsspec": {
            "hashes": [
                "sha256:03b9a6785766a4de40368b88906366755e2819e758b83705c88cd7cb5fe81871",
                "sha256:eda2d8a4116d4f2429db8550f2457da57279247dd930bb12f821b58391359493"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2024.10.0"
        },
        "gast": {
            "hashes": [
                "sha256:52b182313f7330389f72b069ba00f174cfe2a06411099547288839c6cbafbd54",
                "sha256:88fc5300d32c7ac6ca7b515310862f71e6fdf2c029bbec7c66c0f5dd47b6b1fb"
            ],
            "index": "pypi",
            "markers": "python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
            "version": "==0.6.0"
        },
        "google-pasta": {
            "hashes": [
                "sha256:4612951da876b1a10fe3960d7226f0c7682cf901e16ac06e473b267a5afa8954",
                "sha256:b32482794a366b5366a32c92a9a9201b107821889935a02b3e51f6b432ea84ed",
                "sha256:c9f2c8dfc8f96d0d5808299920721be30c9eec37f2389f28904f454565c8a16e"
            ],
            "index": "pypi",
            "version": "==0.2.0"
        },
        "grpcio": {
            "hashes": [
                "sha256:0d230852ba97654453d290e98d6aa61cb48fa5fafb474fb4c4298d8721809354",
                "sha256:0efbbd849867e0e569af09e165363ade75cf84f5229b2698d53cf22c7a4f9e21",
                "sha256:14331e5c27ed3545360464a139ed279aa09db088f6e9502e95ad4bfa852bb116",
                "sha256:15327ab81131ef9b94cb9f45b5bd98803a179c7c61205c8c0ac9aff9d6c4e82a",
                "sha256:15377bce516b1c861c35e18eaa1c280692bf563264836cece693c0f169b48829",
                "sha256:15fa1fe25d365a13bc6d52fcac0e3ee1f9baebdde2c9b3b2425f8a4979fccea1",
                "sha256:18668e36e7f4045820f069997834e94e8275910b1f03e078a6020bd464cb2363",
                "sha256:2af76ab7c427aaa26aa9187c3e3c42f38d3771f91a20f99657d992afada2294a",
                "sha256:2bddd04a790b69f7a7385f6a112f46ea0b34c4746f361ebafe9ca0be567c78e9",
                "sha256:32a9cb4686eb2e89d97022ecb9e1606d132f85c444354c17a7dbde4a455e4a3b",
                "sha256:3ac7f10850fd0487fcce169c3c55509101c3bde2a3b454869639df2176b60a03",
                "sha256:3b2b559beb2d433129441783e5f42e3be40a9e1a89ec906efabf26591c5cd415",
                "sha256:4028b8e9a3bff6f377698587d642e24bd221810c06579a18420a17688e421af7",
                "sha256:44bcbebb24363d587472089b89e2ea0ab2e2b4df0e4856ba4c0b087c82412121",
                "sha256:46a2d74d4dd8993151c6cd585594c082abe74112c8e4175ddda4106f2ceb022f",
                "sha256:4df81d78fd1646bf94ced4fb4cd0a7fe2e91608089c522ef17bc7db26e64effd",
                "sha256:4e300e6978df0b65cc2d100c54e097c10dfc7018b9bd890bbbf08022d47f766d",
                "sha256:4f1931c7aa85be0fa6cea6af388e576f3bf6baee9e5d481c586980c774debcb4",
                "sha256:50992f214264e207e07222703c17d9cfdcc2c46ed5a1ea86843d440148ebbe10",
                "sha256:55d3b52fd41ec5772a953612db4e70ae741a6d6ed640c4c89a64f017a1ac02b5",
                "sha256:5a180328e92b9a0050958ced34dddcb86fec5a8b332f5a229e353dafc16cd332",
                "sha256:619b5d0f29f4f5351440e9343224c3e19912c21aeda44e0c49d0d147a8d01544",
                "sha256:6b2f98165ea2790ea159393a2246b56f580d24d7da0d0342c18a085299c40a75",
                "sha256:6f9c7ad1a23e1047f827385f4713b5b8c6c7d325705be1dd3e31fb00dcb2f665",
                "sha256:79f81b7fbfb136247b70465bd836fa1733043fdee539cd6031cb499e9608a110",
                "sha256:7e0a3e72c0e9a1acab77bef14a73a416630b7fd2cbd893c0a873edc47c42c8cd",
                "sha256:7e7483d39b4a4fddb9906671e9ea21aaad4f031cdfc349fec76bdfa1e404543a",
                "sha256:88fb2925789cfe6daa20900260ef0a1d0a61283dfb2d2fffe6194396a354c618",
                "sha256:8af6137cc4ae8e421690d276e7627cfc726d4293f6607acf9ea7260bd8fc3d7d",
                "sha256:8b0ff09c81e3aded7a183bc6473639b46b6caa9c1901d6f5e2cba24b95e59e30",
                "sha256:8c73f9fbbaee1a132487e31585aa83987ddf626426d703ebcb9a528cf231c9b1",
                "sha256:99f06232b5c9138593ae6f2e355054318717d32a9c09cdc5a2885540835067a1",
                "sha256:9fe1b141cda52f2ca73e17d2d3c6a9f3f3a0c255c216b50ce616e9dca7e3441d",
                "sha256:a17278d977746472698460c63abf333e1d806bd41f2224f90dbe9460101c9796",
                "sha256:a59f5822f9459bed098ffbceb2713abbf7c6fd13f2b9243461da5c338d0cd6c3",
                "sha256:a6213d2f7a22c3c30a479fb5e249b6b7e648e17f364598ff64d08a5136fe488b",
                "sha256:a831dcc343440969aaa812004685ed322cdb526cd197112d0db303b0da1e8659",
                "sha256:afbf45a62ba85a720491bfe9b2642f8761ff348006f5ef67e4622621f116b04a",
                "sha256:b0cf343c6f4f6aa44863e13ec9ddfe299e0be68f87d68e777328bff785897b05",
                "sha256:c03d89df516128febc5a7e760d675b478ba25802447624edf7aa13b1e7b11e2a",
                "sha256:c1245651f3c9ea92a2db4f95d37b7597db6b246d5892bca6ee8c0e90d76fb73c",
                "sha256:cc5f0a4f5904b8c25729a0498886b797feb817d1fd3812554ffa39551112c161",
                "sha256:dba037ff8d284c8e7ea9a510c8ae0f5b016004f13c3648f72411c464b67ff2fb",
                "sha256:def1a60a111d24376e4b753db39705adbe9483ef4ca4761f825639d884d5da78",
                "sha256:e0d2f68eaa0a755edd9a47d40e50dba6df2bceda66960dee1218da81a2834d27",
                "sha256:e0d30f3fee9372796f54d3100b31ee70972eaadcc87314be369360248a3dcffe",
                "sha256:e18589e747c1e70b60fab6767ff99b2d0c359ea1db8a2cb524477f93cdbedf5b",
                "sha256:e1e7ed311afb351ff0d0e583a66fcb39675be112d61e7cfd6c8269884a98afbc",
                "sha256:e46541de8425a4d6829ac6c5d9b16c03c292105fe9ebf78cb1c31e8d242f9155",
                "sha256:e694b5928b7b33ca2d3b4d5f9bf8b5888906f181daff6b406f4938f3a997a490",
                "sha256:f60fa2adf281fd73ae3a50677572521edca34ba373a45b457b5ebe87c2d01e1d",
                "sha256:f84890b205692ea813653ece4ac9afa2139eae136e419231b0eec7c39fdbe4c2",
                "sha256:f8f695d9576ce836eab27ba7401c60acaf9ef6cf2f70dfe5462055ba3df02cc3",
                "sha256:fc05759ffbd7875e0ff2bd877be1438dfe97c9312bbc558c8284a9afa1d0f40e",
                "sha256:fd2c2d47969daa0e27eadaf15c13b5e92605c5e5953d23c06d0b5239a2f176d3"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.68.0"
        },
        "h11": {
            "hashes": [
                "sha256:8f19fbbe99e72420ff35c00b27a34cb9937e902a8b810e2c88300c6f0a3b699d",
                "sha256:e3fe4ac4b851c468cc8363d500db52c2ead036020723024a109d37346efaa761"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==0.14.0"
        },
        "h5py": {
            "hashes": [
                "sha256:018a4597f35092ae3fb28ee851fdc756d2b88c96336b8480e124ce1ac6fb9166",
                "sha256:050a4f2c9126054515169c49cb900949814987f0c7ae74c341b0c9f9b5056834",
                "sha256:06a903a4e4e9e3ebbc8b548959c3c2552ca2d70dac14fcfa650d9261c66939ed",
                "sha256:1473348139b885393125126258ae2d70753ef7e9cec8e7848434f385ae72069e",
                "sha256:2f0f1a382cbf494679c07b4371f90c70391dedb027d517ac94fa2c05299dacda",
                "sha256:326d70b53d31baa61f00b8aa5f95c2fcb9621a3ee8365d770c551a13dbbcbfdf",
                "sha256:3b15d8dbd912c97541312c0e07438864d27dbca857c5ad634de68110c6beb1c2",
                "sha256:3fdf95092d60e8130ba6ae0ef7a9bd4ade8edbe3569c13ebbaf39baefffc5ba4",
                "sha256:4532c7e97fbef3d029735db8b6f5bf01222d9ece41e309b20d63cfaae2fb5c4d",
                "sha256:513171e90ed92236fc2ca363ce7a2fc6f2827375efcbb0cc7fbdd7fe11fecafc",
                "sha256:52ab036c6c97055b85b2a242cb540ff9590bacfda0c03dd0cf0661b311f522f8",
                "sha256:577d618d6b6dea3da07d13cc903ef9634cde5596b13e832476dd861aaf651f3e",
                "sha256:59400f88343b79655a242068a9c900001a34b63e3afb040bd7cdf717e440f653",
                "sha256:59685fe40d8c1fbbee088c88cd4da415a2f8bee5c270337dc5a1c4aa634e3307",
                "sha256:5c4b41d1019322a5afc5082864dfd6359f8935ecd37c11ac0029be78c5d112c9",
                "sha256:62be1fc0ef195891949b2c627ec06bc8e837ff62d5b911b6e42e38e0f20a897d",
                "sha256:6fdf6d7936fa824acfa27305fe2d9f39968e539d831c5bae0e0d83ed521ad1ac",
                "sha256:7b3b8f3b48717e46c6a790e3128d39c61ab595ae0a7237f06dfad6a3b51d5351",
                "sha256:84342bffd1f82d4f036433e7039e241a243531a1d3acd7341b35ae58cdab05bf",
                "sha256:ad8a76557880aed5234cfe7279805f4ab5ce16b17954606cca90d578d3e713ef",
                "sha256:ba51c0c5e029bb5420a343586ff79d56e7455d496d18a30309616fdbeed1068f",
                "sha256:cb65f619dfbdd15e662423e8d257780f9a66677eae5b4b3fc9dca70b5fd2d2a3",
                "sha256:ccd9006d92232727d23f784795191bfd02294a4f2ba68708825cb1da39511a93",
                "sha256:d2b8dd64f127d8b324f5d2cd1c0fd6f68af69084e9e47d27efeb9e28e685af3e",
                "sha256:d3e465aee0ec353949f0f46bf6c6f9790a2006af896cee7c178a8c3e5090aa32",
                "sha256:e4d51919110a030913201422fb07987db4338eba5ec8c5a15d6fab8e03d443fc"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==3.12.1"
        },
        "holoviews": {
            "hashes": [
                "sha256:29d183045fafa3d846deda999d9687b99b8abdc1a8c06712e54afa576bb02b3e",
                "sha256:dc810b6790e1dd2c90f16406b292e08db10efa377b2554e46755a130e12044c5"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==1.20.0"
        },
        "httpcore": {
            "hashes": [
                "sha256:8551cb62a169ec7162ac7be8d4817d561f60e08eaa485234898414bb5a8a0b4c",
                "sha256:a3fff8f43dc260d5bd363d9f9cf1830fa3a458b332856f34282de498ed420edd"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.0.7"
        },
        "httpx": {
            "hashes": [
                "sha256:0858d3bab51ba7e386637f22a61d8ccddaeec5f3fe4209da3a6168dbb91573e0",
                "sha256:dc0b419a0cfeb6e8b34e85167c0da2671206f5095f1baa9663d23bcfd6b535fc"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.28.0"
        },
        "hyperlink": {
            "hashes": [
                "sha256:427af957daa58bc909471c6c40f74c5450fa123dd093fc53efd2e91d2705a56b",
                "sha256:e6b14c37ecb73e89c77d78cdb4c2cc8f3fb59a885c5b3f819ff4ed80f25af1b4"
            ],
            "index": "pypi",
            "version": "==21.0.0"
        },
        "ib-insync": {
            "hashes": [
                "sha256:73af602ca2463f260999970c5bd937b1c4325e383686eff301743a4de08d381e",
                "sha256:a61fbe56ff405d93d211dad8238d7300de76dd6399eafc04c320470edec9a4a4"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==0.9.86"
        },
        "idna": {
            "hashes": [
                "sha256:028ff3aadf0609c1fd278d8ea3089299412a7a8b9bd005dd08b9f8285bcb5cfc",
                "sha256:82fee1fc78add43492d3a1898bfa6d8a904cc97d8427f683ed8e798d07761aa0"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.5'",
            "version": "==3.7"
        },
        "importlib-metadata": {
            "hashes": [
                "sha256:30962b96c0c223483ed6cc7280e7f0199feb01a0e40cfae4d4450fc6fab1f570",
                "sha256:b78938b926ee8d5f020fc4772d487045805a55ddbad2ecf21c6d60938dc7fcd2"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==7.1.0"
        },
        "incremental": {
            "hashes": [
                "sha256:912feeb5e0f7e0188e6f42241d2f450002e11bbc0937c65865045854c24c0bd0",
                "sha256:b864a1f30885ee72c5ac2835a761b8fe8aa9c28b9395cacf27286602688d3e51"
            ],
            "index": "pypi",
            "version": "==22.10.0"
        },
        "ipykernel": {
            "hashes": [
                "sha256:afdb66ba5aa354b09b91379bac28ae4afebbb30e8b39510c9690afb7a10421b5",
                "sha256:f093a22c4a40f8828f8e330a9c297cb93dcab13bd9678ded6de8e5cf81c56215"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==6.29.5"
        },
        "ipython": {
            "hashes": [
                "sha256:85ec56a7e20f6c38fce7727dcca699ae4ffc85985aa7b23635a8008f918ae321",
                "sha256:cb0a405a306d2995a5cbb9901894d240784a9f341394c6ba3f4fe8c6eb89ff6e"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==8.30.0"
        },
        "itsdangerous": {
            "hashes": [
                "sha256:c6242fc49e35958c8b15141343aa660db5fc54d4f13a1db01a3f5891b98700ef",
                "sha256:e0050c0b7da1eea53ffaf149c0cfbb5c6e2e2b69c4bef22c81fa6eb73e5f6173"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.2.0"
        },
        "jedi": {
            "hashes": [
                "sha256:4770dc3de41bde3966b02eb84fbcf557fb33cce26ad23da12c742fb50ecb11f0",
                "sha256:a8ef22bde8490f57fe5c7681a3c83cb58874daf72b4784de3cce5b6ef6edb5b9"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==0.19.2"
        },
        "jinja2": {
            "hashes": [
                "sha256:7d6d50dd97d52cbc355597bd845fabfbac3f551e1f99619e39a35ce8c370b5fa",
                "sha256:ac8bd6544d4bb2c9792bf3a159e80bba8fda7f07e81bc3aed565432d5925ba90"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==3.1.3"
        },
        "jsonschema": {
            "hashes": [
                "sha256:d71497fef26351a33265337fa77ffeb82423f3ea21283cd9467bb03999266bc4",
                "sha256:fbadb6f8b144a8f8cf9f0b89ba94501d143e50411a1278633f56a7acf7fd5566"
            ],
            "markers": "python_version >= '3.8'",
            "version": "==4.23.0"
        },
        "jsonschema-specifications": {
            "hashes": [
                "sha256:4653bffbd6584f7de83a67e0d620ef16900b390ddc7939d56684d6c81e33f1af",
                "sha256:630159c9f4dbea161a6a2205c3011cc4f18ff381b189fff48bb39b9bf26ae608"
            ],
            "markers": "python_version >= '3.9'",
            "version": "==2025.4.1"
        },
        "jupyter-client": {
            "hashes": [
                "sha256:35b3a0947c4a6e9d589eb97d7d4cd5e90f910ee73101611f01283732bd6d9419",
                "sha256:e8a19cc986cc45905ac3362915f410f3af85424b4c0905e94fa5f2cb08e8f23f"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==8.6.3"
        },
        "jupyter-core": {
            "hashes": [
                "sha256:4f7315d2f6b4bcf2e3e7cb6e46772eba760ae459cd1f59d29eb57b0a01bd7409",
                "sha256:aa5f8d32bbf6b431ac830496da7392035d6f61b4f54872f15c4bd2a9c3f536d9"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==5.7.2"
        },
        "kiwisolver": {
            "hashes": [
                "sha256:073a36c8273647592ea332e816e75ef8da5c303236ec0167196793eb1e34657a",
                "sha256:08471d4d86cbaec61f86b217dd938a83d85e03785f51121e791a6e6689a3be95",
                "sha256:0c18ec74c0472de033e1bebb2911c3c310eef5649133dd0bedf2a169a1b269e5",
                "sha256:0c6c43471bc764fad4bc99c5c2d6d16a676b1abf844ca7c8702bdae92df01ee0",
                "sha256:10849fb2c1ecbfae45a693c070e0320a91b35dd4bcf58172c023b994283a124d",
                "sha256:18077b53dc3bb490e330669a99920c5e6a496889ae8c63b58fbc57c3d7f33a18",
                "sha256:18e0cca3e008e17fe9b164b55735a325140a5a35faad8de92dd80265cd5eb80b",
                "sha256:22f499f6157236c19f4bbbd472fa55b063db77a16cd74d49afe28992dff8c258",
                "sha256:2a8781ac3edc42ea4b90bc23e7d37b665d89423818e26eb6df90698aa2287c95",
                "sha256:2e6039dcbe79a8e0f044f1c39db1986a1b8071051efba3ee4d74f5b365f5226e",
                "sha256:34ea1de54beef1c104422d210c47c7d2a4999bdecf42c7b5718fbe59a4cac383",
                "sha256:3ab58c12a2cd0fc769089e6d38466c46d7f76aced0a1f54c77652446733d2d02",
                "sha256:3abc5b19d24af4b77d1598a585b8a719beb8569a71568b66f4ebe1fb0449460b",
                "sha256:3bf1ed55088f214ba6427484c59553123fdd9b218a42bbc8c6496d6754b1e523",
                "sha256:3ce6b2b0231bda412463e152fc18335ba32faf4e8c23a754ad50ffa70e4091ee",
                "sha256:3da53da805b71e41053dc670f9a820d1157aae77b6b944e08024d17bcd51ef88",
                "sha256:3f9362ecfca44c863569d3d3c033dbe8ba452ff8eed6f6b5806382741a1334bd",
                "sha256:409afdfe1e2e90e6ee7fc896f3df9a7fec8e793e58bfa0d052c8a82f99c37abb",
                "sha256:40fa14dbd66b8b8f470d5fc79c089a66185619d31645f9b0773b88b19f7223c4",
                "sha256:4322872d5772cae7369f8351da1edf255a604ea7087fe295411397d0cfd9655e",
                "sha256:44756f9fd339de0fb6ee4f8c1696cfd19b2422e0d70b4cefc1cc7f1f64045a8c",
                "sha256:46707a10836894b559e04b0fd143e343945c97fd170d69a2d26d640b4e297935",
                "sha256:48b571ecd8bae15702e4f22d3ff6a0f13e54d3d00cd25216d5e7f658242065ee",
                "sha256:48be928f59a1f5c8207154f935334d374e79f2b5d212826307d072595ad76a2e",
                "sha256:4bfa75a048c056a411f9705856abfc872558e33c055d80af6a380e3658766038",
                "sha256:4c00336b9dd5ad96d0a558fd18a8b6f711b7449acce4c157e7343ba92dd0cf3d",
                "sha256:4c26ed10c4f6fa6ddb329a5120ba3b6db349ca192ae211e882970bfc9d91420b",
                "sha256:4d05d81ecb47d11e7f8932bd8b61b720bf0b41199358f3f5e36d38e28f0532c5",
                "sha256:4e77f2126c3e0b0d055f44513ed349038ac180371ed9b52fe96a32aa071a5107",
                "sha256:5337ec7809bcd0f424c6b705ecf97941c46279cf5ed92311782c7c9c2026f07f",
                "sha256:5360cc32706dab3931f738d3079652d20982511f7c0ac5711483e6eab08efff2",
                "sha256:58370b1ffbd35407444d57057b57da5d6549d2d854fa30249771775c63b5fe17",
                "sha256:58cb20602b18f86f83a5c87d3ee1c766a79c0d452f8def86d925e6c60fbf7bfb",
                "sha256:599b5c873c63a1f6ed7eead644a8a380cfbdf5db91dcb6f85707aaab213b1674",
                "sha256:5b7dfa3b546da08a9f622bb6becdb14b3e24aaa30adba66749d38f3cc7ea9706",
                "sha256:5b9c3f4ee0b9a439d2415012bd1b1cc2df59e4d6a9939f4d669241d30b414327",
                "sha256:5d34eb8494bea691a1a450141ebb5385e4b69d38bb8403b5146ad279f4b30fa3",
                "sha256:5d5abf8f8ec1f4e22882273c423e16cae834c36856cac348cfbfa68e01c40f3a",
                "sha256:5e3bc157fed2a4c02ec468de4ecd12a6e22818d4f09cde2c31ee3226ffbefab2",
                "sha256:612a10bdae23404a72941a0fc8fa2660c6ea1217c4ce0dbcab8a8f6543ea9e7f",
                "sha256:657a05857bda581c3656bfc3b20e353c232e9193eb167766ad2dc58b56504948",
                "sha256:65e720d2ab2b53f1f72fb5da5fb477455905ce2c88aaa671ff0a447c2c80e8e3",
                "sha256:693902d433cf585133699972b6d7c42a8b9f8f826ebcaf0132ff55200afc599e",
                "sha256:6af936f79086a89b3680a280c47ea90b4df7047b5bdf3aa5c524bbedddb9e545",
                "sha256:71bb308552200fb2c195e35ef05de12f0c878c07fc91c270eb3d6e41698c3bcc",
                "sha256:764202cc7e70f767dab49e8df52c7455e8de0df5d858fa801a11aa0d882ccf3f",
                "sha256:76c8094ac20ec259471ac53e774623eb62e6e1f56cd8690c67ce6ce4fcb05650",
                "sha256:78a42513018c41c2ffd262eb676442315cbfe3c44eed82385c2ed043bc63210a",
                "sha256:79849239c39b5e1fd906556c474d9b0439ea6792b637511f3fe3a41158d89ca8",
                "sha256:7ab9ccab2b5bd5702ab0803676a580fffa2aa178c2badc5557a84cc943fcf750",
                "sha256:7bbfcb7165ce3d54a3dfbe731e470f65739c4c1f85bb1018ee912bae139e263b",
                "sha256:7c06a4c7cf15ec739ce0e5971b26c93638730090add60e183530d70848ebdd34",
                "sha256:801fa7802e5cfabe3ab0c81a34c323a319b097dfb5004be950482d882f3d7225",
                "sha256:803b8e1459341c1bb56d1c5c010406d5edec8a0713a0945851290a7930679b51",
                "sha256:82a5c2f4b87c26bb1a0ef3d16b5c4753434633b83d365cc0ddf2770c93829e3c",
                "sha256:84ec80df401cfee1457063732d90022f93951944b5b58975d34ab56bb150dfb3",
                "sha256:8705f17dfeb43139a692298cb6637ee2e59c0194538153e83e9ee0c75c2eddde",
                "sha256:88a9ca9c710d598fd75ee5de59d5bda2684d9db36a9f50b6125eaea3969c2599",
                "sha256:88f17c5ffa8e9462fb79f62746428dd57b46eb931698e42e990ad63103f35e6c",
                "sha256:8a3ec5aa8e38fc4c8af308917ce12c536f1c88452ce554027e55b22cbbfbff76",
                "sha256:8a9c83f75223d5e48b0bc9cb1bf2776cf01563e00ade8775ffe13b0b6e1af3a6",
                "sha256:8b01aac285f91ca889c800042c35ad3b239e704b150cfd3382adfc9dcc780e39",
                "sha256:8d53103597a252fb3ab8b5845af04c7a26d5e7ea8122303dd7a021176a87e8b9",
                "sha256:8e045731a5416357638d1700927529e2b8ab304811671f665b225f8bf8d8f933",
                "sha256:8f0ea6da6d393d8b2e187e6a5e3fb81f5862010a40c3945e2c6d12ae45cfb2ad",
                "sha256:90da3b5f694b85231cf93586dad5e90e2d71b9428f9aad96952c99055582f520",
                "sha256:913983ad2deb14e66d83c28b632fd35ba2b825031f2fa4ca29675e665dfecbe1",
                "sha256:9242795d174daa40105c1d86aba618e8eab7bf96ba8c3ee614da8302a9f95503",
                "sha256:929e294c1ac1e9f615c62a4e4313ca1823ba37326c164ec720a803287c4c499b",
                "sha256:933d4de052939d90afbe6e9d5273ae05fb836cc86c15b686edd4b3560cc0ee36",
                "sha256:942216596dc64ddb25adb215c3c783215b23626f8d84e8eff8d6d45c3f29f75a",
                "sha256:94252291e3fe68001b1dd747b4c0b3be12582839b95ad4d1b641924d68fd4643",
                "sha256:9893ff81bd7107f7b685d3017cc6583daadb4fc26e4a888350df530e41980a60",
                "sha256:9e838bba3a3bac0fe06d849d29772eb1afb9745a59710762e4ba3f4cb8424483",
                "sha256:a0f64a48bb81af7450e641e3fe0b0394d7381e342805479178b3d335d60ca7cf",
                "sha256:a17f6a29cf8935e587cc8a4dbfc8368c55edc645283db0ce9801016f83526c2d",
                "sha256:a1ecf0ac1c518487d9d23b1cd7139a6a65bc460cd101ab01f1be82ecf09794b6",
                "sha256:a79ae34384df2b615eefca647a2873842ac3b596418032bef9a7283675962644",
                "sha256:a91b5f9f1205845d488c928e8570dcb62b893372f63b8b6e98b863ebd2368ff2",
                "sha256:aa0abdf853e09aff551db11fce173e2177d00786c688203f52c87ad7fcd91ef9",
                "sha256:ac542bf38a8a4be2dc6b15248d36315ccc65f0743f7b1a76688ffb6b5129a5c2",
                "sha256:ad42ba922c67c5f219097b28fae965e10045ddf145d2928bfac2eb2e17673640",
                "sha256:aeb3531b196ef6f11776c21674dba836aeea9d5bd1cf630f869e3d90b16cfade",
                "sha256:b38ac83d5f04b15e515fd86f312479d950d05ce2368d5413d46c088dda7de90a",
                "sha256:b7d755065e4e866a8086c9bdada157133ff466476a2ad7861828e17b6026e22c",
                "sha256:bd3de6481f4ed8b734da5df134cd5a6a64fe32124fe83dde1e5b5f29fe30b1e6",
                "sha256:bfa1acfa0c54932d5607e19a2c24646fb4c1ae2694437789129cf099789a3b00",
                "sha256:c619b101e6de2222c1fcb0531e1b17bbffbe54294bfba43ea0d411d428618c27",
                "sha256:ce8be0466f4c0d585cdb6c1e2ed07232221df101a4c6f28821d2aa754ca2d9e2",
                "sha256:cf0438b42121a66a3a667de17e779330fc0f20b0d97d59d2f2121e182b0505e4",
                "sha256:cf8bcc23ceb5a1b624572a1623b9f79d2c3b337c8c455405ef231933a10da379",
                "sha256:d2b0e12a42fb4e72d509fc994713d099cbb15ebf1103545e8a45f14da2dfca54",
                "sha256:d83db7cde68459fc803052a55ace60bea2bae361fc3b7a6d5da07e11954e4b09",
                "sha256:dda56c24d869b1193fcc763f1284b9126550eaf84b88bbc7256e15028f19188a",
                "sha256:dea0bf229319828467d7fca8c7c189780aa9ff679c94539eed7532ebe33ed37c",
                "sha256:e1631290ee9271dffe3062d2634c3ecac02c83890ada077d225e081aca8aab89",
                "sha256:e28c7fea2196bf4c2f8d46a0415c77a1c480cc0724722f23d7410ffe9842c407",
                "sha256:e2e6c39bd7b9372b0be21456caab138e8e69cc0fc1190a9dfa92bd45a1e6e904",
                "sha256:e33e8fbd440c917106b237ef1a2f1449dfbb9b6f6e1ce17c94cd6a1e0d438376",
                "sha256:e8df2eb9b2bac43ef8b082e06f750350fbbaf2887534a5be97f6cf07b19d9583",
                "sha256:e968b84db54f9d42046cf154e02911e39c0435c9801681e3fc9ce8a3c4130278",
                "sha256:eb542fe7933aa09d8d8f9d9097ef37532a7df6497819d16efe4359890a2f417a",
                "sha256:edcfc407e4eb17e037bca59be0e85a2031a2ac87e4fed26d3e9df88b4165f92d",
                "sha256:eee3ea935c3d227d49b4eb85660ff631556841f6e567f0f7bda972df6c2c9935",
                "sha256:ef97b8df011141c9b0f6caf23b29379f87dd13183c978a30a3c546d2c47314cb",
                "sha256:f106407dda69ae456dd1227966bf445b157ccc80ba0dff3802bb63f30b74e895",
                "sha256:f3160309af4396e0ed04db259c3ccbfdc3621b5559b5453075e5de555e1f3a1b",
                "sha256:f32d6edbc638cde7652bd690c3e728b25332acbadd7cad670cc4a02558d9c417",
                "sha256:f37cfe618a117e50d8c240555331160d73d0411422b59b5ee217843d7b693608",
                "sha256:f4c9aee212bc89d4e13f58be11a56cc8036cabad119259d12ace14b34476fd07",
                "sha256:f4d742cb7af1c28303a51b7a27aaee540e71bb8e24f68c736f6f2ffc82f2bf05",
                "sha256:f5a8b53bdc0b3961f8b6125e198617c40aeed638b387913bf1ce78afb1b0be2a",
                "sha256:f816dd2277f8d63d79f9c8473a79fe54047bc0467754962840782c575522224d",
                "sha256:f9a9e8a507420fe35992ee9ecb302dab68550dedc0da9e2880dd88071c5fb052"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.4.7"
        },
        "libclang": {
            "hashes": [
                "sha256:0b2e143f0fac830156feb56f9231ff8338c20aecfe72b4ffe96f19e5a1dbb69a",
                "sha256:3f0e1f49f04d3cd198985fea0511576b0aee16f9ff0e0f0cad7f9c57ec3c20e8",
                "sha256:4dd2d3b82fab35e2bf9ca717d7b63ac990a3519c7e312f19fa8e86dcc712f7fb",
                "sha256:54dda940a4a0491a9d1532bf071ea3ef26e6dbaf03b5000ed94dd7174e8f9592",
                "sha256:69f8eb8f65c279e765ffd28aaa7e9e364c776c17618af8bff22a8df58677ff4f",
                "sha256:6f14c3f194704e5d09769108f03185fce7acaf1d1ae4bbb2f30a72c2400cb7c5",
                "sha256:83ce5045d101b669ac38e6da8e58765f12da2d3aafb3b9b98d88b286a60964d8",
                "sha256:a1214966d08d73d971287fc3ead8dfaf82eb07fb197680d8b3859dbbbbf78250",
                "sha256:c533091d8a3bbf7460a00cb6c1a71da93bffe148f172c7d03b1c31fbf8aa2a0b",
                "sha256:cf4a99b05376513717ab5d82a0db832c56ccea4fd61a69dbb7bccf2dfb207dbe"
            ],
            "index": "pypi",
            "version": "==18.1.1"
        },
        "linkify-it-py": {
            "hashes": [
                "sha256:68cda27e162e9215c17d786649d1da0021a451bdc436ef9e0fa0ba5234b9b048",
                "sha256:6bcbc417b0ac14323382aef5c5192c0075bf8a9d6b41820a2b66371eac6b6d79"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==2.0.3"
        },
        "llvmlite": {
            "hashes": [
                "sha256:14f0e4bf2fd2d9a75a3534111e8ebeb08eda2f33e9bdd6dfa13282afacdde0ed",
                "sha256:18e9953c748b105668487b7c81a3e97b046d8abf95c4ddc0cd3c94f4e4651ae8",
                "sha256:35d80d61d0cda2d767f72de99450766250560399edc309da16937b93d3b676e7",
                "sha256:3e8d0618cb9bfe40ac38a9633f2493d4d4e9fcc2f438d39a4e854f39cc0f5f98",
                "sha256:47e147cdda9037f94b399bf03bfd8a6b6b1f2f90be94a454e3386f006455a9b4",
                "sha256:6912a87782acdff6eb8bf01675ed01d60ca1f2551f8176a300a886f09e836a6a",
                "sha256:6d4fd101f571a31acb1559ae1af30f30b1dc4b3186669f92ad780e17c81e91bc",
                "sha256:74937acd22dc11b33946b67dca7680e6d103d6e90eeaaaf932603bec6fe7b03a",
                "sha256:7a2872ee80dcf6b5dbdc838763d26554c2a18aa833d31a2635bff16aafefb9c9",
                "sha256:7d434ec7e2ce3cc8f452d1cd9a28591745de022f931d67be688a737320dfcead",
                "sha256:977525a1e5f4059316b183fb4fd34fa858c9eade31f165427a3977c95e3ee749",
                "sha256:9cd2a7376f7b3367019b664c21f0c61766219faa3b03731113ead75107f3b66c",
                "sha256:a289af9a1687c6cf463478f0fa8e8aa3b6fb813317b0d70bf1ed0759eab6f761",
                "sha256:ae2b5b5c3ef67354824fb75517c8db5fbe93bc02cd9671f3c62271626bc041d5",
                "sha256:bc9efc739cc6ed760f795806f67889923f7274276f0eb45092a1473e40d9b867",
                "sha256:c1da416ab53e4f7f3bc8d4eeba36d801cc1894b9fbfbf2022b29b6bad34a7df2",
                "sha256:d5bd550001d26450bd90777736c69d68c487d17bf371438f975229b2b8241a91",
                "sha256:df6509e1507ca0760787a199d19439cc887bfd82226f5af746d6977bd9f66844",
                "sha256:e0a9a1a39d4bf3517f2af9d23d479b4175ead205c592ceeb8b89af48a327ea57",
                "sha256:eccce86bba940bae0d8d48ed925f21dbb813519169246e2ab292b5092aba121f",
                "sha256:f99b600aa7f65235a5a05d0b9a9f31150c390f31261f2a0ba678e26823ec38f7"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==0.43.0"
        },
        "locket": {
            "hashes": [
                "sha256:5c0d4c052a8bbbf750e056a8e65ccd309086f4f0f18a2eac306a8dfa4112a632",
                "sha256:b6c819a722f7b6bd955b80781788e4a66a55628b858d347536b7e81325a3a5e3"
            ],
            "index": "pypi",
            "markers": "python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
            "version": "==1.0.0"
        },
        "lxml": {
            "hashes": [
                "sha256:04ab5415bf6c86e0518d57240a96c4d1fcfc3cb370bb2ac2a732b67f579e5a04",
                "sha256:057cdc6b86ab732cf361f8b4d8af87cf195a1f6dc5b0ff3de2dced242c2015e0",
                "sha256:058a1308914f20784c9f4674036527e7c04f7be6fb60f5d61353545aa7fcb739",
                "sha256:08802f0c56ed150cc6885ae0788a321b73505d2263ee56dad84d200cab11c07a",
                "sha256:0a15438253b34e6362b2dc41475e7f80de76320f335e70c5528b7148cac253a1",
                "sha256:0c3f67e2aeda739d1cc0b1102c9a9129f7dc83901226cc24dd72ba275ced4218",
                "sha256:0e7259016bc4345a31af861fdce942b77c99049d6c2107ca07dc2bba2435c1d9",
                "sha256:0ed777c1e8c99b63037b91f9d73a6aad20fd035d77ac84afcc205225f8f41188",
                "sha256:0f5d65c39f16717a47c36c756af0fb36144069c4718824b7533f803ecdf91138",
                "sha256:0f8c09ed18ecb4ebf23e02b8e7a22a05d6411911e6fabef3a36e4f371f4f2585",
                "sha256:11a04306fcba10cd9637e669fd73aa274c1c09ca64af79c041aa820ea992b637",
                "sha256:1ae67b4e737cddc96c99461d2f75d218bdf7a0c3d3ad5604d1f5e7464a2f9ffe",
                "sha256:1c5bb205e9212d0ebddf946bc07e73fa245c864a5f90f341d11ce7b0b854475d",
                "sha256:1f7785f4f789fdb522729ae465adcaa099e2a3441519df750ebdccc481d961a1",
                "sha256:200e63525948e325d6a13a76ba2911f927ad399ef64f57898cf7c74e69b71095",
                "sha256:21c2e6b09565ba5b45ae161b438e033a86ad1736b8c838c766146eff8ceffff9",
                "sha256:2213afee476546a7f37c7a9b4ad4d74b1e112a6fafffc9185d6d21f043128c81",
                "sha256:27aa20d45c2e0b8cd05da6d4759649170e8dfc4f4e5ef33a34d06f2d79075d57",
                "sha256:2a66bf12fbd4666dd023b6f51223aed3d9f3b40fef06ce404cb75bafd3d89536",
                "sha256:2c9d147f754b1b0e723e6afb7ba1566ecb162fe4ea657f53d2139bbf894d050a",
                "sha256:2ddfe41ddc81f29a4c44c8ce239eda5ade4e7fc305fb7311759dd6229a080052",
                "sha256:31e9a882013c2f6bd2f2c974241bf4ba68c85eba943648ce88936d23209a2e01",
                "sha256:3249cc2989d9090eeac5467e50e9ec2d40704fea9ab72f36b034ea34ee65ca98",
                "sha256:3545039fa4779be2df51d6395e91a810f57122290864918b172d5dc7ca5bb433",
                "sha256:394ed3924d7a01b5bd9a0d9d946136e1c2f7b3dc337196d99e61740ed4bc6fe1",
                "sha256:3a6b45da02336895da82b9d472cd274b22dc27a5cea1d4b793874eead23dd14f",
                "sha256:3a74c4f27167cb95c1d4af1c0b59e88b7f3e0182138db2501c353555f7ec57f4",
                "sha256:3d0c3dd24bb4605439bf91068598d00c6370684f8de4a67c2992683f6c309d6b",
                "sha256:3dbe858ee582cbb2c6294dc85f55b5f19c918c2597855e950f34b660f1a5ede6",
                "sha256:3dc773b2861b37b41a6136e0b72a1a44689a9c4c101e0cddb6b854016acc0aa8",
                "sha256:3f7765e69bbce0906a7c74d5fe46d2c7a7596147318dbc08e4a2431f3060e306",
                "sha256:417d14450f06d51f363e41cace6488519038f940676ce9664b34ebf5653433a5",
                "sha256:44f6c7caff88d988db017b9b0e4ab04934f11e3e72d478031efc7edcac6c622f",
                "sha256:491755202eb21a5e350dae00c6d9a17247769c64dcf62d8c788b5c135e179dc4",
                "sha256:4951e4f7a5680a2db62f7f4ab2f84617674d36d2d76a729b9a8be4b59b3659be",
                "sha256:52421b41ac99e9d91934e4d0d0fe7da9f02bfa7536bb4431b4c05c906c8c6919",
                "sha256:530e7c04f72002d2f334d5257c8a51bf409db0316feee7c87e4385043be136af",
                "sha256:533658f8fbf056b70e434dff7e7aa611bcacb33e01f75de7f821810e48d1bb66",
                "sha256:5670fb70a828663cc37552a2a85bf2ac38475572b0e9b91283dc09efb52c41d1",
                "sha256:56c22432809085b3f3ae04e6e7bdd36883d7258fcd90e53ba7b2e463efc7a6af",
                "sha256:58278b29cb89f3e43ff3e0c756abbd1518f3ee6adad9e35b51fb101c1c1daaec",
                "sha256:588008b8497667f1ddca7c99f2f85ce8511f8f7871b4a06ceede68ab62dff64b",
                "sha256:59565f10607c244bc4c05c0c5fa0c190c990996e0c719d05deec7030c2aa8289",
                "sha256:59689a75ba8d7ffca577aefd017d08d659d86ad4585ccc73e43edbfc7476781a",
                "sha256:5aea8212fb823e006b995c4dda533edcf98a893d941f173f6c9506126188860d",
                "sha256:5c670c0406bdc845b474b680b9a5456c561c65cf366f8db5a60154088c92d102",
                "sha256:5ca1e8188b26a819387b29c3895c47a5e618708fe6f787f3b1a471de2c4a94d9",
                "sha256:5d077bc40a1fe984e1a9931e801e42959a1e6598edc8a3223b061d30fbd26bbc",
                "sha256:5d5792e9b3fb8d16a19f46aa8208987cfeafe082363ee2745ea8b643d9cc5b45",
                "sha256:5dd1537e7cc06efd81371f5d1a992bd5ab156b2b4f88834ca852de4a8ea523fa",
                "sha256:5ea7b6766ac2dfe4bcac8b8595107665a18ef01f8c8343f00710b85096d1b53a",
                "sha256:622020d4521e22fb371e15f580d153134bfb68d6a429d1342a25f051ec72df1c",
                "sha256:627402ad8dea044dde2eccde4370560a2b750ef894c9578e1d4f8ffd54000461",
                "sha256:644df54d729ef810dcd0f7732e50e5ad1bd0a135278ed8d6bcb06f33b6b6f708",
                "sha256:64641a6068a16201366476731301441ce93457eb8452056f570133a6ceb15fca",
                "sha256:64c2baa7774bc22dd4474248ba16fe1a7f611c13ac6123408694d4cc93d66dbd",
                "sha256:6588c459c5627fefa30139be4d2e28a2c2a1d0d1c265aad2ba1935a7863a4913",
                "sha256:66bc5eb8a323ed9894f8fa0ee6cb3e3fb2403d99aee635078fd19a8bc7a5a5da",
                "sha256:68a2610dbe138fa8c5826b3f6d98a7cfc29707b850ddcc3e21910a6fe51f6ca0",
                "sha256:6935bbf153f9a965f1e07c2649c0849d29832487c52bb4a5c5066031d8b44fd5",
                "sha256:6992030d43b916407c9aa52e9673612ff39a575523c5f4cf72cdef75365709a5",
                "sha256:6a014510830df1475176466b6087fc0c08b47a36714823e58d8b8d7709132a96",
                "sha256:6ab833e4735a7e5533711a6ea2df26459b96f9eec36d23f74cafe03631647c41",
                "sha256:6cc6ee342fb7fa2471bd9b6d6fdfc78925a697bf5c2bcd0a302e98b0d35bfad3",
                "sha256:6cf58416653c5901e12624e4013708b6e11142956e7f35e7a83f1ab02f3fe456",
                "sha256:70a9768e1b9d79edca17890175ba915654ee1725975d69ab64813dd785a2bd5c",
                "sha256:70ac664a48aa64e5e635ae5566f5227f2ab7f66a3990d67566d9907edcbbf867",
                "sha256:71e97313406ccf55d32cc98a533ee05c61e15d11b99215b237346171c179c0b0",
                "sha256:7221d49259aa1e5a8f00d3d28b1e0b76031655ca74bb287123ef56c3db92f213",
                "sha256:74b28c6334cca4dd704e8004cba1955af0b778cf449142e581e404bd211fb619",
                "sha256:764b521b75701f60683500d8621841bec41a65eb739b8466000c6fdbc256c240",
                "sha256:78bfa756eab503673991bdcf464917ef7845a964903d3302c5f68417ecdc948c",
                "sha256:794f04eec78f1d0e35d9e0c36cbbb22e42d370dda1609fb03bcd7aeb458c6377",
                "sha256:79bd05260359170f78b181b59ce871673ed01ba048deef4bf49a36ab3e72e80b",
                "sha256:7a7efd5b6d3e30d81ec68ab8a88252d7c7c6f13aaa875009fe3097eb4e30b84c",
                "sha256:7c17b64b0a6ef4e5affae6a3724010a7a66bda48a62cfe0674dabd46642e8b54",
                "sha256:804f74efe22b6a227306dd890eecc4f8c59ff25ca35f1f14e7482bbce96ef10b",
                "sha256:853e074d4931dbcba7480d4dcab23d5c56bd9607f92825ab80ee2bd916edea53",
                "sha256:857500f88b17a6479202ff5fe5f580fc3404922cd02ab3716197adf1ef628029",
                "sha256:865bad62df277c04beed9478fe665b9ef63eb28fe026d5dedcb89b537d2e2ea6",
                "sha256:88e22fc0a6684337d25c994381ed8a1580a6f5ebebd5ad41f89f663ff4ec2885",
                "sha256:8b9c07e7a45bb64e21df4b6aa623cb8ba214dfb47d2027d90eac197329bb5e94",
                "sha256:8de8f9d6caa7f25b204fc861718815d41cbcf27ee8f028c89c882a0cf4ae4134",
                "sha256:8e77c69d5892cb5ba71703c4057091e31ccf534bd7f129307a4d084d90d014b8",
                "sha256:9123716666e25b7b71c4e1789ec829ed18663152008b58544d95b008ed9e21e9",
                "sha256:958244ad566c3ffc385f47dddde4145088a0ab893504b54b52c041987a8c1863",
                "sha256:96323338e6c14e958d775700ec8a88346014a85e5de73ac7967db0367582049b",
                "sha256:9676bfc686fa6a3fa10cd4ae6b76cae8be26eb5ec6811d2a325636c460da1806",
                "sha256:9b0ff53900566bc6325ecde9181d89afadc59c5ffa39bddf084aaedfe3b06a11",
                "sha256:9b9ec9c9978b708d488bec36b9e4c94d88fd12ccac3e62134a9d17ddba910ea9",
                "sha256:9c6ad0fbf105f6bcc9300c00010a2ffa44ea6f555df1a2ad95c88f5656104817",
                "sha256:9ca66b8e90daca431b7ca1408cae085d025326570e57749695d6a01454790e95",
                "sha256:9e2addd2d1866fe112bc6f80117bcc6bc25191c5ed1bfbcf9f1386a884252ae8",
                "sha256:a0af35bd8ebf84888373630f73f24e86bf016642fb8576fba49d3d6b560b7cbc",
                "sha256:a2b44bec7adf3e9305ce6cbfa47a4395667e744097faed97abb4728748ba7d47",
                "sha256:a2dfe7e2473f9b59496247aad6e23b405ddf2e12ef0765677b0081c02d6c2c0b",
                "sha256:a55ee573116ba208932e2d1a037cc4b10d2c1cb264ced2184d00b18ce585b2c0",
                "sha256:a7baf9ffc238e4bf401299f50e971a45bfcc10a785522541a6e3179c83eabf0a",
                "sha256:a8d5c70e04aac1eda5c829a26d1f75c6e5286c74743133d9f742cda8e53b9c2f",
                "sha256:a91481dbcddf1736c98a80b122afa0f7296eeb80b72344d7f45dc9f781551f56",
                "sha256:ab31a88a651039a07a3ae327d68ebdd8bc589b16938c09ef3f32a4b809dc96ef",
                "sha256:abc25c3cab9ec7fcd299b9bcb3b8d4a1231877e425c650fa1c7576c5107ab851",
                "sha256:adfb84ca6b87e06bc6b146dc7da7623395db1e31621c4785ad0658c5028b37d7",
                "sha256:afbbdb120d1e78d2ba8064a68058001b871154cc57787031b645c9142b937a62",
                "sha256:afd5562927cdef7c4f5550374acbc117fd4ecc05b5007bdfa57cc5355864e0a4",
                "sha256:b070bbe8d3f0f6147689bed981d19bbb33070225373338df755a46893528104a",
                "sha256:b0b58fbfa1bf7367dde8a557994e3b1637294be6cf2169810375caf8571a085c",
                "sha256:b560e3aa4b1d49e0e6c847d72665384db35b2f5d45f8e6a5c0072e0283430533",
                "sha256:b6241d4eee5f89453307c2f2bfa03b50362052ca0af1efecf9fef9a41a22bb4f",
                "sha256:b6787b643356111dfd4032b5bffe26d2f8331556ecb79e15dacb9275da02866e",
                "sha256:bcbf4af004f98793a95355980764b3d80d47117678118a44a80b721c9913436a",
                "sha256:beb72935a941965c52990f3a32d7f07ce869fe21c6af8b34bf6a277b33a345d3",
                "sha256:bf2e2458345d9bffb0d9ec16557d8858c9c88d2d11fed53998512504cd9df49b",
                "sha256:c2d35a1d047efd68027817b32ab1586c1169e60ca02c65d428ae815b593e65d4",
                "sha256:c38d7b9a690b090de999835f0443d8aa93ce5f2064035dfc48f27f02b4afc3d0",
                "sha256:c6f2c8372b98208ce609c9e1d707f6918cc118fea4e2c754c9f0812c04ca116d",
                "sha256:c817d420c60a5183953c783b0547d9eb43b7b344a2c46f69513d5952a78cddf3",
                "sha256:c8ba129e6d3b0136a0f50345b2cb3db53f6bda5dd8c7f5d83fbccba97fb5dcb5",
                "sha256:c94e75445b00319c1fad60f3c98b09cd63fe1134a8a953dcd48989ef42318534",
                "sha256:cc4691d60512798304acb9207987e7b2b7c44627ea88b9d77489bbe3e6cc3bd4",
                "sha256:cc518cea79fd1e2f6c90baafa28906d4309d24f3a63e801d855e7424c5b34144",
                "sha256:cd53553ddad4a9c2f1f022756ae64abe16da1feb497edf4d9f87f99ec7cf86bd",
                "sha256:cf22b41fdae514ee2f1691b6c3cdeae666d8b7fa9434de445f12bbeee0cf48dd",
                "sha256:d38c8f50ecf57f0463399569aa388b232cf1a2ffb8f0a9a5412d0db57e054860",
                "sha256:d3be9b2076112e51b323bdf6d5a7f8a798de55fb8d95fcb64bd179460cdc0704",
                "sha256:d4f2cc7060dc3646632d7f15fe68e2fa98f58e35dd5666cd525f3b35d3fed7f8",
                "sha256:d7520db34088c96cc0e0a3ad51a4fd5b401f279ee112aa2b7f8f976d8582606d",
                "sha256:d793bebb202a6000390a5390078e945bbb49855c29c7e4d56a85901326c3b5d9",
                "sha256:da052e7962ea2d5e5ef5bc0355d55007407087392cf465b7ad84ce5f3e25fe0f",
                "sha256:dae0ed02f6b075426accbf6b2863c3d0a7eacc1b41fb40f2251d931e50188dad",
                "sha256:ddc678fb4c7e30cf830a2b5a8d869538bc55b28d6c68544d09c7d0d8f17694dc",
                "sha256:df2e6f546c4df14bc81f9498bbc007fbb87669f1bb707c6138878c46b06f6510",
                "sha256:e02c5175f63effbd7c5e590399c118d5db6183bbfe8e0d118bdb5c2d1b48d937",
                "sha256:e196a4ff48310ba62e53a8e0f97ca2bca83cdd2fe2934d8b5cb0df0a841b193a",
                "sha256:e233db59c8f76630c512ab4a4daf5a5986da5c3d5b44b8e9fc742f2a24dbd460",
                "sha256:e32be23d538753a8adb6c85bd539f5fd3b15cb987404327c569dfc5fd8366e85",
                "sha256:e3d30321949861404323c50aebeb1943461a67cd51d4200ab02babc58bd06a86",
                "sha256:e89580a581bf478d8dcb97d9cd011d567768e8bc4095f8557b21c4d4c5fea7d0",
                "sha256:e998e304036198b4f6914e6a1e2b6f925208a20e2042563d9734881150c6c246",
                "sha256:ec42088248c596dbd61d4ae8a5b004f97a4d91a9fd286f632e42e60b706718d7",
                "sha256:efa7b51824aa0ee957ccd5a741c73e6851de55f40d807f08069eb4c5a26b2baa",
                "sha256:f0a1bc63a465b6d72569a9bba9f2ef0334c4e03958e043da1920299100bc7c08",
                "sha256:f18a5a84e16886898e51ab4b1d43acb3083c39b14c8caeb3589aabff0ee0b270",
                "sha256:f2a9efc53d5b714b8df2b4b3e992accf8ce5bbdfe544d74d5c6766c9e1146a3a",
                "sha256:f3bbbc998d42f8e561f347e798b85513ba4da324c2b3f9b7969e9c45b10f6169",
                "sha256:f42038016852ae51b4088b2862126535cc4fc85802bfe30dea3500fdfaf1864e",
                "sha256:f443cdef978430887ed55112b491f670bba6462cea7a7742ff8f14b7abb98d75",
                "sha256:f51969bac61441fd31f028d7b3b45962f3ecebf691a510495e5d2cd8c8092dbd",
                "sha256:f8aca2e3a72f37bfc7b14ba96d4056244001ddcc18382bd0daa087fd2e68a354",
                "sha256:f9737bf36262046213a28e789cc82d82c6ef19c85a0cf05e75c670a33342ac2c",
                "sha256:fd6037392f2d57793ab98d9e26798f44b8b4da2f2464388588f48ac52c489ea1",
                "sha256:feaa45c0eae424d3e90d78823f3828e7dc42a42f21ed420db98da2c4ecf0a2cb",
                "sha256:ff097ae562e637409b429a7ac958a20aab237a0378c42dabaa1e3abf2f896e5f",
                "sha256:ff46d772d5f6f73564979cd77a4fffe55c916a05f3cb70e7c9c0590059fb29ef"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==5.2.1"
        },
        "markdown": {
            "hashes": [
                "sha256:2ae2471477cfd02dbbf038d5d9bc226d40def84b4fe2986e49b59b6b472bbed2",
                "sha256:7eb6df5690b81a1d7942992c97fad2938e956e79df20cbc6186e9c3a77b1c803"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.7"
        },
        "markdown-it-py": {
            "hashes": [
                "sha256:355216845c60bd96232cd8d8c40e8f9765cc86f46880e43a8fd22dc1a1a8cab1",
                "sha256:e3f60a94fa066dc52ec76661e37c851cb232d92f9886b15cb560aaada2df8feb"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.0.0"
        },
        "markupsafe": {
            "hashes": [
                "sha256:00e046b6dd71aa03a41079792f8473dc494d564611a8f89bbbd7cb93295ebdcf",
                "sha256:075202fa5b72c86ad32dc7d0b56024ebdbcf2048c0ba09f1cde31bfdd57bcfff",
                "sha256:0e397ac966fdf721b2c528cf028494e86172b4feba51d65f81ffd65c63798f3f",
                "sha256:17b950fccb810b3293638215058e432159d2b71005c74371d784862b7e4683f3",
                "sha256:1f3fbcb7ef1f16e48246f704ab79d79da8a46891e2da03f8783a5b6fa41a9532",
                "sha256:2174c595a0d73a3080ca3257b40096db99799265e1c27cc5a610743acd86d62f",
                "sha256:2b7c57a4dfc4f16f7142221afe5ba4e093e09e728ca65c51f5620c9aaeb9a617",
                "sha256:2d2d793e36e230fd32babe143b04cec8a8b3eb8a3122d2aceb4a371e6b09b8df",
                "sha256:30b600cf0a7ac9234b2638fbc0fb6158ba5bdcdf46aeb631ead21248b9affbc4",
                "sha256:397081c1a0bfb5124355710fe79478cdbeb39626492b15d399526ae53422b906",
                "sha256:3a57fdd7ce31c7ff06cdfbf31dafa96cc533c21e443d57f5b1ecc6cdc668ec7f",
                "sha256:3c6b973f22eb18a789b1460b4b91bf04ae3f0c4234a0a6aa6b0a92f6f7b951d4",
                "sha256:3e53af139f8579a6d5f7b76549125f0d94d7e630761a2111bc431fd820e163b8",
                "sha256:4096e9de5c6fdf43fb4f04c26fb114f61ef0bf2e5604b6ee3019d51b69e8c371",
                "sha256:4275d846e41ecefa46e2015117a9f491e57a71ddd59bbead77e904dc02b1bed2",
                "sha256:4c31f53cdae6ecfa91a77820e8b151dba54ab528ba65dfd235c80b086d68a465",
                "sha256:4f11aa001c540f62c6166c7726f71f7573b52c68c31f014c25cc7901deea0b52",
                "sha256:5049256f536511ee3f7e1b3f87d1d1209d327e818e6ae1365e8653d7e3abb6a6",
                "sha256:58c98fee265677f63a4385256a6d7683ab1832f3ddd1e66fe948d5880c21a169",
                "sha256:598e3276b64aff0e7b3451b72e94fa3c238d452e7ddcd893c3ab324717456bad",
                "sha256:5b7b716f97b52c5a14bffdf688f971b2d5ef4029127f1ad7a513973cfd818df2",
                "sha256:5dedb4db619ba5a2787a94d877bc8ffc0566f92a01c0ef214865e54ecc9ee5e0",
                "sha256:619bc166c4f2de5caa5a633b8b7326fbe98e0ccbfacabd87268a2b15ff73a029",
                "sha256:629ddd2ca402ae6dbedfceeba9c46d5f7b2a61d9749597d4307f943ef198fc1f",
                "sha256:656f7526c69fac7f600bd1f400991cc282b417d17539a1b228617081106feb4a",
                "sha256:6ec585f69cec0aa07d945b20805be741395e28ac1627333b1c5b0105962ffced",
                "sha256:72b6be590cc35924b02c78ef34b467da4ba07e4e0f0454a2c5907f473fc50ce5",
                "sha256:7502934a33b54030eaf1194c21c692a534196063db72176b0c4028e140f8f32c",
                "sha256:7a68b554d356a91cce1236aa7682dc01df0edba8d043fd1ce607c49dd3c1edcf",
                "sha256:7b2e5a267c855eea6b4283940daa6e88a285f5f2a67f2220203786dfa59b37e9",
                "sha256:823b65d8706e32ad2df51ed89496147a42a2a6e01c13cfb6ffb8b1e92bc910bb",
                "sha256:8590b4ae07a35970728874632fed7bd57b26b0102df2d2b233b6d9d82f6c62ad",
                "sha256:8dd717634f5a044f860435c1d8c16a270ddf0ef8588d4887037c5028b859b0c3",
                "sha256:8dec4936e9c3100156f8a2dc89c4b88d5c435175ff03413b443469c7c8c5f4d1",
                "sha256:97cafb1f3cbcd3fd2b6fbfb99ae11cdb14deea0736fc2b0952ee177f2b813a46",
                "sha256:a17a92de5231666cfbe003f0e4b9b3a7ae3afb1ec2845aadc2bacc93ff85febc",
                "sha256:a549b9c31bec33820e885335b451286e2969a2d9e24879f83fe904a5ce59d70a",
                "sha256:ac07bad82163452a6884fe8fa0963fb98c2346ba78d779ec06bd7a6262132aee",
                "sha256:ae2ad8ae6ebee9d2d94b17fb62763125f3f374c25618198f40cbb8b525411900",
                "sha256:b91c037585eba9095565a3556f611e3cbfaa42ca1e865f7b8015fe5c7336d5a5",
                "sha256:bc1667f8b83f48511b94671e0e441401371dfd0f0a795c7daa4a3cd1dde55bea",
                "sha256:bec0a414d016ac1a18862a519e54b2fd0fc8bbfd6890376898a6c0891dd82e9f",
                "sha256:bf50cd79a75d181c9181df03572cdce0fbb75cc353bc350712073108cba98de5",
                "sha256:bff1b4290a66b490a2f4719358c0cdcd9bafb6b8f061e45c7a2460866bf50c2e",
                "sha256:c061bb86a71b42465156a3ee7bd58c8c2ceacdbeb95d05a99893e08b8467359a",
                "sha256:c8b29db45f8fe46ad280a7294f5c3ec36dbac9491f2d1c17345be8e69cc5928f",
                "sha256:ce409136744f6521e39fd8e2a24c53fa18ad67aa5bc7c2cf83645cce5b5c4e50",
                "sha256:d050b3361367a06d752db6ead6e7edeb0009be66bc3bae0ee9d97fb326badc2a",
                "sha256:d283d37a890ba4c1ae73ffadf8046435c76e7bc2247bbb63c00bd1a709c6544b",
                "sha256:d9fad5155d72433c921b782e58892377c44bd6252b5af2f67f16b194987338a4",
                "sha256:daa4ee5a243f0f20d528d939d06670a298dd39b1ad5f8a72a4275124a7819eff",
                "sha256:db0b55e0f3cc0be60c1f19efdde9a637c32740486004f20d1cff53c3c0ece4d2",
                "sha256:e61659ba32cf2cf1481e575d0462554625196a1f2fc06a1c777d3f48e8865d46",
                "sha256:ea3d8a3d18833cf4304cd2fc9cbb1efe188ca9b5efef2bdac7adc20594a0e46b",
                "sha256:ec6a563cff360b50eed26f13adc43e61bc0c04d94b8be985e6fb24b81f6dcfdf",
                "sha256:f5dfb42c4604dddc8e4305050aa6deb084540643ed5804d7455b5df8fe16f5e5",
                "sha256:fa173ec60341d6bb97a89f5ea19c85c5643c1e7dedebc22f5181eb73573142c5",
                "sha256:fa9db3f79de01457b03d4f01b34cf91bc0048eb2c3846ff26f66687c2f6d16ab",
                "sha256:fce659a462a1be54d2ffcacea5e3ba2d74daa74f30f5f143fe0c58636e355fdd",
                "sha256:ffee1f21e5ef0d712f9033568f8344d5da8cc2869dbd08d87c84656e6a2d2f68"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==2.1.5"
        },
        "matplotlib": {
            "hashes": [
                "sha256:026bdf3137ab6022c866efa4813b6bbeddc2ed4c9e7e02f0e323a7bca380dfa0",
                "sha256:031b7f5b8e595cc07def77ec5b58464e9bb67dc5760be5d6f26d9da24892481d",
                "sha256:0a0a63cb8404d1d1f94968ef35738900038137dab8af836b6c21bb6f03d75465",
                "sha256:0a361bd5583bf0bcc08841df3c10269617ee2a36b99ac39d455a767da908bbbc",
                "sha256:10d3e5c7a99bd28afb957e1ae661323b0800d75b419f24d041ed1cc5d844a764",
                "sha256:1c40c244221a1adbb1256692b1133c6fb89418df27bf759a31a333e7912a4010",
                "sha256:203d18df84f5288973b2d56de63d4678cc748250026ca9e1ad8f8a0fd8a75d83",
                "sha256:213d6dc25ce686516208d8a3e91120c6a4fdae4a3e06b8505ced5b716b50cc04",
                "sha256:3119b2f16de7f7b9212ba76d8fe6a0e9f90b27a1e04683cd89833a991682f639",
                "sha256:3fb0b37c896172899a4a93d9442ffdc6f870165f59e05ce2e07c6fded1c15749",
                "sha256:41b016e3be4e740b66c79a031a0a6e145728dbc248142e751e8dab4f3188ca1d",
                "sha256:4a8d279f78844aad213c4935c18f8292a9432d51af2d88bca99072c903948045",
                "sha256:4e6eefae6effa0c35bbbc18c25ee6e0b1da44d2359c3cd526eb0c9e703cf055d",
                "sha256:5f2a4ea08e6876206d511365b0bc234edc813d90b930be72c3011bbd7898796f",
                "sha256:66d7b171fecf96940ce069923a08ba3df33ef542de82c2ff4fe8caa8346fa95a",
                "sha256:687df7ceff57b8f070d02b4db66f75566370e7ae182a0782b6d3d21b0d6917dc",
                "sha256:6be0ba61f6ff2e6b68e4270fb63b6813c9e7dec3d15fc3a93f47480444fd72f0",
                "sha256:6e9de2b390d253a508dd497e9b5579f3a851f208763ed67fdca5dc0c3ea6849c",
                "sha256:760a5e89ebbb172989e8273024a1024b0f084510b9105261b3b00c15e9c9f006",
                "sha256:816a966d5d376bf24c92af8f379e78e67278833e4c7cbc9fa41872eec629a060",
                "sha256:87ad73763d93add1b6c1f9fcd33af662fd62ed70e620c52fcb79f3ac427cf3a6",
                "sha256:896774766fd6be4571a43bc2fcbcb1dcca0807e53cab4a5bf88c4aa861a08e12",
                "sha256:8e0143975fc2a6d7136c97e19c637321288371e8f09cff2564ecd73e865ea0b9",
                "sha256:90a85a004fefed9e583597478420bf904bb1a065b0b0ee5b9d8d31b04b0f3f70",
                "sha256:9b081dac96ab19c54fd8558fac17c9d2c9cb5cc4656e7ed3261ddc927ba3e2c5",
                "sha256:9d6b2e8856dec3a6db1ae51aec85c82223e834b228c1d3228aede87eee2b34f9",
                "sha256:9f459c8ee2c086455744723628264e43c884be0c7d7b45d84b8cd981310b4815",
                "sha256:9fa6e193c14d6944e0685cdb527cb6b38b0e4a518043e7212f214113af7391da",
                "sha256:a42b9dc42de2cfe357efa27d9c50c7833fc5ab9b2eb7252ccd5d5f836a84e1e4",
                "sha256:b651b0d3642991259109dc0351fc33ad44c624801367bb8307be9bfc35e427ad",
                "sha256:b6c12514329ac0d03128cf1dcceb335f4fbf7c11da98bca68dca8dcb983153a9",
                "sha256:c52f48eb75fcc119a4fdb68ba83eb5f71656999420375df7c94cc68e0e14686e",
                "sha256:c96eeeb8c68b662c7747f91a385688d4b449687d29b691eff7068a4602fe6dc4",
                "sha256:cd1077b9a09b16d8c3c7075a8add5ffbfe6a69156a57e290c800ed4d435bef1d",
                "sha256:cd5dbbc8e25cad5f706845c4d100e2c8b34691b412b93717ce38d8ae803bcfa5",
                "sha256:cf2a60daf6cecff6828bc608df00dbc794380e7234d2411c0ec612811f01969d",
                "sha256:d3c93796b44fa111049b88a24105e947f03c01966b5c0cc782e2ee3887b790a3",
                "sha256:d796272408f8567ff7eaa00eb2856b3a00524490e47ad505b0b4ca6bb8a7411f",
                "sha256:e0fcb7da73fbf67b5f4bdaa57d85bb585a4e913d4a10f3e15b32baea56a67f0a",
                "sha256:e14485bb1b83eeb3d55b6878f9560240981e7bbc7a8d4e1e8c38b9bd6ec8d2de",
                "sha256:edd14cf733fdc4f6e6fe3f705af97676a7e52859bf0044aa2c84e55be739241c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==3.9.3"
        },
        "matplotlib-inline": {
            "hashes": [
                "sha256:8423b23ec666be3d16e16b60bdd8ac4e86e840ebd1dd11a30b9f117f2fa0ab90",
                "sha256:df192d39a4ff8f21b1895d72e6a13f5fcc5099f00fa84384e0ea28c2cc0653ca"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.1.7"
        },
        "mdit-py-plugins": {
            "hashes": [
                "sha256:0c673c3f889399a33b95e88d2f0d111b4447bdfea7f237dab2d488f459835636",
                "sha256:5f2cd1fdb606ddf152d37ec30e46101a60512bc0e5fa1a7002c36647b09e26b5"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.4.2"
        },
        "mdurl": {
            "hashes": [
                "sha256:84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8",
                "sha256:bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==0.1.2"
        },
        "ml-dtypes": {
            "hashes": [
                "sha256:126e7d679b8676d1a958f2651949fbfa182832c3cd08020d8facd94e4114f3e9",
                "sha256:15fdd922fea57e493844e5abb930b9c0bd0af217d9edd3724479fc3d7ce70e3f",
                "sha256:1fe8b5b5e70cd67211db94b05cfd58dace592f24489b038dc6f9fe347d2e07d5",
                "sha256:274cc7193dd73b35fb26bef6c5d40ae3eb258359ee71cd82f6e96a8c948bdaa6",
                "sha256:2d55b588116a7085d6e074cf0cdb1d6fa3875c059dddc4d2c94a4cc81c23e975",
                "sha256:560be16dc1e3bdf7c087eb727e2cf9c0e6a3d87e9f415079d2491cc419b3ebf5",
                "sha256:74c6cfb5cf78535b103fde9ea3ded8e9f16f75bc07789054edc7776abfb3d752",
                "sha256:772426b08a6172a891274d581ce58ea2789cc8abc1c002a27223f314aaf894e7",
                "sha256:827d3ca2097085cf0355f8fdf092b888890bb1b1455f52801a2d7756f056f54b",
                "sha256:8c09a6d11d8475c2a9fd2bc0695628aec105f97cab3b3a3fb7c9660348ff7d24",
                "sha256:9f5e8f75fa371020dd30f9196e7d73babae2abd51cf59bdd56cb4f8de7e13354",
                "sha256:ad0b757d445a20df39035c4cdeed457ec8b60d236020d2560dbc25887533cf50",
                "sha256:df0fb650d5c582a9e72bb5bd96cfebb2cdb889d89daff621c8fbc60295eba66c",
                "sha256:e138a9b7a48079c900ea969341a5754019a1ad17ae27ee330f7ebf43f23877f9",
                "sha256:e35e486e97aee577d0890bc3bd9e9f9eece50c08c163304008587ec8cfe7575b",
                "sha256:ef0d7e3fece227b49b544fa69e50e607ac20948f0043e9f76b44f35f229ea450",
                "sha256:fad5f2de464fd09127e49b7fd1252b9006fb43d2edc1ff112d390c324af5ca7a"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==0.4.1"
        },
        "mpl-interactions": {
            "hashes": [
                "sha256:2ef91b44bd3fb88395d7ea0bae862b7c987004d87dfb478c8bc1655999a3c2e1",
                "sha256:bacda7af49007096942d01a4973e7df5b52afaa8385a688a383e34ffee6105d3"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==0.24.2"
        },
        "mpmath": {
            "hashes": [
                "sha256:7a28eb2a9774d00c7bc92411c19a89209d5da7c4c9a9e227be8330a23a25b91f",
                "sha256:a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c"
            ],
            "index": "pypi",
            "version": "==1.3.0"
        },
        "msgpack": {
            "hashes": [
                "sha256:00e073efcba9ea99db5acef3959efa45b52bc67b61b00823d2a1a6944bf45982",
                "sha256:0726c282d188e204281ebd8de31724b7d749adebc086873a59efb8cf7ae27df3",
                "sha256:0ceea77719d45c839fd73abcb190b8390412a890df2f83fb8cf49b2a4b5c2f40",
                "sha256:114be227f5213ef8b215c22dde19532f5da9652e56e8ce969bf0a26d7c419fee",
                "sha256:13577ec9e247f8741c84d06b9ece5f654920d8365a4b636ce0e44f15e07ec693",
                "sha256:1876b0b653a808fcd50123b953af170c535027bf1d053b59790eebb0aeb38950",
                "sha256:1ab0bbcd4d1f7b6991ee7c753655b481c50084294218de69365f8f1970d4c151",
                "sha256:1cce488457370ffd1f953846f82323cb6b2ad2190987cd4d70b2713e17268d24",
                "sha256:26ee97a8261e6e35885c2ecd2fd4a6d38252246f94a2aec23665a4e66d066305",
                "sha256:3528807cbbb7f315bb81959d5961855e7ba52aa60a3097151cb21956fbc7502b",
                "sha256:374a8e88ddab84b9ada695d255679fb99c53513c0a51778796fcf0944d6c789c",
                "sha256:376081f471a2ef24828b83a641a02c575d6103a3ad7fd7dade5486cad10ea659",
                "sha256:3923a1778f7e5ef31865893fdca12a8d7dc03a44b33e2a5f3295416314c09f5d",
                "sha256:4916727e31c28be8beaf11cf117d6f6f188dcc36daae4e851fee88646f5b6b18",
                "sha256:493c5c5e44b06d6c9268ce21b302c9ca055c1fd3484c25ba41d34476c76ee746",
                "sha256:505fe3d03856ac7d215dbe005414bc28505d26f0c128906037e66d98c4e95868",
                "sha256:5845fdf5e5d5b78a49b826fcdc0eb2e2aa7191980e3d2cfd2a30303a74f212e2",
                "sha256:5c330eace3dd100bdb54b5653b966de7f51c26ec4a7d4e87132d9b4f738220ba",
                "sha256:5dbf059fb4b7c240c873c1245ee112505be27497e90f7c6591261c7d3c3a8228",
                "sha256:5e390971d082dba073c05dbd56322427d3280b7cc8b53484c9377adfbae67dc2",
                "sha256:5fbb160554e319f7b22ecf530a80a3ff496d38e8e07ae763b9e82fadfe96f273",
                "sha256:64d0fcd436c5683fdd7c907eeae5e2cbb5eb872fafbc03a43609d7941840995c",
                "sha256:69284049d07fce531c17404fcba2bb1df472bc2dcdac642ae71a2d079d950653",
                "sha256:6a0e76621f6e1f908ae52860bdcb58e1ca85231a9b0545e64509c931dd34275a",
                "sha256:73ee792784d48aa338bba28063e19a27e8d989344f34aad14ea6e1b9bd83f596",
                "sha256:74398a4cf19de42e1498368c36eed45d9528f5fd0155241e82c4082b7e16cffd",
                "sha256:7938111ed1358f536daf311be244f34df7bf3cdedb3ed883787aca97778b28d8",
                "sha256:82d92c773fbc6942a7a8b520d22c11cfc8fd83bba86116bfcf962c2f5c2ecdaa",
                "sha256:83b5c044f3eff2a6534768ccfd50425939e7a8b5cf9a7261c385de1e20dcfc85",
                "sha256:8db8e423192303ed77cff4dce3a4b88dbfaf43979d280181558af5e2c3c71afc",
                "sha256:9517004e21664f2b5a5fd6333b0731b9cf0817403a941b393d89a2f1dc2bd836",
                "sha256:95c02b0e27e706e48d0e5426d1710ca78e0f0628d6e89d5b5a5b91a5f12274f3",
                "sha256:99881222f4a8c2f641f25703963a5cefb076adffd959e0558dc9f803a52d6a58",
                "sha256:9ee32dcb8e531adae1f1ca568822e9b3a738369b3b686d1477cbc643c4a9c128",
                "sha256:a22e47578b30a3e199ab067a4d43d790249b3c0587d9a771921f86250c8435db",
                "sha256:b5505774ea2a73a86ea176e8a9a4a7c8bf5d521050f0f6f8426afe798689243f",
                "sha256:bd739c9251d01e0279ce729e37b39d49a08c0420d3fee7f2a4968c0576678f77",
                "sha256:d16a786905034e7e34098634b184a7d81f91d4c3d246edc6bd7aefb2fd8ea6ad",
                "sha256:d3420522057ebab1728b21ad473aa950026d07cb09da41103f8e597dfbfaeb13",
                "sha256:d56fd9f1f1cdc8227d7b7918f55091349741904d9520c65f0139a9755952c9e8",
                "sha256:d661dc4785affa9d0edfdd1e59ec056a58b3dbb9f196fa43587f3ddac654ac7b",
                "sha256:dfe1f0f0ed5785c187144c46a292b8c34c1295c01da12e10ccddfc16def4448a",
                "sha256:e1dd7839443592d00e96db831eddb4111a2a81a46b028f0facd60a09ebbdd543",
                "sha256:e2872993e209f7ed04d963e4b4fbae72d034844ec66bc4ca403329db2074377b",
                "sha256:e2f879ab92ce502a1e65fce390eab619774dda6a6ff719718069ac94084098ce",
                "sha256:e3aa7e51d738e0ec0afbed661261513b38b3014754c9459508399baf14ae0c9d",
                "sha256:e532dbd6ddfe13946de050d7474e3f5fb6ec774fbb1a188aaf469b08cf04189a",
                "sha256:e6b7842518a63a9f17107eb176320960ec095a8ee3b4420b5f688e24bf50c53c",
                "sha256:e75753aeda0ddc4c28dce4c32ba2f6ec30b1b02f6c0b14e547841ba5b24f753f",
                "sha256:eadb9f826c138e6cf3c49d6f8de88225a3c0ab181a9b4ba792e006e5292d150e",
                "sha256:ed59dd52075f8fc91da6053b12e8c89e37aa043f8986efd89e61fae69dc1b011",
                "sha256:ef254a06bcea461e65ff0373d8a0dd1ed3aa004af48839f002a0c994a6f72d04",
                "sha256:f3709997b228685fe53e8c433e2df9f0cdb5f4542bd5114ed17ac3c0129b0480",
                "sha256:f51bab98d52739c50c56658cc303f190785f9a2cd97b823357e7aeae54c8f68a",
                "sha256:f9904e24646570539a8950400602d66d2b2c492b9010ea7e965025cb71d0c86d",
                "sha256:f9af38a89b6a5c04b7d18c492c8ccf2aee7048aff1ce8437c4683bb5a1df893d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.0.8"
        },
        "multipledispatch": {
            "hashes": [
                "sha256:0c53cd8b077546da4e48869f49b13164bebafd0c2a5afceb6bb6a316e7fb46e4",
                "sha256:5c839915465c68206c3e9c473357908216c28383b425361e5d144594bf85a7e0"
            ],
            "index": "pypi",
            "version": "==1.0.0"
        },
        "namex": {
            "hashes": [
                "sha256:32a50f6c565c0bb10aa76298c959507abdc0e850efe085dc38f3440fcb3aa90b",
                "sha256:7ddb6c2bb0e753a311b7590f84f6da659dd0c05e65cb89d519d54c0a250c0487"
            ],
            "index": "pypi",
            "version": "==0.0.8"
        },
        "nbformat": {
            "hashes": [
                "sha256:322168b14f937a5d11362988ecac2a4952d3d8e3a2cbeb2319584631226d5b3a",
                "sha256:3b48d6c8fbca4b299bf3982ea7db1af21580e4fec269ad087b9e81588891200b"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==5.10.4"
        },
        "nest-asyncio": {
            "hashes": [
                "sha256:6f172d5449aca15afd6c646851f4e31e02c598d553a667e38cafa997cfec55fe",
                "sha256:87af6efd6b5e897c81050477ef65c62e2b2f35d51703cae01aff2905b1852e1c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.5'",
            "version": "==1.6.0"
        },
        "networkx": {
            "hashes": [
                "sha256:307c3669428c5362aab27c8a1260aa8f47c4e91d3891f48be0141738d8d053e1",
                "sha256:df5d4365b724cf81b8c6a7312509d0c22386097011ad1abe274afd5e9d3bbc5f"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==3.4.2"
        },
        "numba": {
            "hashes": [
                "sha256:01ef4cd7d83abe087d644eaa3d95831b777aa21d441a23703d649e06b8e06b74",
                "sha256:0b983bd6ad82fe868493012487f34eae8bf7dd94654951404114f23c3466d34b",
                "sha256:0ebaa91538e996f708f1ab30ef4d3ddc344b64b5227b67a57aa74f401bb68b9d",
                "sha256:1527dc578b95c7c4ff248792ec33d097ba6bef9eda466c948b68dfc995c25781",
                "sha256:159e618ef213fba758837f9837fb402bbe65326e60ba0633dbe6c7f274d42c1b",
                "sha256:19407ced081d7e2e4b8d8c36aa57b7452e0283871c296e12d798852bc7d7f198",
                "sha256:3031547a015710140e8c87226b4cfe927cac199835e5bf7d4fe5cb64e814e3ab",
                "sha256:38d6ea4c1f56417076ecf8fc327c831ae793282e0ff51080c5094cb726507b1c",
                "sha256:3fb02b344a2a80efa6f677aa5c40cd5dd452e1b35f8d1c2af0dfd9ada9978e4b",
                "sha256:4142d7ac0210cc86432b818338a2bc368dc773a2f5cf1e32ff7c5b378bd63ee8",
                "sha256:5d761de835cd38fb400d2c26bb103a2726f548dc30368853121d66201672e651",
                "sha256:5df6158e5584eece5fc83294b949fd30b9f1125df7708862205217e068aabf16",
                "sha256:5f4fde652ea604ea3c86508a3fb31556a6157b2c76c8b51b1d45eb40c8598703",
                "sha256:62908d29fb6a3229c242e981ca27e32a6e606cc253fc9e8faeb0e48760de241e",
                "sha256:819a3dfd4630d95fd574036f99e47212a1af41cbcb019bf8afac63ff56834449",
                "sha256:a17b70fc9e380ee29c42717e8cc0bfaa5556c416d94f9aa96ba13acb41bdece8",
                "sha256:c151748cd269ddeab66334bd754817ffc0cabd9433acb0f551697e5151917d25",
                "sha256:cac02c041e9b5bc8cf8f2034ff6f0dbafccd1ae9590dc146b3a02a45e53af4e2",
                "sha256:d7da4098db31182fc5ffe4bc42c6f24cd7d1cb8a14b59fd755bfee32e34b8404",
                "sha256:f75262e8fe7fa96db1dca93d53a194a38c46da28b112b8a4aca168f0df860347",
                "sha256:fe0b28abb8d70f8160798f4de9d486143200f34458d34c4a214114e445d7124e"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==0.60.0"
        },
        "numpy": {
            "hashes": [
                "sha256:0123ffdaa88fa4ab64835dcbde75dcdf89c453c922f18dced6e27c90d1d0ec5a",
                "sha256:11a76c372d1d37437857280aa142086476136a8c0f373b2e648ab2c8f18fb195",
                "sha256:13e689d772146140a252c3a28501da66dfecd77490b498b168b501835041f951",
                "sha256:1e795a8be3ddbac43274f18588329c72939870a16cae810c2b73461c40718ab1",
                "sha256:26df23238872200f63518dd2aa984cfca675d82469535dc7162dc2ee52d9dd5c",
                "sha256:286cd40ce2b7d652a6f22efdfc6d1edf879440e53e76a75955bc0c826c7e64dc",
                "sha256:2b2955fa6f11907cf7a70dab0d0755159bca87755e831e47932367fc8f2f2d0b",
                "sha256:2da5960c3cf0df7eafefd806d4e612c5e19358de82cb3c343631188991566ccd",
                "sha256:312950fdd060354350ed123c0e25a71327d3711584beaef30cdaa93320c392d4",
                "sha256:423e89b23490805d2a5a96fe40ec507407b8ee786d66f7328be214f9679df6dd",
                "sha256:496f71341824ed9f3d2fd36cf3ac57ae2e0165c143b55c3a035ee219413f3318",
                "sha256:49ca4decb342d66018b01932139c0961a8f9ddc7589611158cb3c27cbcf76448",
                "sha256:51129a29dbe56f9ca83438b706e2e69a39892b5eda6cedcb6b0c9fdc9b0d3ece",
                "sha256:5fec9451a7789926bcf7c2b8d187292c9f93ea30284802a0ab3f5be8ab36865d",
                "sha256:671bec6496f83202ed2d3c8fdc486a8fc86942f2e69ff0e986140339a63bcbe5",
                "sha256:7f0a0c6f12e07fa94133c8a67404322845220c06a9e80e85999afe727f7438b8",
                "sha256:807ec44583fd708a21d4a11d94aedf2f4f3c3719035c76a2bbe1fe8e217bdc57",
                "sha256:883c987dee1880e2a864ab0dc9892292582510604156762362d9326444636e78",
                "sha256:8c5713284ce4e282544c68d1c3b2c7161d38c256d2eefc93c1d683cf47683e66",
                "sha256:8cafab480740e22f8d833acefed5cc87ce276f4ece12fdaa2e8903db2f82897a",
                "sha256:8df823f570d9adf0978347d1f926b2a867d5608f434a7cff7f7908c6570dcf5e",
                "sha256:9059e10581ce4093f735ed23f3b9d283b9d517ff46009ddd485f1747eb22653c",
                "sha256:905d16e0c60200656500c95b6b8dca5d109e23cb24abc701d41c02d74c6b3afa",
                "sha256:9189427407d88ff25ecf8f12469d4d39d35bee1db5d39fc5c168c6f088a6956d",
                "sha256:96a55f64139912d61de9137f11bf39a55ec8faec288c75a54f93dfd39f7eb40c",
                "sha256:97032a27bd9d8988b9a97a8c4d2c9f2c15a81f61e2f21404d7e8ef00cb5be729",
                "sha256:984d96121c9f9616cd33fbd0618b7f08e0cfc9600a7ee1d6fd9b239186d19d97",
                "sha256:9a92ae5c14811e390f3767053ff54eaee3bf84576d99a2456391401323f4ec2c",
                "sha256:9ea91dfb7c3d1c56a0e55657c0afb38cf1eeae4544c208dc465c3c9f3a7c09f9",
                "sha256:a15f476a45e6e5a3a79d8a14e62161d27ad897381fecfa4a09ed5322f2085669",
                "sha256:a392a68bd329eafac5817e5aefeb39038c48b671afd242710b451e76090e81f4",
                "sha256:a3f4ab0caa7f053f6797fcd4e1e25caee367db3112ef2b6ef82d749530768c73",
                "sha256:a46288ec55ebbd58947d31d72be2c63cbf839f0a63b49cb755022310792a3385",
                "sha256:a61ec659f68ae254e4d237816e33171497e978140353c0c2038d46e63282d0c8",
                "sha256:a842d573724391493a97a62ebbb8e731f8a5dcc5d285dfc99141ca15a3302d0c",
                "sha256:becfae3ddd30736fe1889a37f1f580e245ba79a5855bff5f2a29cb3ccc22dd7b",
                "sha256:c05e238064fc0610c840d1cf6a13bf63d7e391717d247f1bf0318172e759e692",
                "sha256:c1c9307701fec8f3f7a1e6711f9089c06e6284b3afbbcd259f7791282d660a15",
                "sha256:c7b0be4ef08607dd04da4092faee0b86607f111d5ae68036f16cc787e250a131",
                "sha256:cfd41e13fdc257aa5778496b8caa5e856dc4896d4ccf01841daee1d96465467a",
                "sha256:d731a1c6116ba289c1e9ee714b08a8ff882944d4ad631fd411106a30f083c326",
                "sha256:df55d490dea7934f330006d0f81e8551ba6010a5bf035a249ef61a94f21c500b",
                "sha256:ec9852fb39354b5a45a80bdab5ac02dd02b15f44b3804e9f00c556bf24b4bded",
                "sha256:f15975dfec0cf2239224d80e32c3170b1d168335eaedee69da84fbe9f1f9cd04",
                "sha256:f26b258c385842546006213344c50655ff1555a9338e2e5e02a0756dc3e803dd"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==2.0.2"
        },
        "openpyxl": {
            "hashes": [
                "sha256:5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2",
                "sha256:cf0e3cf56142039133628b5acffe8ef0c12bc902d2aadd3e0fe5878dc08d1050"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.1.5"
        },
        "opt-einsum": {
            "hashes": [
                "sha256:69bb92469f86a1565195ece4ac0323943e83477171b91d24c35afe028a90d7cd",
                "sha256:96ca72f1b886d148241348783498194c577fa30a8faac108586b14f1ba4473ac"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.4.0"
        },
        "optree": {
            "hashes": [
                "sha256:01819c3df950696f32c91faf8d376ae6b695ffdba18f330f1cab6b8e314e4612",
                "sha256:025d23400b8b579462a251420f0a9ae77d3d3593f84276f3465985731d79d722",
                "sha256:04252b5f24e5dae716647848b302f5f7849ecb028f8c617666d1b89a42eb988b",
                "sha256:0914ba436d6c0781dc9b04e3b95e06fe5c4fc6a87e94893da971805a3790efe8",
                "sha256:0adc896018f34b5f37f6c92c35ae639877578725c5281cc9d4a0ac2ab2c46f77",
                "sha256:0aec6da79a6130b4c76073241c0f31c11b96a38e70c7a00f9ed918d7464394ab",
                "sha256:0f1bde49e41a158af28d99fae1bd425fbd664907c53cf595106fb5b35e5cbe26",
                "sha256:0f9707547635cfede8d79e4161c066021ffefc401d98bbf8eba452b1355a42c7",
                "sha256:100d70cc57af5284649f881e6b266fee3a3e86e82024484eaa64ee18d1587e42",
                "sha256:111172446e8a4f0d3be13a853fa28cb46b5679a1c7ca15b2e6db2b43dbbf9efb",
                "sha256:135e29e0a69149958003443d43f49af0ebb65f03ae52cddf4142e94d5a36b0c8",
                "sha256:1496f29d5b9633fed4b3f1fd4b7e772d77200eb2370c08ef8e14404309c669b9",
                "sha256:1891267f9dc76e9ddfed947ff7b755ad438ad483de0537a6b5bcf38478d5a33c",
                "sha256:1935639dd498a42367633e3877797e1330e39d44d48bbca1a136bb4dbe4c1bc9",
                "sha256:1b291aed475ca5992a0c587ca4b72f074724209e01afca9d015c9a5b2089c68d",
                "sha256:1d74ff3dfe8599935d52b26a2fe5a43242b4d3f47be6fc1c5ce34c25e116d616",
                "sha256:2063234ef4d58f11277e157d1cf066a8bd07be911da226bff84fc9761b8c1a25",
                "sha256:22ce30c9d733c2214fa321c8370e4dfc8c7829970364618b2b5cacffbc9e8949",
                "sha256:2521840d6aded4dac62c787f50bcb1cacbfcda86b9319d666b4025fa0ba5545a",
                "sha256:27d81dc43b522ba47ba7d2e7d91dbb486940348b1bf85caeb0afc2815c0aa492",
                "sha256:28f083ede9be89503357a6b9e5d304826701596abe13d33e8f6fa2cd85b407fc",
                "sha256:2909cb42add6bb1a5a2b0243bdd8c4b861bf072f3741e26239481907ac8ad4e6",
                "sha256:2cba7ca4cf991270a9fdd080b091d2cbdbcbf27858acebda6af40ff57312d1ea",
                "sha256:3010ae24e994f6e00071098d34e98e78eb995b7454a2ef629a0bf7df17441b24",
                "sha256:30b02951c48ecca6fbeb6a3cc7a858267c4d82d1c874481a639061e845168da5",
                "sha256:34b4dd0f5d73170c7740726cadfca973220ccbed9559beb51fab446d9e584d0a",
                "sha256:360f2e8f7eb22ff131bc7e3e241035908e6b47d41372eb3d68d77bc7036ddb30",
                "sha256:363939b255a9fa0e077d8297a8301857c859592fc581cee19ec9238e0c145c4a",
                "sha256:37948e2d796db23d6ccd07105b709b827eba26549d34dd2149e95887c89fe9b4",
                "sha256:395ac2eb69528613fd0f2ee8706890b7921b8ff3159df53b6e9f67eaf519c5cb",
                "sha256:3d0161012d80e4865017e10298ac55652cc3ad9a3eae9440229d4bf00b140e01",
                "sha256:3da76fc43dcc22fe58d11634a04672ca7cc270aed469ac35fd5c78b7b9bc9125",
                "sha256:4711f5cac5a2a49c3d6c9f0eca7b77c22b452170bb33ea01c3214ebb17931db9",
                "sha256:48c29d9c6c64c8dc48c8ee97f7c1d5cdb83e37320f0be0857c06ce4b97994aea",
                "sha256:50dd6a9c8ccef267ab4941f07eac53faf6a00666dce4d209da20525570ffaca3",
                "sha256:536ecf0e555432cc939d958590e33e00e75cc254ab0dd269e84fc9de8352db61",
                "sha256:5569b95e214d20a1b7acb7d9477fabbd709d334bc34f3257368ea1418b811a44",
                "sha256:55e82426bef151149cfa41d68ac957730fcd420996c0db8324fca81aa6a810ba",
                "sha256:587fb8de8e75e80fe7c7240e269630876bec3ee2038724893370976207813e4b",
                "sha256:5b5626c38d4a18a144063db5c1dbb558431d83ca10682324f74665a12214801f",
                "sha256:5b6531cd4eb23fadbbf77faf834e1119da06d7af3154f55786b59953cd87bb8a",
                "sha256:5c6aed6c5eabda59a91376aca08ba508a06f1c68850216a98743b5f8f55af841",
                "sha256:5c950c85561c47efb3b1a3771ed1b2b2339bd5e28a0ca42bdcedadccc645eeac",
                "sha256:5d21a8b449e47fdbf118ac1938cf6f97d8a60258bc45c6eba3e61f79feeb1ea8",
                "sha256:5da0fd26325a07354915cc4e3a9aee797cb75dff07c60d24b3f309457069abd3",
                "sha256:5dec0785bc4bbcabecd7e82be3f189b21f3ce8a1244b243009736912a6d8f737",
                "sha256:5f94a627c5a2fb776bbfa8f7558db5b918916d37586ba943e74e5f22789c4301",
                "sha256:63b2749504fe0b9ac3892e26bf55a040ae2973bcf8da1476afe9266a4624be9d",
                "sha256:64032b77420410c3d315a4b9bcbece15853432c155613bb4261d87809b3ee357",
                "sha256:652287e43fcbb29b8d1821144987e3bc558be4e5eec0d42fce7007cc3ee8e574",
                "sha256:6bc9aae5ee17a38e3657c8c5db1a60923cc10debd177f6781f352362a846feeb",
                "sha256:6c4ab1d391b89cb88eb3c63383d5eb0930bc21141de9d5acd277feed9e38eb65",
                "sha256:7abf1c6fe42cb112f0fb169f80d7b26476fa44226d2caf3727b49d210bdc3343",
                "sha256:7e1c1da6574d59073b6a6b9a13633217f584ec271ddee4e014c7e422f171e9b4",
                "sha256:84a6a974aa9dc4119fe502865c8e1755090ac17dbb53a964619a8ece1130831e",
                "sha256:8d89891e11a55ad83ab3e2810f8571774b2117a6198b4044fa44e0f37f72855e",
                "sha256:940c739c9957404a9bbe40ed9289792adaf476cece59eca4fe2f32137fa15a8d",
                "sha256:95298846c057cce2e7d114c03c645e86a5381b72388c8c390986bdefe69a759c",
                "sha256:9824a4258b058282eeaee1b388c8dfc704e49beda957b99177db8bd8249a3abe",
                "sha256:9c8ee1e988c634a451146b87d9ebdbf650a75dc1f52a9cffcd89fabb7289321c",
                "sha256:a3058e2d6a6a7d6362d40f7826258204d9fc2cc4cc8f72eaa3dbff14b6622025",
                "sha256:a408a43f16840475612c7058eb80b53791bf8b8266c5b3cd07f69697958fd97d",
                "sha256:aee696272eece657c2b9e3cf079d8fc7cbbcc8a5c8199dbcd0960ddf7e672fe9",
                "sha256:af67856aa8073d237fe67313d84f8aeafac32c1cef7239c628a2768d02679c43",
                "sha256:b21ac55473476007e317500fd5851d0a0d695a0c51742bd65fe7347d18530da2",
                "sha256:b5e5f09c85ae558a6bdaea57e63168082e728e777391393e9e2792f0d15b7b59",
                "sha256:b94f9081cd810a59faae4dbac8f0447e59ce0fb2d70cfb388dc123c33a9fd1a8",
                "sha256:bbc5fa2ff5090389f3a906567446f01d692bd6fe5cfcc5ae2d5861f24e8e0e4d",
                "sha256:bc9c396f64f9aacdf852713bd75f1b9a83f118660fd82e87c937c081b7ddccd1",
                "sha256:c4d13f55dbd509d27be3af54d53b4ca0751bc518244ced6d0567e518e51452a2",
                "sha256:c84ecb6977ba7f5d4ba24d0312cbffb74c6860237572701c2716bd811ca9b226",
                "sha256:c99891c2ea6050738f7e3de5ab4038736cf33555a752b34a06922ebc9bf0488e",
                "sha256:ce962f0dd387137817dcda600bd6cf2e1b65103411807b6cdbbd9ffddf1061f6",
                "sha256:cf85ba1a7d80b6dc19ef5ca4c17d2ff0290dc9306c5b8b468d51cede287f3c8d",
                "sha256:cfdf7f5cfb5f9b1c0188c667a3dc56551e60a52a918cb8600f84e2f0ad882106",
                "sha256:d0c5a389c108367007151bcfef494f8c2674e4aa23d80ac9163876f5b213dfb6",
                "sha256:d1844b966bb5c95b64af5c6f92f99e4037452b92b18d060fbd80097b5b773d86",
                "sha256:d580f1bf23bb352c4db6b3544f282f1ac08dcb0d9ab537d25e56220353438cf7",
                "sha256:d866f707b9f3a9f0e670a73fe8feee4993b2dbdbf9eef598e1cf2e5cb2876413",
                "sha256:de1ae16ea0410497e50fe2b4d48a83c37bfc87da76e1e82f9cc8c800b4fc8be6",
                "sha256:e40f018f522fcfd244688d1b3a360518e636ba7f636385aae0566eae3e7d29bc",
                "sha256:efbffeec15e4a79ed9921dc2227cbba1b64db353c4b72ce4ce83e62fbce9e652",
                "sha256:f2a9eadcab78ccc04114a6916e9decdbc886bbe04c1b7a7bb32e723209162998",
                "sha256:f39c7174a3f3cdc3f5fe6fb4b832f608c40ac174d7567ed6734b2ee952094631",
                "sha256:f74fb880472572d550d85d2f1563365b6f194e2157a7703790cbd54d9ab5cf29",
                "sha256:f788b2ad120deb73b4908a74473cd6de79cfb9f33bbe9dcb59cea2e2477d4e28",
                "sha256:f8e2a546cecc5077ec7d4fe24ec8aede43ca8555b832d115f1ebbb4f3b35bc78",
                "sha256:fafeda2e35e3270532132e27b471ea3e3aeac18f7966a4d0469137d1f36046ec"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==0.13.1"
        },
        "packaging": {
            "hashes": [
                "sha256:2ddfb553fdf02fb784c234c7ba6ccc288296ceabec964ad2eae3777778130bc5",
                "sha256:eb82c5e3e56209074766e6885bb04b8c38a0c015d0a30036ebe7ece34c9989e9"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==24.0"
        },
        "pandas": {
            "hashes": [
                "sha256:062309c1b9ea12a50e8ce661145c6aab431b1e99530d3cd60640e255778bd43a",
                "sha256:15c0e1e02e93116177d29ff83e8b1619c93ddc9c49083f237d4312337a61165d",
                "sha256:1948ddde24197a0f7add2bdc4ca83bf2b1ef84a1bc8ccffd95eda17fd836ecb5",
                "sha256:1db71525a1538b30142094edb9adc10be3f3e176748cd7acc2240c2f2e5aa3a4",
                "sha256:22a9d949bfc9a502d320aa04e5d02feab689d61da4e7764b62c30b991c42c5f0",
                "sha256:29401dbfa9ad77319367d36940cd8a0b3a11aba16063e39632d98b0e931ddf32",
                "sha256:31d0ced62d4ea3e231a9f228366919a5ea0b07440d9d4dac345376fd8e1477ea",
                "sha256:3508d914817e153ad359d7e069d752cdd736a247c322d932eb89e6bc84217f28",
                "sha256:37e0aced3e8f539eccf2e099f65cdb9c8aa85109b0be6e93e2baff94264bdc6f",
                "sha256:381175499d3802cde0eabbaf6324cce0c4f5d52ca6f8c377c29ad442f50f6348",
                "sha256:38cf8125c40dae9d5acc10fa66af8ea6fdf760b2714ee482ca691fc66e6fcb18",
                "sha256:3b71f27954685ee685317063bf13c7709a7ba74fc996b84fc6821c59b0f06468",
                "sha256:3fc6873a41186404dad67245896a6e440baacc92f5b716ccd1bc9ed2995ab2c5",
                "sha256:4850ba03528b6dd51d6c5d273c46f183f39a9baf3f0143e566b89450965b105e",
                "sha256:4f18ba62b61d7e192368b84517265a99b4d7ee8912f8708660fb4a366cc82667",
                "sha256:56534ce0746a58afaf7942ba4863e0ef81c9c50d3f0ae93e9497d6a41a057645",
                "sha256:59ef3764d0fe818125a5097d2ae867ca3fa64df032331b7e0917cf5d7bf66b13",
                "sha256:5dbca4c1acd72e8eeef4753eeca07de9b1db4f398669d5994086f788a5d7cc30",
                "sha256:5de54125a92bb4d1c051c0659e6fcb75256bf799a732a87184e5ea503965bce3",
                "sha256:61c5ad4043f791b61dd4752191d9f07f0ae412515d59ba8f005832a532f8736d",
                "sha256:6374c452ff3ec675a8f46fd9ab25c4ad0ba590b71cf0656f8b6daa5202bca3fb",
                "sha256:63cc132e40a2e084cf01adf0775b15ac515ba905d7dcca47e9a251819c575ef3",
                "sha256:66108071e1b935240e74525006034333f98bcdb87ea116de573a6a0dccb6c039",
                "sha256:6dfcb5ee8d4d50c06a51c2fffa6cff6272098ad6540aed1a76d15fb9318194d8",
                "sha256:7c2875855b0ff77b2a64a0365e24455d9990730d6431b9e0ee18ad8acee13dbd",
                "sha256:7eee9e7cea6adf3e3d24e304ac6b8300646e2a5d1cd3a3c2abed9101b0846761",
                "sha256:800250ecdadb6d9c78eae4990da62743b857b470883fa27f652db8bdde7f6659",
                "sha256:86976a1c5b25ae3f8ccae3a5306e443569ee3c3faf444dfd0f41cda24667ad57",
                "sha256:8cd6d7cc958a3910f934ea8dbdf17b2364827bb4dafc38ce6eef6bb3d65ff09c",
                "sha256:99df71520d25fade9db7c1076ac94eb994f4d2673ef2aa2e86ee039b6746d20c",
                "sha256:a5a1595fe639f5988ba6a8e5bc9649af3baf26df3998a0abe56c02609392e0a4",
                "sha256:ad5b65698ab28ed8d7f18790a0dc58005c7629f227be9ecc1072aa74c0c1d43a",
                "sha256:b1d432e8d08679a40e2a6d8b2f9770a5c21793a6f9f47fdd52c5ce1948a5a8a9",
                "sha256:b8661b0238a69d7aafe156b7fa86c44b881387509653fdf857bebc5e4008ad42",
                "sha256:ba96630bc17c875161df3818780af30e43be9b166ce51c9a18c1feae342906c2",
                "sha256:bc6b93f9b966093cb0fd62ff1a7e4c09e6d546ad7c1de191767baffc57628f39",
                "sha256:c124333816c3a9b03fbeef3a9f230ba9a737e9e5bb4060aa2107a86cc0a497fc",
                "sha256:cd8d0c3be0515c12fed0bdbae072551c8b54b7192c7b1fda0ba56059a0179698",
                "sha256:d9c45366def9a3dd85a6454c0e7908f2b3b8e9c138f5dc38fed7ce720d8453ed",
                "sha256:f00d1345d84d8c86a63e476bb4955e46458b304b9575dcf71102b5c705320015",
                "sha256:f3a255b2c19987fbbe62a9dfd6cff7ff2aa9ccab3fc75218fd4b7530f01efa24",
                "sha256:fffb8ae78d8af97f849404f21411c95062db1496aeb3e56f146f0355c9989319"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==2.2.3"
        },
        "panel": {
            "hashes": [
                "sha256:7644e87afe9b94c32b4fca939d645c5b958d671691bd841d3391e31941090092",
                "sha256:98521ff61dfe2ef684181213842521674d2db95f692c7942ab9103a2c0e882b9"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==1.5.4"
        },
        "param": {
            "hashes": [
                "sha256:3b1da14abafa75bfd908572378a58696826b3719a723bc31b40ffff2e9a5c852",
                "sha256:81066d040526fbaa44b6419f3e92348fa8856ea44c8d3915e9245937ddabe2d6"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.1.1"
        },
        "parso": {
            "hashes": [
                "sha256:a418670a20291dacd2dddc80c377c5c3791378ee1e8d12bffc35420643d43f18",
                "sha256:eb3a7b58240fb99099a345571deecc0f9540ea5f4dd2fe14c2a99d6b281ab92d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==0.8.4"
        },
        "partd": {
            "hashes": [
                "sha256:978e4ac767ec4ba5b86c6eaa52e5a2a3bc748a2ca839e8cc798f1cc6ce6efb0f",
                "sha256:d022c33afbdc8405c226621b015e8067888173d85f7f5ecebb3cafed9a20f02c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==1.4.2"
        },
        "pillow": {
            "hashes": [
                "sha256:00177a63030d612148e659b55ba99527803288cea7c75fb05766ab7981a8c1b7",
                "sha256:006bcdd307cc47ba43e924099a038cbf9591062e6c50e570819743f5607404f5",
                "sha256:084a07ef0821cfe4858fe86652fffac8e187b6ae677e9906e192aafcc1b69903",
                "sha256:0ae08bd8ffc41aebf578c2af2f9d8749d91f448b3bfd41d7d9ff573d74f2a6b2",
                "sha256:0e038b0745997c7dcaae350d35859c9715c71e92ffb7e0f4a8e8a16732150f38",
                "sha256:1187739620f2b365de756ce086fdb3604573337cc28a0d3ac4a01ab6b2d2a6d2",
                "sha256:16095692a253047fe3ec028e951fa4221a1f3ed3d80c397e83541a3037ff67c9",
                "sha256:1a61b54f87ab5786b8479f81c4b11f4d61702830354520837f8cc791ebba0f5f",
                "sha256:1c1d72714f429a521d8d2d018badc42414c3077eb187a59579f28e4270b4b0fc",
                "sha256:1e2688958a840c822279fda0086fec1fdab2f95bf2b717b66871c4ad9859d7e8",
                "sha256:20ec184af98a121fb2da42642dea8a29ec80fc3efbaefb86d8fdd2606619045d",
                "sha256:21a0d3b115009ebb8ac3d2ebec5c2982cc693da935f4ab7bb5c8ebe2f47d36f2",
                "sha256:224aaa38177597bb179f3ec87eeefcce8e4f85e608025e9cfac60de237ba6316",
                "sha256:2679d2258b7f1192b378e2893a8a0a0ca472234d4c2c0e6bdd3380e8dfa21b6a",
                "sha256:27a7860107500d813fcd203b4ea19b04babe79448268403172782754870dac25",
                "sha256:290f2cc809f9da7d6d622550bbf4c1e57518212da51b6a30fe8e0a270a5b78bd",
                "sha256:2e46773dc9f35a1dd28bd6981332fd7f27bec001a918a72a79b4133cf5291dba",
                "sha256:3107c66e43bda25359d5ef446f59c497de2b5ed4c7fdba0894f8d6cf3822dafc",
                "sha256:375b8dd15a1f5d2feafff536d47e22f69625c1aa92f12b339ec0b2ca40263273",
                "sha256:45c566eb10b8967d71bf1ab8e4a525e5a93519e29ea071459ce517f6b903d7fa",
                "sha256:499c3a1b0d6fc8213519e193796eb1a86a1be4b1877d678b30f83fd979811d1a",
                "sha256:4ad70c4214f67d7466bea6a08061eba35c01b1b89eaa098040a35272a8efb22b",
                "sha256:4b60c9520f7207aaf2e1d94de026682fc227806c6e1f55bba7606d1c94dd623a",
                "sha256:5178952973e588b3f1360868847334e9e3bf49d19e169bbbdfaf8398002419ae",
                "sha256:52a2d8323a465f84faaba5236567d212c3668f2ab53e1c74c15583cf507a0291",
                "sha256:598b4e238f13276e0008299bd2482003f48158e2b11826862b1eb2ad7c768b97",
                "sha256:5bd2d3bdb846d757055910f0a59792d33b555800813c3b39ada1829c372ccb06",
                "sha256:5c39ed17edea3bc69c743a8dd3e9853b7509625c2462532e62baa0732163a904",
                "sha256:5d203af30149ae339ad1b4f710d9844ed8796e97fda23ffbc4cc472968a47d0b",
                "sha256:5ddbfd761ee00c12ee1be86c9c0683ecf5bb14c9772ddbd782085779a63dd55b",
                "sha256:607bbe123c74e272e381a8d1957083a9463401f7bd01287f50521ecb05a313f8",
                "sha256:61b887f9ddba63ddf62fd02a3ba7add935d053b6dd7d58998c630e6dbade8527",
                "sha256:6619654954dc4936fcff82db8eb6401d3159ec6be81e33c6000dfd76ae189947",
                "sha256:674629ff60030d144b7bca2b8330225a9b11c482ed408813924619c6f302fdbb",
                "sha256:6ec0d5af64f2e3d64a165f490d96368bb5dea8b8f9ad04487f9ab60dc4bb6003",
                "sha256:6f4dba50cfa56f910241eb7f883c20f1e7b1d8f7d91c750cd0b318bad443f4d5",
                "sha256:70fbbdacd1d271b77b7721fe3cdd2d537bbbd75d29e6300c672ec6bb38d9672f",
                "sha256:72bacbaf24ac003fea9bff9837d1eedb6088758d41e100c1552930151f677739",
                "sha256:7326a1787e3c7b0429659e0a944725e1b03eeaa10edd945a86dead1913383944",
                "sha256:73853108f56df97baf2bb8b522f3578221e56f646ba345a372c78326710d3830",
                "sha256:73e3a0200cdda995c7e43dd47436c1548f87a30bb27fb871f352a22ab8dcf45f",
                "sha256:75acbbeb05b86bc53cbe7b7e6fe00fbcf82ad7c684b3ad82e3d711da9ba287d3",
                "sha256:8069c5179902dcdce0be9bfc8235347fdbac249d23bd90514b7a47a72d9fecf4",
                "sha256:846e193e103b41e984ac921b335df59195356ce3f71dcfd155aa79c603873b84",
                "sha256:8594f42df584e5b4bb9281799698403f7af489fba84c34d53d1c4bfb71b7c4e7",
                "sha256:86510e3f5eca0ab87429dd77fafc04693195eec7fd6a137c389c3eeb4cfb77c6",
                "sha256:8853a3bf12afddfdf15f57c4b02d7ded92c7a75a5d7331d19f4f9572a89c17e6",
                "sha256:88a58d8ac0cc0e7f3a014509f0455248a76629ca9b604eca7dc5927cc593c5e9",
                "sha256:8ba470552b48e5835f1d23ecb936bb7f71d206f9dfeee64245f30c3270b994de",
                "sha256:8c676b587da5673d3c75bd67dd2a8cdfeb282ca38a30f37950511766b26858c4",
                "sha256:8ec4a89295cd6cd4d1058a5e6aec6bf51e0eaaf9714774e1bfac7cfc9051db47",
                "sha256:94f3e1780abb45062287b4614a5bc0874519c86a777d4a7ad34978e86428b8dd",
                "sha256:9a0f748eaa434a41fccf8e1ee7a3eed68af1b690e75328fd7a60af123c193b50",
                "sha256:a5629742881bcbc1f42e840af185fd4d83a5edeb96475a575f4da50d6ede337c",
                "sha256:a65149d8ada1055029fcb665452b2814fe7d7082fcb0c5bed6db851cb69b2086",
                "sha256:b3c5ac4bed7519088103d9450a1107f76308ecf91d6dabc8a33a2fcfb18d0fba",
                "sha256:b4fd7bd29610a83a8c9b564d457cf5bd92b4e11e79a4ee4716a63c959699b306",
                "sha256:bcd1fb5bb7b07f64c15618c89efcc2cfa3e95f0e3bcdbaf4642509de1942a699",
                "sha256:c12b5ae868897c7338519c03049a806af85b9b8c237b7d675b8c5e089e4a618e",
                "sha256:c26845094b1af3c91852745ae78e3ea47abf3dbcd1cf962f16b9a5fbe3ee8488",
                "sha256:c6a660307ca9d4867caa8d9ca2c2658ab685de83792d1876274991adec7b93fa",
                "sha256:c809a70e43c7977c4a42aefd62f0131823ebf7dd73556fa5d5950f5b354087e2",
                "sha256:c8b2351c85d855293a299038e1f89db92a2f35e8d2f783489c6f0b2b5f3fe8a3",
                "sha256:cb929ca942d0ec4fac404cbf520ee6cac37bf35be479b970c4ffadf2b6a1cad9",
                "sha256:d2c0a187a92a1cb5ef2c8ed5412dd8d4334272617f532d4ad4de31e0495bd923",
                "sha256:d69bfd8ec3219ae71bcde1f942b728903cad25fafe3100ba2258b973bd2bc1b2",
                "sha256:daffdf51ee5db69a82dd127eabecce20729e21f7a3680cf7cbb23f0829189790",
                "sha256:e58876c91f97b0952eb766123bfef372792ab3f4e3e1f1a2267834c2ab131734",
                "sha256:eda2616eb2313cbb3eebbe51f19362eb434b18e3bb599466a1ffa76a033fb916",
                "sha256:ee217c198f2e41f184f3869f3e485557296d505b5195c513b2bfe0062dc537f1",
                "sha256:f02541ef64077f22bf4924f225c0fd1248c168f86e4b7abdedd87d6ebaceab0f",
                "sha256:f1b82c27e89fffc6da125d5eb0ca6e68017faf5efc078128cfaa42cf5cb38798",
                "sha256:fba162b8872d30fea8c52b258a542c5dfd7b235fb5cb352240c8d63b414013eb",
                "sha256:fbbcb7b57dc9c794843e3d1258c0fbf0f48656d46ffe9e09b63bbd6e8cd5d0a2",
                "sha256:fcb4621042ac4b7865c179bb972ed0da0218a076dc1820ffc48b1d74c1e37fe9"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==11.0.0"
        },
        "platformdirs": {
            "hashes": [
                "sha256:357fb2acbc885b0419afd3ce3ed34564c13c9b95c89360cd9563f73aa5e2b907",
                "sha256:73e575e1408ab8103900836b97580d5307456908a03e92031bab39e4554cc3fb"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.3.6"
        },
        "plotly": {
            "hashes": [
                "sha256:837a9c8aa90f2c0a2f0d747b82544d014dc2a2bdde967b5bb1da25b53932d1a9",
                "sha256:bf901c805d22032cfa534b2ff7c5aa6b0659e037f19ec1e0cca7f585918b5c89"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==5.20.0"
        },
        "polygon": {
            "hashes": [
                "sha256:05f583ff5273d7d83529aea53aaa24e7aa2f66edc548a1e376868c2bded6cbf4"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.6'",
            "version": "==1.2.5"
        },
        "prompt-toolkit": {
            "hashes": [
                "sha256:d6623ab0477a80df74e646bdbc93621143f5caf104206aa29294d53de1a03d90",
                "sha256:f49a827f90062e411f1ce1f854f2aedb3c23353244f8108b89283587397ac10e"
            ],
            "index": "pypi",
            "markers": "python_full_version >= '3.7.0'",
            "version": "==3.0.48"
        },
        "protobuf": {
            "hashes": [
                "sha256:0cd67a1e5c2d88930aa767f702773b2d054e29957432d7c6a18f8be02a07719a",
                "sha256:0d10091d6d03537c3f902279fcf11e95372bdd36a79556311da0487455791b20",
                "sha256:17d128eebbd5d8aee80300aed7a43a48a25170af3337f6f1333d1fac2c6839ac",
                "sha256:34a90cf30c908f47f40ebea7811f743d360e202b6f10d40c02529ebd84afc069",
                "sha256:445a0c02483869ed8513a585d80020d012c6dc60075f96fa0563a724987b1001",
                "sha256:6c3009e22717c6cc9e6594bb11ef9f15f669b19957ad4087214d69e08a213368",
                "sha256:85286a47caf63b34fa92fdc1fd98b649a8895db595cfa746c5286eeae890a0b1",
                "sha256:88c4af76a73183e21061881360240c0cdd3c39d263b4e8fb570aaf83348d608f",
                "sha256:c931c61d0cc143a2e756b1e7f8197a508de5365efd40f83c907a9febf36e6b43",
                "sha256:e467f81fdd12ded9655cea3e9b83dc319d93b394ce810b556fb0f421d8613e86",
                "sha256:ea7fb379b257911c8c020688d455e8f74efd2f734b72dc1ea4b4d7e9fd1326f2"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==5.29.0"
        },
        "psutil": {
            "hashes": [
                "sha256:000d1d1ebd634b4efb383f4034437384e44a6d455260aaee2eca1e9c1b55f047",
                "sha256:045f00a43c737f960d273a83973b2511430d61f283a44c96bf13a6e829ba8fdc",
                "sha256:0895b8414afafc526712c498bd9de2b063deaac4021a3b3c34566283464aff8e",
                "sha256:1209036fbd0421afde505a4879dee3b2fd7b1e14fee81c0069807adcbbcca747",
                "sha256:1ad45a1f5d0b608253b11508f80940985d1d0c8f6111b5cb637533a0e6ddc13e",
                "sha256:353815f59a7f64cdaca1c0307ee13558a0512f6db064e92fe833784f08539c7a",
                "sha256:498c6979f9c6637ebc3a73b3f87f9eb1ec24e1ce53a7c5173b8508981614a90b",
                "sha256:5cd2bcdc75b452ba2e10f0e8ecc0b57b827dd5d7aaffbc6821b2a9a242823a76",
                "sha256:6d3fbbc8d23fcdcb500d2c9f94e07b1342df8ed71b948a2649b5cb060a7c94ca",
                "sha256:6e2dcd475ce8b80522e51d923d10c7871e45f20918e027ab682f94f1c6351688",
                "sha256:9118f27452b70bb1d9ab3198c1f626c2499384935aaf55388211ad982611407e",
                "sha256:9dcbfce5d89f1d1f2546a2090f4fcf87c7f669d1d90aacb7d7582addece9fb38",
                "sha256:a8506f6119cff7015678e2bce904a4da21025cc70ad283a53b099e7620061d85",
                "sha256:a8fb3752b491d246034fa4d279ff076501588ce8cbcdbb62c32fd7a377d996be",
                "sha256:c0e0c00aa18ca2d3b2b991643b799a15fc8f0563d2ebb6040f64ce8dc027b942",
                "sha256:d905186d647b16755a800e7263d43df08b790d709d575105d419f8b6ef65423a",
                "sha256:ff34df86226c0227c52f38b919213157588a678d049688eded74c76c8ba4a5d0"
            ],
            "index": "pypi",
            "markers": "python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3, 3.4, 3.5'",
            "version": "==6.1.0"
        },
        "psycopg2": {
            "hashes": [
                "sha256:121081ea2e76729acfb0673ff33755e8703d45e926e416cb59bae3a86c6a4981",
                "sha256:38a8dcc6856f569068b47de286b472b7c473ac7977243593a288ebce0dc89516",
                "sha256:426f9f29bde126913a20a96ff8ce7d73fd8a216cfb323b1f04da402d452853c3",
                "sha256:5e0d98cade4f0e0304d7d6f25bbfbc5bd186e07b38eac65379309c4ca3193efa",
                "sha256:7e2dacf8b009a1c1e843b5213a87f7c544b2b042476ed7755be813eaf4e8347a",
                "sha256:a7653d00b732afb6fc597e29c50ad28087dcb4fbfb28e86092277a559ae4e693",
                "sha256:ade01303ccf7ae12c356a5e10911c9e1c51136003a9a1d92f7aa9d010fb98372",
                "sha256:bac58c024c9922c23550af2a581998624d6e02350f4ae9c5f0bc642c633a2d5e",
                "sha256:c92811b2d4c9b6ea0285942b2e7cac98a59e166d59c588fe5cfe1eda58e72d59",
                "sha256:d1454bde93fb1e224166811694d600e746430c006fbb031ea06ecc2ea41bf156",
                "sha256:d735786acc7dd25815e89cc4ad529a43af779db2e25aa7c626de864127e5a024",
                "sha256:de80739447af31525feddeb8effd640782cf5998e1a4e9192ebdf829717e3913",
                "sha256:ff432630e510709564c01dafdbe996cb552e0b9f3f065eb89bdce5bd31fabf4c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==2.9.9"
        },
        "pure-eval": {
            "hashes": [
                "sha256:1db8e35b67b3d218d818ae653e27f06c3aa420901fa7b081ca98cbedc874e0d0",
                "sha256:5f4e983f40564c576c7c8635ae88db5956bb2229d7e9237d03b3c0b0190eaf42"
            ],
            "index": "pypi",
            "version": "==0.2.3"
        },
        "pyasn1": {
            "hashes": [
                "sha256:3a35ab2c4b5ef98e17dfdec8ab074046fbda76e281c5a706ccd82328cfc8f64c",
                "sha256:cca4bb0f2df5504f02f6f8a775b6e416ff9b0b3b16f7ee80b5a3153d9b804473"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.6.0"
        },
        "pyasn1-modules": {
            "hashes": [
                "sha256:831dbcea1b177b28c9baddf4c6d1013c24c3accd14a1873fffaa6a2e905f17b6",
                "sha256:be04f15b66c206eed667e0bb5ab27e2b1855ea54a842e5037738099e8ca4ae0b"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.4.0"
        },
        "pycparser": {
            "hashes": [
                "sha256:491c8be9c040f5390f5bf44a5b07752bd07f56edf992381b05c701439eec10f6",
                "sha256:c3702b6d3dd8c7abc1afa565d7e63d53a1d0bd86cdc24edd75470f4de499cfcc"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.22"
        },
        "pyct": {
            "hashes": [
                "sha256:a4038a8885059ab8cac6f946ea30e0b5e6bdbe0b92b6723f06737035f9d65e8c",
                "sha256:dd9f4ac5cbd8e37c352c04036062d3c5f67efec76d404761ef16b0cbf26aa6a0"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==0.5.0"
        },
        "pygments": {
            "hashes": [
                "sha256:786ff802f32e91311bff3889f6e9a86e81505fe99f2735bb6d60ae0c5004f199",
                "sha256:b8e6aca0523f3ab76fee51799c488e38782ac06eafcf95e7ba832985c8e7b13a"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.18.0"
        },
        "pyopenssl": {
            "hashes": [
                "sha256:17ed5be5936449c5418d1cd269a1a9e9081bc54c17aed272b45856a3d3dc86ad",
                "sha256:cabed4bfaa5df9f1a16c0ef64a0cb65318b5cd077a7eda7d6970131ca2f41a6f"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==24.1.0"
        },
        "pyparsing": {
            "hashes": [
                "sha256:93d9577b88da0bbea8cc8334ee8b918ed014968fd2ec383e868fb8afb1ccef84",
                "sha256:cbf74e27246d595d9a74b186b810f6fbb86726dbf3b9532efb343f6d7294fe9c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==3.2.0"
        },
        "python-dateutil": {
            "hashes": [
                "sha256:37dd54208da7e1cd875388217d5e00ebd4179249f90fb72437e91a35459a0ad3",
                "sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427"
            ],
            "index": "pypi",
            "markers": "python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
            "version": "==2.9.0.post0"
        },
        "pytz": {
            "hashes": [
                "sha256:2aa355083c50a0f93fa581709deac0c9ad65cca8a9e9beac660adcbd493c798a",
                "sha256:31c7c1817eb7fae7ca4b8c7ee50c72f93aa2dd863de768e1ef4245d426aa0725"
            ],
            "index": "pypi",
            "version": "==2024.2"
        },
        "pyviz-comms": {
            "hashes": [
                "sha256:fd26951eebc7950106d481655d91ba06296d4cf352dffb1d03f88f959832448e",
                "sha256:fde4a017c2213ecee63a9a6741431c845e42a5c7b1588e4a7ba2e4370c583728"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.0.3"
        },
        "pywin32": {
            "hashes": [
                "sha256:00b3e11ef09ede56c6a43c71f2d31857cf7c54b0ab6e78ac659497abd2834f47",
                "sha256:100a5442b7332070983c4cd03f2e906a5648a5104b8a7f50175f7906efd16bb6",
                "sha256:13dcb914ed4347019fbec6697a01a0aec61019c1046c2b905410d197856326a6",
                "sha256:1c44539a37a5b7b21d02ab34e6a4d314e0788f1690d65b48e9b0b89f31abbbed",
                "sha256:1f696ab352a2ddd63bd07430080dd598e6369152ea13a25ebcdd2f503a38f1ff",
                "sha256:3b92622e29d651c6b783e368ba7d6722b1634b8e70bd376fd7610fe1992e19de",
                "sha256:4fc888c59b3c0bef905ce7eb7e2106a07712015ea1c8234b703a088d46110e8e",
                "sha256:575621b90f0dc2695fec346b2d6302faebd4f0f45c05ea29404cefe35d89442b",
                "sha256:5794e764ebcabf4ff08c555b31bd348c9025929371763b2183172ff4708152f0",
                "sha256:587f3e19696f4bf96fde9d8a57cec74a57021ad5f204c9e627e15c33ff568897",
                "sha256:5d8c8015b24a7d6855b1550d8e660d8daa09983c80e5daf89a273e5c6fb5095a",
                "sha256:71b3322d949b4cc20776436a9c9ba0eeedcbc9c650daa536df63f0ff111bb920",
                "sha256:7873ca4dc60ab3287919881a7d4f88baee4a6e639aa6962de25a98ba6b193341",
                "sha256:796ff4426437896550d2981b9c2ac0ffd75238ad9ea2d3bfa67a1abd546d262e",
                "sha256:9b4de86c8d909aed15b7011182c8cab38c8850de36e6afb1f0db22b8959e3091",
                "sha256:a5ab5381813b40f264fa3495b98af850098f814a25a63589a8e9eb12560f450c",
                "sha256:ef313c46d4c18dfb82a2431e3051ac8f112ccee1a34f29c263c583c568db63cd",
                "sha256:fd380990e792eaf6827fcb7e187b2b4b1cede0585e3d0c9e84201ec27b9905e4"
            ],
            "index": "pypi",
            "version": "==308"
        },
        "pyyaml": {
            "hashes": [
                "sha256:01179a4a8559ab5de078078f37e5c1a30d76bb88519906844fd7bdea1b7729ff",
                "sha256:0833f8694549e586547b576dcfaba4a6b55b9e96098b36cdc7ebefe667dfed48",
                "sha256:0a9a2848a5b7feac301353437eb7d5957887edbf81d56e903999a75a3d743086",
                "sha256:0b69e4ce7a131fe56b7e4d770c67429700908fc0752af059838b1cfb41960e4e",
                "sha256:0ffe8360bab4910ef1b9e87fb812d8bc0a308b0d0eef8c8f44e0254ab3b07133",
                "sha256:11d8f3dd2b9c1207dcaf2ee0bbbfd5991f571186ec9cc78427ba5bd32afae4b5",
                "sha256:17e311b6c678207928d649faa7cb0d7b4c26a0ba73d41e99c4fff6b6c3276484",
                "sha256:1e2120ef853f59c7419231f3bf4e7021f1b936f6ebd222406c3b60212205d2ee",
                "sha256:1f71ea527786de97d1a0cc0eacd1defc0985dcf6b3f17bb77dcfc8c34bec4dc5",
                "sha256:23502f431948090f597378482b4812b0caae32c22213aecf3b55325e049a6c68",
                "sha256:24471b829b3bf607e04e88d79542a9d48bb037c2267d7927a874e6c205ca7e9a",
                "sha256:29717114e51c84ddfba879543fb232a6ed60086602313ca38cce623c1d62cfbf",
                "sha256:2e99c6826ffa974fe6e27cdb5ed0021786b03fc98e5ee3c5bfe1fd5015f42b99",
                "sha256:39693e1f8320ae4f43943590b49779ffb98acb81f788220ea932a6b6c51004d8",
                "sha256:3ad2a3decf9aaba3d29c8f537ac4b243e36bef957511b4766cb0057d32b0be85",
                "sha256:3b1fdb9dc17f5a7677423d508ab4f243a726dea51fa5e70992e59a7411c89d19",
                "sha256:41e4e3953a79407c794916fa277a82531dd93aad34e29c2a514c2c0c5fe971cc",
                "sha256:43fa96a3ca0d6b1812e01ced1044a003533c47f6ee8aca31724f78e93ccc089a",
                "sha256:50187695423ffe49e2deacb8cd10510bc361faac997de9efef88badc3bb9e2d1",
                "sha256:5ac9328ec4831237bec75defaf839f7d4564be1e6b25ac710bd1a96321cc8317",
                "sha256:5d225db5a45f21e78dd9358e58a98702a0302f2659a3c6cd320564b75b86f47c",
                "sha256:6395c297d42274772abc367baaa79683958044e5d3835486c16da75d2a694631",
                "sha256:688ba32a1cffef67fd2e9398a2efebaea461578b0923624778664cc1c914db5d",
                "sha256:68ccc6023a3400877818152ad9a1033e3db8625d899c72eacb5a668902e4d652",
                "sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5",
                "sha256:797b4f722ffa07cc8d62053e4cff1486fa6dc094105d13fea7b1de7d8bf71c9e",
                "sha256:7c36280e6fb8385e520936c3cb3b8042851904eba0e58d277dca80a5cfed590b",
                "sha256:7e7401d0de89a9a855c839bc697c079a4af81cf878373abd7dc625847d25cbd8",
                "sha256:80bab7bfc629882493af4aa31a4cfa43a4c57c83813253626916b8c7ada83476",
                "sha256:82d09873e40955485746739bcb8b4586983670466c23382c19cffecbf1fd8706",
                "sha256:8388ee1976c416731879ac16da0aff3f63b286ffdd57cdeb95f3f2e085687563",
                "sha256:8824b5a04a04a047e72eea5cec3bc266db09e35de6bdfe34c9436ac5ee27d237",
                "sha256:8b9c7197f7cb2738065c481a0461e50ad02f18c78cd75775628afb4d7137fb3b",
                "sha256:9056c1ecd25795207ad294bcf39f2db3d845767be0ea6e6a34d856f006006083",
                "sha256:936d68689298c36b53b29f23c6dbb74de12b4ac12ca6cfe0e047bedceea56180",
                "sha256:9b22676e8097e9e22e36d6b7bda33190d0d400f345f23d4065d48f4ca7ae0425",
                "sha256:a4d3091415f010369ae4ed1fc6b79def9416358877534caf6a0fdd2146c87a3e",
                "sha256:a8786accb172bd8afb8be14490a16625cbc387036876ab6ba70912730faf8e1f",
                "sha256:a9f8c2e67970f13b16084e04f134610fd1d374bf477b17ec1599185cf611d725",
                "sha256:bc2fa7c6b47d6bc618dd7fb02ef6fdedb1090ec036abab80d4681424b84c1183",
                "sha256:c70c95198c015b85feafc136515252a261a84561b7b1d51e3384e0655ddf25ab",
                "sha256:cc1c1159b3d456576af7a3e4d1ba7e6924cb39de8f67111c735f6fc832082774",
                "sha256:ce826d6ef20b1bc864f0a68340c8b3287705cae2f8b4b1d932177dcc76721725",
                "sha256:d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e",
                "sha256:d7fded462629cfa4b685c5416b949ebad6cec74af5e2d42905d41e257e0869f5",
                "sha256:d84a1718ee396f54f3a086ea0a66d8e552b2ab2017ef8b420e92edbc841c352d",
                "sha256:d8e03406cac8513435335dbab54c0d385e4a49e4945d2909a581c83647ca0290",
                "sha256:e10ce637b18caea04431ce14fabcf5c64a1c61ec9c56b071a4b7ca131ca52d44",
                "sha256:ec031d5d2feb36d1d1a24380e4db6d43695f3748343d99434e6f5f9156aaa2ed",
                "sha256:ef6107725bd54b262d6dedcc2af448a266975032bc85ef0172c5f059da6325b4",
                "sha256:efdca5630322a10774e8e98e1af481aad470dd62c3170801852d752aa7a783ba",
                "sha256:f753120cb8181e736c57ef7636e83f31b9c0d1722c516f7e86cf15b7aa57ff12",
                "sha256:ff3824dc5261f50c9b0dfb3be22b4567a6f938ccce4587b38952d85fd9e9afe4"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==6.0.2"
        },
        "pyzmq": {
            "hashes": [
                "sha256:007137c9ac9ad5ea21e6ad97d3489af654381324d5d3ba614c323f60dab8fae6",
                "sha256:034da5fc55d9f8da09015d368f519478a52675e558c989bfcb5cf6d4e16a7d2a",
                "sha256:05590cdbc6b902101d0e65d6a4780af14dc22914cc6ab995d99b85af45362cc9",
                "sha256:070672c258581c8e4f640b5159297580a9974b026043bd4ab0470be9ed324f1f",
                "sha256:0aca98bc423eb7d153214b2df397c6421ba6373d3397b26c057af3c904452e37",
                "sha256:0bed0e799e6120b9c32756203fb9dfe8ca2fb8467fed830c34c877e25638c3fc",
                "sha256:0d987a3ae5a71c6226b203cfd298720e0086c7fe7c74f35fa8edddfbd6597eed",
                "sha256:0eaa83fc4c1e271c24eaf8fb083cbccef8fde77ec8cd45f3c35a9a123e6da097",
                "sha256:160c7e0a5eb178011e72892f99f918c04a131f36056d10d9c1afb223fc952c2d",
                "sha256:17bf5a931c7f6618023cdacc7081f3f266aecb68ca692adac015c383a134ca52",
                "sha256:17c412bad2eb9468e876f556eb4ee910e62d721d2c7a53c7fa31e643d35352e6",
                "sha256:18c8dc3b7468d8b4bdf60ce9d7141897da103c7a4690157b32b60acb45e333e6",
                "sha256:1a534f43bc738181aa7cbbaf48e3eca62c76453a40a746ab95d4b27b1111a7d2",
                "sha256:1c17211bc037c7d88e85ed8b7d8f7e52db6dc8eca5590d162717c654550f7282",
                "sha256:1f3496d76b89d9429a656293744ceca4d2ac2a10ae59b84c1da9b5165f429ad3",
                "sha256:1fcc03fa4997c447dce58264e93b5aa2d57714fbe0f06c07b7785ae131512732",
                "sha256:226af7dcb51fdb0109f0016449b357e182ea0ceb6b47dfb5999d569e5db161d5",
                "sha256:23f4aad749d13698f3f7b64aad34f5fc02d6f20f05999eebc96b89b01262fb18",
                "sha256:25bf2374a2a8433633c65ccb9553350d5e17e60c8eb4de4d92cc6bd60f01d306",
                "sha256:28ad5233e9c3b52d76196c696e362508959741e1a005fb8fa03b51aea156088f",
                "sha256:28c812d9757fe8acecc910c9ac9dafd2ce968c00f9e619db09e9f8f54c3a68a3",
                "sha256:29c6a4635eef69d68a00321e12a7d2559fe2dfccfa8efae3ffb8e91cd0b36a8b",
                "sha256:29c7947c594e105cb9e6c466bace8532dc1ca02d498684128b339799f5248277",
                "sha256:2a50625acdc7801bc6f74698c5c583a491c61d73c6b7ea4dee3901bb99adb27a",
                "sha256:2ae90ff9dad33a1cfe947d2c40cb9cb5e600d759ac4f0fd22616ce6540f72797",
                "sha256:2c4a71d5d6e7b28a47a394c0471b7e77a0661e2d651e7ae91e0cab0a587859ca",
                "sha256:2ea4ad4e6a12e454de05f2949d4beddb52460f3de7c8b9d5c46fbb7d7222e02c",
                "sha256:2eb7735ee73ca1b0d71e0e67c3739c689067f055c764f73aac4cc8ecf958ee3f",
                "sha256:31507f7b47cc1ead1f6e86927f8ebb196a0bab043f6345ce070f412a59bf87b5",
                "sha256:35cffef589bcdc587d06f9149f8d5e9e8859920a071df5a2671de2213bef592a",
                "sha256:367b4f689786fca726ef7a6c5ba606958b145b9340a5e4808132cc65759abd44",
                "sha256:39887ac397ff35b7b775db7201095fc6310a35fdbae85bac4523f7eb3b840e20",
                "sha256:3a495b30fc91db2db25120df5847d9833af237546fd59170701acd816ccc01c4",
                "sha256:3b55a4229ce5da9497dd0452b914556ae58e96a4381bb6f59f1305dfd7e53fc8",
                "sha256:402b190912935d3db15b03e8f7485812db350d271b284ded2b80d2e5704be780",
                "sha256:43a47408ac52647dfabbc66a25b05b6a61700b5165807e3fbd40063fcaf46386",
                "sha256:4661c88db4a9e0f958c8abc2b97472e23061f0bc737f6f6179d7a27024e1faa5",
                "sha256:46a446c212e58456b23af260f3d9fb785054f3e3653dbf7279d8f2b5546b21c2",
                "sha256:470d4a4f6d48fb34e92d768b4e8a5cc3780db0d69107abf1cd7ff734b9766eb0",
                "sha256:49d34ab71db5a9c292a7644ce74190b1dd5a3475612eefb1f8be1d6961441971",
                "sha256:4d29ab8592b6ad12ebbf92ac2ed2bedcfd1cec192d8e559e2e099f648570e19b",
                "sha256:4d80b1dd99c1942f74ed608ddb38b181b87476c6a966a88a950c7dee118fdf50",
                "sha256:4da04c48873a6abdd71811c5e163bd656ee1b957971db7f35140a2d573f6949c",
                "sha256:4f78c88905461a9203eac9faac157a2a0dbba84a0fd09fd29315db27be40af9f",
                "sha256:4ff9dc6bc1664bb9eec25cd17506ef6672d506115095411e237d571e92a58231",
                "sha256:5506f06d7dc6ecf1efacb4a013b1f05071bb24b76350832c96449f4a2d95091c",
                "sha256:55cf66647e49d4621a7e20c8d13511ef1fe1efbbccf670811864452487007e08",
                "sha256:5a509df7d0a83a4b178d0f937ef14286659225ef4e8812e05580776c70e155d5",
                "sha256:5c2b3bfd4b9689919db068ac6c9911f3fcb231c39f7dd30e3138be94896d18e6",
                "sha256:6835dd60355593de10350394242b5757fbbd88b25287314316f266e24c61d073",
                "sha256:689c5d781014956a4a6de61d74ba97b23547e431e9e7d64f27d4922ba96e9d6e",
                "sha256:6a96179a24b14fa6428cbfc08641c779a53f8fcec43644030328f44034c7f1f4",
                "sha256:6ace4f71f1900a548f48407fc9be59c6ba9d9aaf658c2eea6cf2779e72f9f317",
                "sha256:6b274e0762c33c7471f1a7471d1a2085b1a35eba5cdc48d2ae319f28b6fc4de3",
                "sha256:706e794564bec25819d21a41c31d4df2d48e1cc4b061e8d345d7fb4dd3e94072",
                "sha256:70fc7fcf0410d16ebdda9b26cbd8bf8d803d220a7f3522e060a69a9c87bf7bad",
                "sha256:7133d0a1677aec369d67dd78520d3fa96dd7f3dcec99d66c1762870e5ea1a50a",
                "sha256:7445be39143a8aa4faec43b076e06944b8f9d0701b669df4af200531b21e40bb",
                "sha256:76589c020680778f06b7e0b193f4b6dd66d470234a16e1df90329f5e14a171cd",
                "sha256:76589f2cd6b77b5bdea4fca5992dc1c23389d68b18ccc26a53680ba2dc80ff2f",
                "sha256:77eb0968da535cba0470a5165468b2cac7772cfb569977cff92e240f57e31bef",
                "sha256:794a4562dcb374f7dbbfb3f51d28fb40123b5a2abadee7b4091f93054909add5",
                "sha256:7ad1bc8d1b7a18497dda9600b12dc193c577beb391beae5cd2349184db40f187",
                "sha256:7f98f6dfa8b8ccaf39163ce872bddacca38f6a67289116c8937a02e30bbe9711",
                "sha256:8423c1877d72c041f2c263b1ec6e34360448decfb323fa8b94e85883043ef988",
                "sha256:8685fa9c25ff00f550c1fec650430c4b71e4e48e8d852f7ddcf2e48308038640",
                "sha256:878206a45202247781472a2d99df12a176fef806ca175799e1c6ad263510d57c",
                "sha256:89289a5ee32ef6c439086184529ae060c741334b8970a6855ec0b6ad3ff28764",
                "sha256:8ab5cad923cc95c87bffee098a27856c859bd5d0af31bd346035aa816b081fe1",
                "sha256:8b435f2753621cd36e7c1762156815e21c985c72b19135dac43a7f4f31d28dd1",
                "sha256:8be4700cd8bb02cc454f630dcdf7cfa99de96788b80c51b60fe2fe1dac480289",
                "sha256:8c997098cc65e3208eca09303630e84d42718620e83b733d0fd69543a9cab9cb",
                "sha256:8ea039387c10202ce304af74def5021e9adc6297067f3441d348d2b633e8166a",
                "sha256:8f7e66c7113c684c2b3f1c83cdd3376103ee0ce4c49ff80a648643e57fb22218",
                "sha256:90412f2db8c02a3864cbfc67db0e3dcdbda336acf1c469526d3e869394fe001c",
                "sha256:92a78853d7280bffb93df0a4a6a2498cba10ee793cc8076ef797ef2f74d107cf",
                "sha256:989d842dc06dc59feea09e58c74ca3e1678c812a4a8a2a419046d711031f69c7",
                "sha256:9cb3a6460cdea8fe8194a76de8895707e61ded10ad0be97188cc8463ffa7e3a8",
                "sha256:9dd8cd1aeb00775f527ec60022004d030ddc51d783d056e3e23e74e623e33726",
                "sha256:9ed69074a610fad1c2fda66180e7b2edd4d31c53f2d1872bc2d1211563904cd9",
                "sha256:9edda2df81daa129b25a39b86cb57dfdfe16f7ec15b42b19bfac503360d27a93",
                "sha256:a2224fa4a4c2ee872886ed00a571f5e967c85e078e8e8c2530a2fb01b3309b88",
                "sha256:a4f96f0d88accc3dbe4a9025f785ba830f968e21e3e2c6321ccdfc9aef755115",
                "sha256:aedd5dd8692635813368e558a05266b995d3d020b23e49581ddd5bbe197a8ab6",
                "sha256:aee22939bb6075e7afededabad1a56a905da0b3c4e3e0c45e75810ebe3a52672",
                "sha256:b1d464cb8d72bfc1a3adc53305a63a8e0cac6bc8c5a07e8ca190ab8d3faa43c2",
                "sha256:b8f86dd868d41bea9a5f873ee13bf5551c94cf6bc51baebc6f85075971fe6eea",
                "sha256:bc6bee759a6bddea5db78d7dcd609397449cb2d2d6587f48f3ca613b19410cfc",
                "sha256:bea2acdd8ea4275e1278350ced63da0b166421928276c7c8e3f9729d7402a57b",
                "sha256:bfa832bfa540e5b5c27dcf5de5d82ebc431b82c453a43d141afb1e5d2de025fa",
                "sha256:c0e6091b157d48cbe37bd67233318dbb53e1e6327d6fc3bb284afd585d141003",
                "sha256:c3789bd5768ab5618ebf09cef6ec2b35fed88709b104351748a63045f0ff9797",
                "sha256:c530e1eecd036ecc83c3407f77bb86feb79916d4a33d11394b8234f3bd35b940",
                "sha256:c811cfcd6a9bf680236c40c6f617187515269ab2912f3d7e8c0174898e2519db",
                "sha256:c92d73464b886931308ccc45b2744e5968cbaade0b1d6aeb40d8ab537765f5bc",
                "sha256:cccba051221b916a4f5e538997c45d7d136a5646442b1231b916d0164067ea27",
                "sha256:cdeabcff45d1c219636ee2e54d852262e5c2e085d6cb476d938aee8d921356b3",
                "sha256:ced65e5a985398827cc9276b93ef6dfabe0273c23de8c7931339d7e141c2818e",
                "sha256:d049df610ac811dcffdc147153b414147428567fbbc8be43bb8885f04db39d98",
                "sha256:dacd995031a01d16eec825bf30802fceb2c3791ef24bcce48fa98ce40918c27b",
                "sha256:ddf33d97d2f52d89f6e6e7ae66ee35a4d9ca6f36eda89c24591b0c40205a3629",
                "sha256:ded0fc7d90fe93ae0b18059930086c51e640cdd3baebdc783a695c77f123dcd9",
                "sha256:e3e0210287329272539eea617830a6a28161fbbd8a3271bf4150ae3e58c5d0e6",
                "sha256:e6fa2e3e683f34aea77de8112f6483803c96a44fd726d7358b9888ae5bb394ec",
                "sha256:ea0eb6af8a17fa272f7b98d7bebfab7836a0d62738e16ba380f440fceca2d951",
                "sha256:ea7f69de383cb47522c9c208aec6dd17697db7875a4674c4af3f8cfdac0bdeae",
                "sha256:eac5174677da084abf378739dbf4ad245661635f1600edd1221f150b165343f4",
                "sha256:fc4f7a173a5609631bb0c42c23d12c49df3966f89f496a51d3eb0ec81f4519d6",
                "sha256:fdb5b3e311d4d4b0eb8b3e8b4d1b0a512713ad7e6a68791d0923d1aec433d919"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==26.2.0"
        },
        "redis": {
            "hashes": [
                "sha256:7adc2835c7a9b5033b7ad8f8918d09b7344188228809c98df07af226d39dec91",
                "sha256:ec31f2ed9675cc54c21ba854cfe0462e6faf1d83c8ce5944709db8a4700b9c61"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==5.0.4"
        },
        "referencing": {
            "hashes": [
                "sha256:df2e89862cd09deabbdba16944cc3f10feb6b3e6f18e902f7cc25609a34775aa",
                "sha256:e8699adbbf8b5c7de96d8ffa0eb5c158b3beafce084968e2ea8bb08c6794dcd0"
            ],
            "markers": "python_version >= '3.9'",
            "version": "==0.36.2"
        },
        "requests": {
            "hashes": [
                "sha256:58cd2187c01e70e6e26505bca751777aa9f2ee0b7f4300988b709f44e013003f",
                "sha256:942c5a758f98d790eaed1a29cb6eefc7ffb0d1cf7af05c3d2791656dbd6ad1e1"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==2.31.0"
        },
        "retrying": {
            "hashes": [
                "sha256:345da8c5765bd982b1d1915deb9102fd3d1f7ad16bd84a9700b85f64d24e8f3e",
                "sha256:8cc4d43cb8e1125e0ff3344e9de678fefd85db3b750b81b2240dc0183af37b35"
            ],
            "index": "pypi",
            "version": "==1.3.4"
        },
        "rich": {
            "hashes": [
                "sha256:439594978a49a09530cff7ebc4b5c7103ef57baf48d5ea3184f21d9a2befa098",
                "sha256:6049d5e6ec054bf2779ab3358186963bac2ea89175919d699e378b99738c2a90"
            ],
            "index": "pypi",
            "markers": "python_full_version >= '3.8.0'",
            "version": "==13.9.4"
        },
        "rpds-py": {
            "hashes": [
                "sha256:0047638c3aa0dbcd0ab99ed1e549bbf0e142c9ecc173b6492868432d8989a046",
                "sha256:006f4342fe729a368c6df36578d7a348c7c716be1da0a1a0f86e3021f8e98724",
                "sha256:041f00419e1da7a03c46042453598479f45be3d787eb837af382bfc169c0db33",
                "sha256:04ecf5c1ff4d589987b4d9882872f80ba13da7d42427234fce8f22efb43133bc",
                "sha256:04f2b712a2206e13800a8136b07aaedc23af3facab84918e7aa89e4be0260032",
                "sha256:0aeb3329c1721c43c58cae274d7d2ca85c1690d89485d9c63a006cb79a85771a",
                "sha256:0e374c0ce0ca82e5b67cd61fb964077d40ec177dd2c4eda67dba130de09085c7",
                "sha256:0f00c16e089282ad68a3820fd0c831c35d3194b7cdc31d6e469511d9bffc535c",
                "sha256:174e46569968ddbbeb8a806d9922f17cd2b524aa753b468f35b97ff9c19cb718",
                "sha256:1b221c2457d92a1fb3c97bee9095c874144d196f47c038462ae6e4a14436f7bc",
                "sha256:208b3a70a98cf3710e97cabdc308a51cd4f28aa6e7bb11de3d56cd8b74bab98d",
                "sha256:20f2712bd1cc26a3cc16c5a1bfee9ed1abc33d4cdf1aabd297fe0eb724df4272",
                "sha256:24795c099453e3721fda5d8ddd45f5dfcc8e5a547ce7b8e9da06fecc3832e26f",
                "sha256:2a0f156e9509cee987283abd2296ec816225145a13ed0391df8f71bf1d789e2d",
                "sha256:2b2356688e5d958c4d5cb964af865bea84db29971d3e563fb78e46e20fe1848b",
                "sha256:2c13777ecdbbba2077670285dd1fe50828c8742f6a4119dbef6f83ea13ad10fb",
                "sha256:2d3ee4615df36ab8eb16c2507b11e764dcc11fd350bbf4da16d09cda11fcedef",
                "sha256:2d53747da70a4e4b17f559569d5f9506420966083a31c5fbd84e764461c4444b",
                "sha256:32bab0a56eac685828e00cc2f5d1200c548f8bc11f2e44abf311d6b548ce2e45",
                "sha256:34d90ad8c045df9a4259c47d2e16a3f21fdb396665c94520dbfe8766e62187a4",
                "sha256:369d9c6d4c714e36d4a03957b4783217a3ccd1e222cdd67d464a3a479fc17796",
                "sha256:3a55fc10fdcbf1a4bd3c018eea422c52cf08700cf99c28b5cb10fe97ab77a0d3",
                "sha256:3d2d8e4508e15fc05b31285c4b00ddf2e0eb94259c2dc896771966a163122a0c",
                "sha256:3fab5f4a2c64a8fb64fc13b3d139848817a64d467dd6ed60dcdd6b479e7febc9",
                "sha256:43dba99f00f1d37b2a0265a259592d05fcc8e7c19d140fe51c6e6f16faabeb1f",
                "sha256:44d51febb7a114293ffd56c6cf4736cb31cd68c0fddd6aa303ed09ea5a48e029",
                "sha256:493fe54318bed7d124ce272fc36adbf59d46729659b2c792e87c3b95649cdee9",
                "sha256:4b28e5122829181de1898c2c97f81c0b3246d49f585f22743a1246420bb8d399",
                "sha256:4cd031e63bc5f05bdcda120646a0d32f6d729486d0067f09d79c8db5368f4586",
                "sha256:528927e63a70b4d5f3f5ccc1fa988a35456eb5d15f804d276709c33fc2f19bda",
                "sha256:564c96b6076a98215af52f55efa90d8419cc2ef45d99e314fddefe816bc24f91",
                "sha256:5db385bacd0c43f24be92b60c857cf760b7f10d8234f4bd4be67b5b20a7c0b6b",
                "sha256:5ef877fa3bbfb40b388a5ae1cb00636a624690dcb9a29a65267054c9ea86d88a",
                "sha256:5f6e3cec44ba05ee5cbdebe92d052f69b63ae792e7d05f1020ac5e964394080c",
                "sha256:5fc13b44de6419d1e7a7e592a4885b323fbc2f46e1f22151e3a8ed3b8b920405",
                "sha256:60748789e028d2a46fc1c70750454f83c6bdd0d05db50f5ae83e2db500b34da5",
                "sha256:60d9b630c8025b9458a9d114e3af579a2c54bd32df601c4581bd054e85258143",
                "sha256:619ca56a5468f933d940e1bf431c6f4e13bef8e688698b067ae68eb4f9b30e3a",
                "sha256:630d3d8ea77eabd6cbcd2ea712e1c5cecb5b558d39547ac988351195db433f6c",
                "sha256:63981feca3f110ed132fd217bf7768ee8ed738a55549883628ee3da75bb9cb78",
                "sha256:66420986c9afff67ef0c5d1e4cdc2d0e5262f53ad11e4f90e5e22448df485bf0",
                "sha256:675269d407a257b8c00a6b58205b72eec8231656506c56fd429d924ca00bb350",
                "sha256:6a4a535013aeeef13c5532f802708cecae8d66c282babb5cd916379b72110cf7",
                "sha256:6a727fd083009bc83eb83d6950f0c32b3c94c8b80a9b667c87f4bd1274ca30ba",
                "sha256:6e1daf5bf6c2be39654beae83ee6b9a12347cb5aced9a29eecf12a2d25fff664",
                "sha256:6eea559077d29486c68218178ea946263b87f1c41ae7f996b1f30a983c476a5a",
                "sha256:75a810b7664c17f24bf2ffd7f92416c00ec84b49bb68e6a0d93e542406336b56",
                "sha256:772cc1b2cd963e7e17e6cc55fe0371fb9c704d63e44cacec7b9b7f523b78919e",
                "sha256:78884d155fd15d9f64f5d6124b486f3d3f7fd7cd71a78e9670a0f6f6ca06fb2d",
                "sha256:79e8d804c2ccd618417e96720ad5cd076a86fa3f8cb310ea386a3e6229bae7d1",
                "sha256:7e80d375134ddb04231a53800503752093dbb65dad8dabacce2c84cccc78e964",
                "sha256:8097b3422d020ff1c44effc40ae58e67d93e60d540a65649d2cdaf9466030791",
                "sha256:8205ee14463248d3349131bb8099efe15cd3ce83b8ef3ace63c7e976998e7124",
                "sha256:8212ff58ac6dfde49946bea57474a386cca3f7706fc72c25b772b9ca4af6b79e",
                "sha256:823e74ab6fbaa028ec89615ff6acb409e90ff45580c45920d4dfdddb069f2120",
                "sha256:84e0566f15cf4d769dade9b366b7b87c959be472c92dffb70462dd0844d7cbad",
                "sha256:896c41007931217a343eff197c34513c154267636c8056fb409eafd494c3dcdc",
                "sha256:8aa362811ccdc1f8dadcc916c6d47e554169ab79559319ae9fae7d7752d0d60c",
                "sha256:8b3b397eefecec8e8e39fa65c630ef70a24b09141a6f9fc17b3c3a50bed6b50e",
                "sha256:8ebc7e65ca4b111d928b669713865f021b7773350eeac4a31d3e70144297baba",
                "sha256:9168764133fd919f8dcca2ead66de0105f4ef5659cbb4fa044f7014bed9a1797",
                "sha256:921ae54f9ecba3b6325df425cf72c074cd469dea843fb5743a26ca7fb2ccb149",
                "sha256:92558d37d872e808944c3c96d0423b8604879a3d1c86fdad508d7ed91ea547d5",
                "sha256:951cc481c0c395c4a08639a469d53b7d4afa252529a085418b82a6b43c45c240",
                "sha256:998c01b8e71cf051c28f5d6f1187abbdf5cf45fc0efce5da6c06447cba997034",
                "sha256:9abc80fe8c1f87218db116016de575a7998ab1629078c90840e8d11ab423ee25",
                "sha256:9be4f99bee42ac107870c61dfdb294d912bf81c3c6d45538aad7aecab468b6b7",
                "sha256:9c39438c55983d48f4bb3487734d040e22dad200dab22c41e331cee145e7a50d",
                "sha256:9d7e8ce990ae17dda686f7e82fd41a055c668e13ddcf058e7fb5e9da20b57793",
                "sha256:9ea7f4174d2e4194289cb0c4e172d83e79a6404297ff95f2875cf9ac9bced8ba",
                "sha256:a18fc371e900a21d7392517c6f60fe859e802547309e94313cd8181ad9db004d",
                "sha256:a36b452abbf29f68527cf52e181fced56685731c86b52e852053e38d8b60bc8d",
                "sha256:a5b66d1b201cc71bc3081bc2f1fc36b0c1f268b773e03bbc39066651b9e18391",
                "sha256:a824d2c7a703ba6daaca848f9c3d5cb93af0505be505de70e7e66829affd676e",
                "sha256:a88c0d17d039333a41d9bf4616bd062f0bd7aa0edeb6cafe00a2fc2a804e944f",
                "sha256:aa6800adc8204ce898c8a424303969b7aa6a5e4ad2789c13f8648739830323b7",
                "sha256:aad911555286884be1e427ef0dc0ba3929e6821cbeca2194b13dc415a462c7fd",
                "sha256:afc6e35f344490faa8276b5f2f7cbf71f88bc2cda4328e00553bd451728c571f",
                "sha256:b9a4df06c35465ef4d81799999bba810c68d29972bf1c31db61bfdb81dd9d5bb",
                "sha256:bb2954155bb8f63bb19d56d80e5e5320b61d71084617ed89efedb861a684baea",
                "sha256:bbc4362e06f950c62cad3d4abf1191021b2ffaf0b31ac230fbf0526453eee75e",
                "sha256:c0145295ca415668420ad142ee42189f78d27af806fcf1f32a18e51d47dd2052",
                "sha256:c30ff468163a48535ee7e9bf21bd14c7a81147c0e58a36c1078289a8ca7af0bd",
                "sha256:c347a20d79cedc0a7bd51c4d4b7dbc613ca4e65a756b5c3e57ec84bd43505b47",
                "sha256:c43583ea8517ed2e780a345dd9960896afc1327e8cf3ac8239c167530397440d",
                "sha256:c61a2cb0085c8783906b2f8b1f16a7e65777823c7f4d0a6aaffe26dc0d358dd9",
                "sha256:c9ca89938dff18828a328af41ffdf3902405a19f4131c88e22e776a8e228c5a8",
                "sha256:cc31e13ce212e14a539d430428cd365e74f8b2d534f8bc22dd4c9c55b277b875",
                "sha256:cdabcd3beb2a6dca7027007473d8ef1c3b053347c76f685f5f060a00327b8b65",
                "sha256:cf86f72d705fc2ef776bb7dd9e5fbba79d7e1f3e258bf9377f8204ad0fc1c51e",
                "sha256:d09dc82af2d3c17e7dd17120b202a79b578d79f2b5424bda209d9966efeed114",
                "sha256:d3aa13bdf38630da298f2e0d77aca967b200b8cc1473ea05248f6c5e9c9bdb44",
                "sha256:d69d003296df4840bd445a5d15fa5b6ff6ac40496f956a221c4d1f6f7b4bc4d9",
                "sha256:d6e109a454412ab82979c5b1b3aee0604eca4bbf9a02693bb9df027af2bfa91a",
                "sha256:d8551e733626afec514b5d15befabea0dd70a343a9f23322860c4f16a9430205",
                "sha256:d8754d872a5dfc3c5bf9c0e059e8107451364a30d9fd50f1f1a85c4fb9481164",
                "sha256:d8f9a6e7fd5434817526815f09ea27f2746c4a51ee11bb3439065f5fc754db58",
                "sha256:dbcbb6db5582ea33ce46a5d20a5793134b5365110d84df4e30b9d37c6fd40ad3",
                "sha256:e0f3ef95795efcd3b2ec3fe0a5bcfb5dadf5e3996ea2117427e524d4fbf309c6",
                "sha256:e13ae74a8a3a0c2f22f450f773e35f893484fcfacb00bb4344a7e0f4f48e1f97",
                "sha256:e274f62cbd274359eff63e5c7e7274c913e8e09620f6a57aae66744b3df046d6",
                "sha256:e838bf2bb0b91ee67bf2b889a1a841e5ecac06dd7a2b1ef4e6151e2ce155c7ae",
                "sha256:e8acd55bd5b071156bae57b555f5d33697998752673b9de554dd82f5b5352727",
                "sha256:e8e5ab32cf9eb3647450bc74eb201b27c185d3857276162c101c0f8c6374e098",
                "sha256:ebcb786b9ff30b994d5969213a8430cbb984cdd7ea9fd6df06663194bd3c450c",
                "sha256:ebea2821cdb5f9fef44933617be76185b80150632736f3d76e54829ab4a3b4d1",
                "sha256:ed0ef550042a8dbcd657dfb284a8ee00f0ba269d3f2286b0493b15a5694f9fe8",
                "sha256:eda5c1e2a715a4cbbca2d6d304988460942551e4e5e3b7457b50943cd741626d",
                "sha256:f5c0ed12926dec1dfe7d645333ea59cf93f4d07750986a586f511c0bc61fe103",
                "sha256:f6016bd950be4dcd047b7475fdf55fb1e1f59fc7403f387be0e8123e4a576d30",
                "sha256:f9e0057a509e096e47c87f753136c9b10d7a91842d8042c2ee6866899a717c0d",
                "sha256:fc1c892b1ec1f8cbd5da8de287577b455e388d9c328ad592eabbdcb6fc93bee5",
                "sha256:fc2c1e1b00f88317d9de6b2c2b39b012ebbfe35fe5e7bef980fd2a91f6100a07",
                "sha256:fd822f019ccccd75c832deb7aa040bb02d70a92eb15a2f16c7987b7ad4ee8d83"
            ],
            "markers": "python_version >= '3.9'",
            "version": "==0.24.0"
        },
        "scipy": {
            "hashes": [
                "sha256:0c2f95de3b04e26f5f3ad5bb05e74ba7f68b837133a4492414b3afd79dfe540e",
                "sha256:1729560c906963fc8389f6aac023739ff3983e727b1a4d87696b7bf108316a79",
                "sha256:278266012eb69f4a720827bdd2dc54b2271c97d84255b2faaa8f161a158c3b37",
                "sha256:2843f2d527d9eebec9a43e6b406fb7266f3af25a751aa91d62ff416f54170bc5",
                "sha256:2da0469a4ef0ecd3693761acbdc20f2fdeafb69e6819cc081308cc978153c675",
                "sha256:2ff0a7e01e422c15739ecd64432743cf7aae2b03f3084288f399affcefe5222d",
                "sha256:2ff38e22128e6c03ff73b6bb0f85f897d2362f8c052e3b8ad00532198fbdae3f",
                "sha256:30ac8812c1d2aab7131a79ba62933a2a76f582d5dbbc695192453dae67ad6310",
                "sha256:3a1b111fac6baec1c1d92f27e76511c9e7218f1695d61b59e05e0fe04dc59617",
                "sha256:4079b90df244709e675cdc8b93bfd8a395d59af40b72e339c2287c91860deb8e",
                "sha256:5149e3fd2d686e42144a093b206aef01932a0059c2a33ddfa67f5f035bdfe13e",
                "sha256:5a275584e726026a5699459aa72f828a610821006228e841b94275c4a7c08417",
                "sha256:631f07b3734d34aced009aaf6fedfd0eb3498a97e581c3b1e5f14a04164a456d",
                "sha256:716e389b694c4bb564b4fc0c51bc84d381735e0d39d3f26ec1af2556ec6aad94",
                "sha256:8426251ad1e4ad903a4514712d2fa8fdd5382c978010d1c6f5f37ef286a713ad",
                "sha256:8475230e55549ab3f207bff11ebfc91c805dc3463ef62eda3ccf593254524ce8",
                "sha256:8bddf15838ba768bb5f5083c1ea012d64c9a444e16192762bd858f1e126196d0",
                "sha256:8e32dced201274bf96899e6491d9ba3e9a5f6b336708656466ad0522d8528f69",
                "sha256:8f9ea80f2e65bdaa0b7627fb00cbeb2daf163caa015e59b7516395fe3bd1e066",
                "sha256:97c5dddd5932bd2a1a31c927ba5e1463a53b87ca96b5c9bdf5dfd6096e27efc3",
                "sha256:a49f6ed96f83966f576b33a44257d869756df6cf1ef4934f59dd58b25e0327e5",
                "sha256:af29a935803cc707ab2ed7791c44288a682f9c8107bc00f0eccc4f92c08d6e07",
                "sha256:b05d43735bb2f07d689f56f7b474788a13ed8adc484a85aa65c0fd931cf9ccd2",
                "sha256:b28d2ca4add7ac16ae8bb6632a3c86e4b9e4d52d3e34267f6e1b0c1f8d87e389",
                "sha256:b99722ea48b7ea25e8e015e8341ae74624f72e5f21fc2abd45f3a93266de4c5d",
                "sha256:baff393942b550823bfce952bb62270ee17504d02a1801d7fd0719534dfb9c84",
                "sha256:c0ee987efa6737242745f347835da2cc5bb9f1b42996a4d97d5c7ff7928cb6f2",
                "sha256:d0d2821003174de06b69e58cef2316a6622b60ee613121199cb2852a873f8cf3",
                "sha256:e0cf28db0f24a38b2a0ca33a85a54852586e43cf6fd876365c86e0657cfe7d73",
                "sha256:e4f5a7c49323533f9103d4dacf4e4f07078f360743dec7f7596949149efeec06",
                "sha256:eb58ca0abd96911932f688528977858681a59d61a7ce908ffd355957f7025cfc",
                "sha256:edaf02b82cd7639db00dbff629995ef185c8df4c3ffa71a5562a595765a06ce1",
                "sha256:fef8c87f8abfb884dac04e97824b61299880c43f4ce675dd2cbeadd3c9b466d2"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==1.14.1"
        },
        "service-identity": {
            "hashes": [
                "sha256:6829c9d62fb832c2e1c435629b0a8c476e1929881f28bee4d20bc24161009221",
                "sha256:a28caf8130c8a5c1c7a6f5293faaf239bbfb7751e4862436920ee6f2616f568a"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==24.1.0"
        },
        "setuptools": {
            "hashes": [
                "sha256:128ce7b8f33c3079fd1b067ecbb4051a66e8526e7b65f6cec075dfc650ddfa88",
                "sha256:e147c0549f27767ba362f9da434eab9c5dc0045d5304feb602a0af001089fc51"
            ],
            "markers": "python_version >= '3.9'",
            "version": "==79.0.1"
        },
        "six": {
            "hashes": [
                "sha256:1e61c37477a1626458e36f7b1d82aa5c9b094fa4802892072e49de9c60c4c926",
                "sha256:8abb2f1d86890a2dfb989f9a77cfcfd3e47c2a354b01111771326f8aa26e0254"
            ],
            "index": "pypi",
            "markers": "python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
            "version": "==1.16.0"
        },
        "sniffio": {
            "hashes": [
                "sha256:2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2",
                "sha256:f4324edc670a0f49750a81b895f35c3adb843cca46f0530f79fc1babb23789dc"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==1.3.1"
        },
        "sqlparse": {
            "hashes": [
                "sha256:714d0a4932c059d16189f58ef5411ec2287a4360f17cdd0edd2d09d4c5087c93",
                "sha256:c204494cd97479d0e39f28c93d46c0b2d5959c7b9ab904762ea6c7af211c8663"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==0.5.0"
        },
        "stack-data": {
            "hashes": [
                "sha256:836a778de4fec4dcd1dcd89ed8abff8a221f58308462e1c4aa2a3cf30148f0b9",
                "sha256:d5558e0c25a4cb0853cddad3d77da9891a08cb85dd9f9f91b9f8cd66e511e695"
            ],
            "index": "pypi",
            "version": "==0.6.3"
        },
        "statistics": {
            "hashes": [
                "sha256:2dc379b80b07bf2ddd5488cad06b2b9531da4dd31edb04dc9ec0dc226486c138"
            ],
            "index": "pypi",
            "version": "==1.0.3.5"
        },
        "sympy": {
            "hashes": [
                "sha256:9cebf7e04ff162015ce31c9c6c9144daa34a93bd082f54fd8f12deca4f47515f",
                "sha256:db36cdc64bf61b9b24578b6f7bab1ecdd2452cf008f34faa33776680c26d66f8"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.13.1"
        },
        "ta": {
            "hashes": [
                "sha256:de86af43418420bd6b088a2ea9b95483071bf453c522a8441bc2f12bcf8493fd"
            ],
            "index": "pypi",
            "version": "==0.11.0"
        },
        "tenacity": {
            "hashes": [
                "sha256:5398ef0d78e63f40007c1fb4c0bff96e1911394d2fa8d194f77619c05ff6cc8a",
                "sha256:ce510e327a630c9e1beaf17d42e6ffacc88185044ad85cf74c0a8887c6a0f88c"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==8.2.3"
        },
        "termcolor": {
            "hashes": [
                "sha256:37b17b5fc1e604945c2642c872a3764b5d547a48009871aea3edd3afa180afb8",
                "sha256:998d8d27da6d48442e8e1f016119076b690d962507531df4890fcd2db2ef8a6f"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==2.5.0"
        },
        "toolz": {
            "hashes": [
                "sha256:292c8f1c4e7516bf9086f8850935c799a874039c8bcf959d47b600e4c44a6236",
                "sha256:2c86e3d9a04798ac556793bced838816296a2f085017664e4995cb40a1047a02"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.0.0"
        },
        "torch": {
            "hashes": [
                "sha256:09e06f9949e1a0518c5b09fe95295bc9661f219d9ecb6f9893e5123e10696628",
                "sha256:265f70de5fd45b864d924b64be1797f86e76c8e48a02c2a3a6fc7ec247d2226c",
                "sha256:2bb8987f3bb1ef2675897034402373ddfc8f5ef0e156e2d8cfc47cacafdda4a9",
                "sha256:46763dcb051180ce1ed23d1891d9b1598e07d051ce4c9d14307029809c4d64f7",
                "sha256:4874a73507a300a5d089ceaff616a569e7bb7c613c56f37f63ec3ffac65259cf",
                "sha256:510c73251bee9ba02ae1cb6c9d4ee0907b3ce6020e62784e2d7598e0cfa4d6cc",
                "sha256:56eeaf2ecac90da5d9e35f7f35eb286da82673ec3c582e310a8d1631a1c02341",
                "sha256:683410f97984103148e31b38a8631acf31c3034c020c0f4d26171e7626d8317a",
                "sha256:6860df13d9911ac158f4c44031609700e1eba07916fff62e21e6ffa0a9e01961",
                "sha256:7979834102cd5b7a43cc64e87f2f3b14bd0e1458f06e9f88ffa386d07c7446e1",
                "sha256:7e1448426d0ba3620408218b50aa6ada88aeae34f7a239ba5431f6c8774b1239",
                "sha256:94fc63b3b4bedd327af588696559f68c264440e2503cc9e6954019473d74ae21",
                "sha256:9a610afe216a85a8b9bc9f8365ed561535c93e804c2a317ef7fabcc5deda0989",
                "sha256:9ea955317cfcd3852b1402b62af258ce735c2edeee42ca9419b6bc889e5ae053",
                "sha256:a0d5e1b9874c1a6c25556840ab8920569a7a4137afa8a63a32cee0bc7d89bd4b",
                "sha256:b789069020c5588c70d5c2158ac0aa23fd24a028f34a8b4fcb8fcb4d7efcf5fb",
                "sha256:bb2c6c3e65049f081940f5ab15c9136c7de40d3f01192541c920a07c7c585b7e",
                "sha256:c4f103a49830ce4c7561ef4434cc7926e5a5fe4e5eb100c19ab36ea1e2b634ab",
                "sha256:ccbd0320411fe1a3b3fec7b4d3185aa7d0c52adac94480ab024b5c8f74a0bf1d",
                "sha256:ff96f4038f8af9f7ec4231710ed4549da1bdebad95923953a25045dcf6fd87e2"
            ],
            "index": "pypi",
            "markers": "python_full_version >= '3.9.0'",
            "version": "==2.6.0"
        },
        "torchaudio": {
            "hashes": [
                "sha256:04803a969710bdb77a4ddfdb85a32fa9b9e0310dc91f7eb7e54d6083dd69bfab",
                "sha256:0eda1cd876f44fc014dc04aa680db2fa355a83df5d834398db6dd5f5cd911f4c",
                "sha256:0f0db5c997d031c34066d8be1c0ce7d2a1f2b6c016a92885b20b00bfeb17b753",
                "sha256:22798d5d8e37869bd5875d37f42270efbeb8ae94bda97fed40c1c5e0e1c62fa3",
                "sha256:377b177a3d683a9163e4cab5a06f0346dac9ff96fa527477338fd90fc6a2a4b6",
                "sha256:393fa74ec40d167f0170728ea21c9b5e0f830648fd02df7db2bf7e62f64245ec",
                "sha256:52182f6de4e7b342d139e54b703185d428de9cce3c4cf914a9b2ab2359d192a3",
                "sha256:52f15185349c370fc1faa84e8b8b2782c007472db9d586a16bba314130b322f2",
                "sha256:6291d9507dc1d6b4ffe8843fbfb201e6c8270dd8c42ad70bb76226c0ebdcad56",
                "sha256:66f2e0bd5ab56fd81419d2f5afb74a9a70141688594646441756c8c24f424a73",
                "sha256:715aa21f6bdbd085454c313ae3a2c7cc07bf2e8cf05752f819afb5b4c57f4e6f",
                "sha256:72e77055d8e742475c6dfacf59fab09b1fc94d4423e14897e188b67cad3851c6",
                "sha256:7d0e4b08c42325bf4b887de9a25c44ed882997001740e1bd7d901f65581cf1ab",
                "sha256:86d6239792bf94741a41acd6fe3d549faaf0d50e7275d17d076a190bd007e2f9",
                "sha256:8c1a4d08e35a9ceaadadbff6e60bcb3442482f800369be350103dfd08b4ddf52",
                "sha256:9d8e07789452efdb8132d62afe21f2293a72805f26c2891c6c53e4e4df38ddf6",
                "sha256:b521ea9618fb4c29a6f8071628170c222291f46a48a3bf424cfeb488f54af714",
                "sha256:c12fc41241b8dfce3ccc1917f1c81a0f92f532d9917706600046f1eb21d2d765",
                "sha256:c6386bfa478afae2137715bb60f35520e3b05f5fc6d3bcc6969cf9cdfb11c09c",
                "sha256:d855da878a28c2e5e6fb3d76fcddd544f4d957a320b29602cea5af2fe0ad1f3a"
            ],
            "index": "pypi",
            "version": "==2.6.0"
        },
        "torchvision": {
            "hashes": [
                "sha256:044ea420b8c6c3162a234cada8e2025b9076fa82504758cd11ec5d0f8cd9fa37",
                "sha256:084ac3f5a1f50c70d630a488d19bf62f323018eae1b1c1232f2b7047d3a7b76d",
                "sha256:110d115333524d60e9e474d53c7d20f096dbd8a080232f88dddb90566f90064c",
                "sha256:3891cd086c5071bda6b4ee9d266bb2ac39c998c045c2ebcd1e818b8316fb5d41",
                "sha256:49bcfad8cfe2c27dee116c45d4f866d7974bcf14a5a9fbef893635deae322f2f",
                "sha256:5045a3a5f21ec3eea6962fa5f2fa2d4283f854caec25ada493fcf4aab2925467",
                "sha256:5083a5b1fec2351bf5ea9900a741d54086db75baec4b1d21e39451e00977f1b1",
                "sha256:54454923a50104c66a9ab6bd8b73a11c2fc218c964b1006d5d1fe5b442c3dcb6",
                "sha256:54815e0a56dde95cc6ec952577f67e0dc151eadd928e8d9f6a7f821d69a4a734",
                "sha256:5568c5a1ff1b2ec33127b629403adb530fab81378d9018ca4ed6508293f76e2b",
                "sha256:5c22caeaae8b3c36d93459f1a5294e6f43306cff856ed243189a229331a404b4",
                "sha256:659b76c86757cb2ee4ca2db245e0740cfc3081fef46f0f1064d11adb4a8cee31",
                "sha256:669575b290ec27304569e188a960d12b907d5173f9cd65e86621d34c4e5b6c30",
                "sha256:6bdce3890fa949219de129e85e4f6d544598af3c073afe5c44e14aed15bdcbb2",
                "sha256:6eb75d41e3bbfc2f7642d0abba9383cc9ae6c5a4ca8d6b00628c225e1eaa63b3",
                "sha256:7e9e9afa150e40cd2a8f0701c43cb82a8d724f512896455c0918b987f94b84a4",
                "sha256:8c44b6924b530d0702e88ff383b65c4b34a0eaf666e8b399a73245574d546947",
                "sha256:9147f5e096a9270684e3befdee350f3cacafd48e0c54ab195f45790a9c146d67",
                "sha256:97a5814a93c793aaf0179cfc7f916024f4b63218929aee977b645633d074a49f",
                "sha256:abbf1d7b9d52c00d2af4afa8dac1fb3e2356f662a4566bd98dfaaa3634f4eb34",
                "sha256:b0c0b264b89ab572888244f2e0bad5b7eaf5b696068fc0b93e96f7c3c198953f",
                "sha256:b578bcad8a4083b40d34f689b19ca9f7c63e511758d806510ea03c29ac568f7b",
                "sha256:e6572227228ec521618cea9ac3a368c45b7f96f1f8622dc9f1afe891c044051f",
                "sha256:ff96666b94a55e802ea6796cabe788541719e6f4905fc59c380fed3517b6a64d",
                "sha256:ffa2a16499508fe6798323e455f312c7c55f2a88901c9a7c0fb1efa86cf7e327"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==0.21.0"
        },
        "tornado": {
            "hashes": [
                "sha256:072ce12ada169c5b00b7d92a99ba089447ccc993ea2143c9ede887e0937aa803",
                "sha256:1a017d239bd1bb0919f72af256a970624241f070496635784d9bf0db640d3fec",
                "sha256:2876cef82e6c5978fde1e0d5b1f919d756968d5b4282418f3146b79b58556482",
                "sha256:304463bd0772442ff4d0f5149c6f1c2135a1fae045adf070821c6cdc76980634",
                "sha256:908b71bf3ff37d81073356a5fadcc660eb10c1476ee6e2725588626ce7e5ca38",
                "sha256:92bad5b4746e9879fd7bf1eb21dce4e3fc5128d71601f80005afa39237ad620b",
                "sha256:932d195ca9015956fa502c6b56af9eb06106140d844a335590c1ec7f5277d10c",
                "sha256:bca9eb02196e789c9cb5c3c7c0f04fb447dc2adffd95265b2c7223a8a615ccbf",
                "sha256:c36e62ce8f63409301537222faffcef7dfc5284f27eec227389f2ad11b09d946",
                "sha256:c82c46813ba483a385ab2a99caeaedf92585a1f90defb5693351fa7e4ea0bf73",
                "sha256:e828cce1123e9e44ae2a50a9de3055497ab1d0aeb440c5ac23064d9e44880da1"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==6.4.2"
        },
        "tqdm": {
            "hashes": [
                "sha256:26445eca388f82e72884e0d580d5464cd801a3ea01e63e5601bdff9ba6a48de2",
                "sha256:f8aef9c52c08c13a65f30ea34f4e5aac3fd1a34959879d7e59e63027286627f2"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==4.67.1"
        },
        "traitlets": {
            "hashes": [
                "sha256:9ed0579d3502c94b4b3732ac120375cda96f923114522847de4b3bb98b96b6b7",
                "sha256:b74e89e397b1ed28cc831db7aea759ba6640cb3de13090ca145426688ff1ac4f"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==5.14.3"
        },
        "twisted": {
            "extras": [
                "tls"
            ],
            "hashes": [
                "sha256:039f2e6a49ab5108abd94de187fa92377abe5985c7a72d68d0ad266ba19eae63",
                "sha256:6b38b6ece7296b5e122c9eb17da2eeab3d98a198f50ca9efd00fb03e5b4fd4ae"
            ],
            "index": "pypi",
            "markers": "python_full_version >= '3.8.0'",
            "version": "==24.3.0"
        },
        "twisted-iocpsupport": {
            "hashes": [
                "sha256:0058c963c8957bcd3deda62122e89953c9de1e867a274facc9b15dde1a9f31e8",
                "sha256:0c1b5cf37f0b2d96cc3c9bc86fff16613b9f5d0ca565c96cf1f1fb8cfca4b81c",
                "sha256:196f7c7ccad4ba4d1783b1c4e1d1b22d93c04275cd780bf7498d16c77319ad6e",
                "sha256:300437af17396a945a58dcfffd77863303a8b6d9e65c6e81f1d2eed55b50d444",
                "sha256:391ac4d6002a80e15f35adc4ad6056f4fe1c17ceb0d1f98ba01b0f4f917adfd7",
                "sha256:3c5dc11d72519e55f727320e3cee535feedfaee09c0f0765ed1ca7badff1ab3c",
                "sha256:3d306fc4d88a6bcf61ce9d572c738b918578121bfd72891625fab314549024b5",
                "sha256:4574eef1f3bb81501fb02f911298af3c02fe8179c31a33b361dd49180c3e644d",
                "sha256:4e5f97bcbabdd79cbaa969b63439b89801ea560f11d42b0a387634275c633623",
                "sha256:6081bd7c2f4fcf9b383dcdb3b3385d75a26a7c9d2be25b6950c3d8ea652d2d2d",
                "sha256:76f7e67cec1f1d097d1f4ed7de41be3d74546e1a4ede0c7d56e775c4dce5dfb0",
                "sha256:7c66fa0aa4236b27b3c61cb488662d85dae746a6d1c7b0d91cf7aae118445adf",
                "sha256:858096c0d15e33f15ac157f455d8f86f2f2cdd223963e58c0f682a3af8362d89",
                "sha256:872747a3b64e2909aee59c803ccd0bceb9b75bf27915520ebd32d69687040fa2",
                "sha256:afa2b630797f9ed2f27f3d9f55e3f72b4244911e45a8c82756f44babbf0b243e",
                "sha256:c2712b778bacf1db434e3e065adfed3db300754186a29aecac1efae9ef4bcaff",
                "sha256:c27985e949b9b1a1fb4c20c71d315c10ea0f93fdf3ccdd4a8c158b5926edd8c8",
                "sha256:cc86c2ef598c15d824a243c2541c29459881c67fc3c0adb6efe2242f8f0ec3af",
                "sha256:e311dfcb470696e3c077249615893cada598e62fa7c4e4ca090167bd2b7d331f"
            ],
            "index": "pypi",
            "version": "==1.0.4"
        },
        "txaio": {
            "hashes": [
                "sha256:aaea42f8aad50e0ecfb976130ada140797e9dcb85fad2cf72b0f37f8cefcb490",
                "sha256:f9a9216e976e5e3246dfd112ad7ad55ca915606b60b84a757ac769bd404ff704"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==23.1.1"
        },
        "typing-extensions": {
            "hashes": [
                "sha256:83f085bd5ca59c80295fc2a82ab5dac679cbe02b9f33f7d83af68e241bea51b0",
                "sha256:c1f94d72897edaf4ce775bb7558d5b79d8126906a14ea5ed1635921406c0387a"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==4.11.0"
        },
        "tzdata": {
            "hashes": [
                "sha256:2674120f8d891909751c38abcdfd386ac0a5a1127954fbc332af6b5ceae07efd",
                "sha256:9068bc196136463f5245e51efda838afa15aaeca9903f49050dfa2679db4d252"
            ],
            "index": "pypi",
            "markers": "python_version >= '2'",
            "version": "==2024.1"
        },
        "tzlocal": {
            "hashes": [
                "sha256:49816ef2fe65ea8ac19d19aa7a1ae0551c834303d5014c6d5a62e4cbda8047b8",
                "sha256:8d399205578f1a9342816409cc1e46a93ebd5755e39ea2d85334bea911bf0e6e"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==5.2"
        },
        "uc-micro-py": {
            "hashes": [
                "sha256:d321b92cff673ec58027c04015fcaa8bb1e005478643ff4a500882eaab88c48a",
                "sha256:db1dffff340817673d7b466ec86114a9dc0e9d4d9b5ba229d9d60e5c12600cd5"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.7'",
            "version": "==1.0.3"
        },
        "urllib3": {
            "hashes": [
                "sha256:450b20ec296a467077128bff42b73080516e71b56ff59a60a02bef2232c4fa9d",
                "sha256:d0570876c61ab9e520d776c38acbbb5b05a776d3f9ff98a5c8fd5162a444cf19"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2.2.1"
        },
        "wcwidth": {
            "hashes": [
                "sha256:3da69048e4540d84af32131829ff948f1e022c1c6bdb8d6102117aac784f6859",
                "sha256:72ea0c06399eb286d978fdedb6923a9eb47e1c486ce63e9b4e64fc18303972b5"
            ],
            "index": "pypi",
            "version": "==0.2.13"
        },
        "webencodings": {
            "hashes": [
                "sha256:a0af1213f3c2226497a97e2b3aa01a7e4bee4f403f95be16fc9acd2947514a78",
                "sha256:b36a1c245f2d304965eb4e0a82848379241dc04b865afcc4aab16748587e1923"
            ],
            "index": "pypi",
            "version": "==0.5.1"
        },
        "websocket-client": {
            "hashes": [
                "sha256:17b44cc997f5c498e809b22cdf2d9c7a9e71c02c8cc2b6c56e7c2d1239bfa526",
                "sha256:3239df9f44da632f96012472805d40a23281a991027ce11d2f45a6f24ac4c3da"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.8.0"
        },
        "websockets": {
            "hashes": [
                "sha256:00fe5da3f037041da1ee0cf8e308374e236883f9842c7c465aa65098b1c9af59",
                "sha256:01bb2d4f0a6d04538d3c5dfd27c0643269656c28045a53439cbf1c004f90897a",
                "sha256:034feb9f4286476f273b9a245fb15f02c34d9586a5bc936aff108c3ba1b21beb",
                "sha256:04a97aca96ca2acedf0d1f332c861c5a4486fdcba7bcef35873820f940c4231e",
                "sha256:0d4290d559d68288da9f444089fd82490c8d2744309113fc26e2da6e48b65da6",
                "sha256:1288369a6a84e81b90da5dbed48610cd7e5d60af62df9851ed1d1d23a9069f10",
                "sha256:14839f54786987ccd9d03ed7f334baec0f02272e7ec4f6e9d427ff584aeea8b4",
                "sha256:1d045cbe1358d76b24d5e20e7b1878efe578d9897a25c24e6006eef788c0fdf0",
                "sha256:1f874ba705deea77bcf64a9da42c1f5fc2466d8f14daf410bc7d4ceae0a9fcb0",
                "sha256:205f672a6c2c671a86d33f6d47c9b35781a998728d2c7c2a3e1cf3333fcb62b7",
                "sha256:2177ee3901075167f01c5e335a6685e71b162a54a89a56001f1c3e9e3d2ad250",
                "sha256:219c8187b3ceeadbf2afcf0f25a4918d02da7b944d703b97d12fb01510869078",
                "sha256:25225cc79cfebc95ba1d24cd3ab86aaa35bcd315d12fa4358939bd55e9bd74a5",
                "sha256:3630b670d5057cd9e08b9c4dab6493670e8e762a24c2c94ef312783870736ab9",
                "sha256:368a05465f49c5949e27afd6fbe0a77ce53082185bbb2ac096a3a8afaf4de52e",
                "sha256:36ebd71db3b89e1f7b1a5deaa341a654852c3518ea7a8ddfdf69cc66acc2db1b",
                "sha256:39450e6215f7d9f6f7bc2a6da21d79374729f5d052333da4d5825af8a97e6735",
                "sha256:398b10c77d471c0aab20a845e7a60076b6390bfdaac7a6d2edb0d2c59d75e8d8",
                "sha256:3c3deac3748ec73ef24fc7be0b68220d14d47d6647d2f85b2771cb35ea847aa1",
                "sha256:3f14a96a0034a27f9d47fd9788913924c89612225878f8078bb9d55f859272b0",
                "sha256:3fc753451d471cff90b8f467a1fc0ae64031cf2d81b7b34e1811b7e2691bc4bc",
                "sha256:414ffe86f4d6f434a8c3b7913655a1a5383b617f9bf38720e7c0799fac3ab1c6",
                "sha256:449d77d636f8d9c17952628cc7e3b8faf6e92a17ec581ec0c0256300717e1512",
                "sha256:4b6caec8576e760f2c7dd878ba817653144d5f369200b6ddf9771d64385b84d4",
                "sha256:4d4fc827a20abe6d544a119896f6b78ee13fe81cbfef416f3f2ddf09a03f0e2e",
                "sha256:5a42d3ecbb2db5080fc578314439b1d79eef71d323dc661aa616fb492436af5d",
                "sha256:5b918d288958dc3fa1c5a0b9aa3256cb2b2b84c54407f4813c45d52267600cd3",
                "sha256:5ef440054124728cc49b01c33469de06755e5a7a4e83ef61934ad95fc327fbb0",
                "sha256:660c308dabd2b380807ab64b62985eaccf923a78ebc572bd485375b9ca2b7dc7",
                "sha256:6a6c9bcf7cdc0fd41cc7b7944447982e8acfd9f0d560ea6d6845428ed0562058",
                "sha256:6d24fc337fc055c9e83414c94e1ee0dee902a486d19d2a7f0929e49d7d604b09",
                "sha256:7048eb4415d46368ef29d32133134c513f507fff7d953c18c91104738a68c3b3",
                "sha256:77569d19a13015e840b81550922056acabc25e3f52782625bc6843cfa034e1da",
                "sha256:8149a0f5a72ca36720981418eeffeb5c2729ea55fa179091c81a0910a114a5d2",
                "sha256:836bef7ae338a072e9d1863502026f01b14027250a4545672673057997d5c05a",
                "sha256:8621a07991add373c3c5c2cf89e1d277e49dc82ed72c75e3afc74bd0acc446f0",
                "sha256:87e31011b5c14a33b29f17eb48932e63e1dcd3fa31d72209848652310d3d1f0d",
                "sha256:88cf9163ef674b5be5736a584c999e98daf3aabac6e536e43286eb74c126b9c7",
                "sha256:8fda642151d5affdee8a430bd85496f2e2517be3a2b9d2484d633d5712b15c56",
                "sha256:90b5d9dfbb6d07a84ed3e696012610b6da074d97453bd01e0e30744b472c8179",
                "sha256:90f4c7a069c733d95c308380aae314f2cb45bd8a904fb03eb36d1a4983a4993f",
                "sha256:9481a6de29105d73cf4515f2bef8eb71e17ac184c19d0b9918a3701c6c9c4f23",
                "sha256:9607b9a442392e690a57909c362811184ea429585a71061cd5d3c2b98065c199",
                "sha256:9777564c0a72a1d457f0848977a1cbe15cfa75fa2f67ce267441e465717dcf1a",
                "sha256:a032855dc7db987dff813583d04f4950d14326665d7e714d584560b140ae6b8b",
                "sha256:a0adf84bc2e7c86e8a202537b4fd50e6f7f0e4a6b6bf64d7ccb96c4cd3330b29",
                "sha256:a35f704be14768cea9790d921c2c1cc4fc52700410b1c10948511039be824aac",
                "sha256:a3dfff83ca578cada2d19e665e9c8368e1598d4e787422a460ec70e531dbdd58",
                "sha256:a4c805c6034206143fbabd2d259ec5e757f8b29d0a2f0bf3d2fe5d1f60147a4a",
                "sha256:a655bde548ca98f55b43711b0ceefd2a88a71af6350b0c168aa77562104f3f45",
                "sha256:ad2ab2547761d79926effe63de21479dfaf29834c50f98c4bf5b5480b5838434",
                "sha256:b1f3628a0510bd58968c0f60447e7a692933589b791a6b572fcef374053ca280",
                "sha256:b7e7ea2f782408c32d86b87a0d2c1fd8871b0399dd762364c731d86c86069a78",
                "sha256:bc6ccf7d54c02ae47a48ddf9414c54d48af9c01076a2e1023e3b486b6e72c707",
                "sha256:bea45f19b7ca000380fbd4e02552be86343080120d074b87f25593ce1700ad58",
                "sha256:cc1fc87428c1d18b643479caa7b15db7d544652e5bf610513d4a3478dbe823d0",
                "sha256:cd7c11968bc3860d5c78577f0dbc535257ccec41750675d58d8dc66aa47fe52c",
                "sha256:ceada5be22fa5a5a4cdeec74e761c2ee7db287208f54c718f2df4b7e200b8d4a",
                "sha256:cf5201a04550136ef870aa60ad3d29d2a59e452a7f96b94193bee6d73b8ad9a9",
                "sha256:d9fd19ecc3a4d5ae82ddbfb30962cf6d874ff943e56e0c81f5169be2fda62979",
                "sha256:ddaa4a390af911da6f680be8be4ff5aaf31c4c834c1a9147bc21cbcbca2d4370",
                "sha256:df174ece723b228d3e8734a6f2a6febbd413ddec39b3dc592f5a4aa0aff28098",
                "sha256:e0744623852f1497d825a49a99bfbec9bea4f3f946df6eb9d8a2f0c37a2fec2e",
                "sha256:e5dc25a9dbd1a7f61eca4b7cb04e74ae4b963d658f9e4f9aad9cd00b688692c8",
                "sha256:e7591d6f440af7f73c4bd9404f3772bfee064e639d2b6cc8c94076e71b2471c1",
                "sha256:eb6d38971c800ff02e4a6afd791bbe3b923a9a57ca9aeab7314c21c84bf9ff05",
                "sha256:ed907449fe5e021933e46a3e65d651f641975a768d0649fee59f10c2985529ed",
                "sha256:f6cf0ad281c979306a6a34242b371e90e891bce504509fb6bb5246bbbf31e7b6",
                "sha256:f95ba34d71e2fa0c5d225bde3b3bdb152e957150100e75c86bc7f3964c450d89"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.9'",
            "version": "==14.1"
        },
        "werkzeug": {
            "hashes": [
                "sha256:3aac3f5da756f93030740bc235d3e09449efcf65f2f55e3602e1d851b8f48795",
                "sha256:e39b645a6ac92822588e7b39a692e7828724ceae0b0d702ef96701f90e70128d"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.0.2"
        },
        "wheel": {
            "hashes": [
                "sha256:661e1abd9198507b1409a20c02106d9670b2576e916d58f520316666abca6729",
                "sha256:708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248"
            ],
            "markers": "python_version >= '3.8'",
            "version": "==0.45.1"
        },
        "whitenoise": {
            "hashes": [
                "sha256:8998f7370973447fac1e8ef6e8ded2c5209a7b1f67c1012866dbcd09681c3251",
                "sha256:b1f9db9bf67dc183484d760b99f4080185633136a273a03f6436034a41064146"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==6.6.0"
        },
        "wrapt": {
            "hashes": [
                "sha256:0229b247b0fc7dee0d36176cbb79dbaf2a9eb7ecc50ec3121f40ef443155fb1d",
                "sha256:0698d3a86f68abc894d537887b9bbf84d29bcfbc759e23f4644be27acf6da301",
                "sha256:0a0a1a1ec28b641f2a3a2c35cbe86c00051c04fffcfcc577ffcdd707df3f8635",
                "sha256:0b48554952f0f387984da81ccfa73b62e52817a4386d070c75e4db7d43a28c4a",
                "sha256:0f2a28eb35cf99d5f5bd12f5dd44a0f41d206db226535b37b0c60e9da162c3ed",
                "sha256:140ea00c87fafc42739bd74a94a5a9003f8e72c27c47cd4f61d8e05e6dec8721",
                "sha256:16187aa2317c731170a88ef35e8937ae0f533c402872c1ee5e6d079fcf320801",
                "sha256:17fcf043d0b4724858f25b8826c36e08f9fb2e475410bece0ec44a22d533da9b",
                "sha256:18b956061b8db634120b58f668592a772e87e2e78bc1f6a906cfcaa0cc7991c1",
                "sha256:2399408ac33ffd5b200480ee858baa58d77dd30e0dd0cab6a8a9547135f30a88",
                "sha256:2a0c23b8319848426f305f9cb0c98a6e32ee68a36264f45948ccf8e7d2b941f8",
                "sha256:2dfb7cff84e72e7bf975b06b4989477873dcf160b2fd89959c629535df53d4e0",
                "sha256:2f495b6754358979379f84534f8dd7a43ff8cff2558dcdea4a148a6e713a758f",
                "sha256:33539c6f5b96cf0b1105a0ff4cf5db9332e773bb521cc804a90e58dc49b10578",
                "sha256:3c34f6896a01b84bab196f7119770fd8466c8ae3dfa73c59c0bb281e7b588ce7",
                "sha256:498fec8da10e3e62edd1e7368f4b24aa362ac0ad931e678332d1b209aec93045",
                "sha256:4d63f4d446e10ad19ed01188d6c1e1bb134cde8c18b0aa2acfd973d41fcc5ada",
                "sha256:4e4b4385363de9052dac1a67bfb535c376f3d19c238b5f36bddc95efae15e12d",
                "sha256:4e547b447073fc0dbfcbff15154c1be8823d10dab4ad401bdb1575e3fdedff1b",
                "sha256:4f643df3d4419ea3f856c5c3f40fec1d65ea2e89ec812c83f7767c8730f9827a",
                "sha256:4f763a29ee6a20c529496a20a7bcb16a73de27f5da6a843249c7047daf135977",
                "sha256:5ae271862b2142f4bc687bdbfcc942e2473a89999a54231aa1c2c676e28f29ea",
                "sha256:5d8fd17635b262448ab8f99230fe4dac991af1dabdbb92f7a70a6afac8a7e346",
                "sha256:69c40d4655e078ede067a7095544bcec5a963566e17503e75a3a3e0fe2803b13",
                "sha256:69d093792dc34a9c4c8a70e4973a3361c7a7578e9cd86961b2bbf38ca71e4e22",
                "sha256:6a9653131bda68a1f029c52157fd81e11f07d485df55410401f745007bd6d339",
                "sha256:6ff02a91c4fc9b6a94e1c9c20f62ea06a7e375f42fe57587f004d1078ac86ca9",
                "sha256:714c12485aa52efbc0fc0ade1e9ab3a70343db82627f90f2ecbc898fdf0bb181",
                "sha256:7264cbb4a18dc4acfd73b63e4bcfec9c9802614572025bdd44d0721983fc1d9c",
                "sha256:73a96fd11d2b2e77d623a7f26e004cc31f131a365add1ce1ce9a19e55a1eef90",
                "sha256:74bf625b1b4caaa7bad51d9003f8b07a468a704e0644a700e936c357c17dd45a",
                "sha256:81b1289e99cf4bad07c23393ab447e5e96db0ab50974a280f7954b071d41b489",
                "sha256:8425cfce27b8b20c9b89d77fb50e368d8306a90bf2b6eef2cdf5cd5083adf83f",
                "sha256:875d240fdbdbe9e11f9831901fb8719da0bd4e6131f83aa9f69b96d18fae7504",
                "sha256:879591c2b5ab0a7184258274c42a126b74a2c3d5a329df16d69f9cee07bba6ea",
                "sha256:89fc28495896097622c3fc238915c79365dd0ede02f9a82ce436b13bd0ab7569",
                "sha256:8a5e7cc39a45fc430af1aefc4d77ee6bad72c5bcdb1322cfde852c15192b8bd4",
                "sha256:8f8909cdb9f1b237786c09a810e24ee5e15ef17019f7cecb207ce205b9b5fcce",
                "sha256:914f66f3b6fc7b915d46c1cc424bc2441841083de01b90f9e81109c9759e43ab",
                "sha256:92a3d214d5e53cb1db8b015f30d544bc9d3f7179a05feb8f16df713cecc2620a",
                "sha256:948a9bd0fb2c5120457b07e59c8d7210cbc8703243225dbd78f4dfc13c8d2d1f",
                "sha256:9c900108df470060174108012de06d45f514aa4ec21a191e7ab42988ff42a86c",
                "sha256:9f2939cd4a2a52ca32bc0b359015718472d7f6de870760342e7ba295be9ebaf9",
                "sha256:a4192b45dff127c7d69b3bdfb4d3e47b64179a0b9900b6351859f3001397dabf",
                "sha256:a8fc931382e56627ec4acb01e09ce66e5c03c384ca52606111cee50d931a342d",
                "sha256:ad47b095f0bdc5585bced35bd088cbfe4177236c7df9984b3cc46b391cc60627",
                "sha256:b1ca5f060e205f72bec57faae5bd817a1560fcfc4af03f414b08fa29106b7e2d",
                "sha256:ba1739fb38441a27a676f4de4123d3e858e494fac05868b7a281c0a383c098f4",
                "sha256:baa7ef4e0886a6f482e00d1d5bcd37c201b383f1d314643dfb0367169f94f04c",
                "sha256:bb90765dd91aed05b53cd7a87bd7f5c188fcd95960914bae0d32c5e7f899719d",
                "sha256:bc7f729a72b16ee21795a943f85c6244971724819819a41ddbaeb691b2dd85ad",
                "sha256:bdf62d25234290db1837875d4dceb2151e4ea7f9fff2ed41c0fde23ed542eb5b",
                "sha256:c30970bdee1cad6a8da2044febd824ef6dc4cc0b19e39af3085c763fdec7de33",
                "sha256:d2c63b93548eda58abf5188e505ffed0229bf675f7c3090f8e36ad55b8cbc371",
                "sha256:d751300b94e35b6016d4b1e7d0e7bbc3b5e1751e2405ef908316c2a9024008a1",
                "sha256:da427d311782324a376cacb47c1a4adc43f99fd9d996ffc1b3e8529c4074d393",
                "sha256:daba396199399ccabafbfc509037ac635a6bc18510ad1add8fd16d4739cdd106",
                "sha256:e185ec6060e301a7e5f8461c86fb3640a7beb1a0f0208ffde7a65ec4074931df",
                "sha256:e4a557d97f12813dc5e18dad9fa765ae44ddd56a672bb5de4825527c847d6379",
                "sha256:e5ed16d95fd142e9c72b6c10b06514ad30e846a0d0917ab406186541fe68b451",
                "sha256:e711fc1acc7468463bc084d1b68561e40d1eaa135d8c509a65dd534403d83d7b",
                "sha256:f28b29dc158ca5d6ac396c8e0a2ef45c4e97bb7e65522bfc04c989e6fe814575",
                "sha256:f335579a1b485c834849e9075191c9898e0731af45705c2ebf70e0cd5d58beed",
                "sha256:fce6fee67c318fdfb7f285c29a82d84782ae2579c0e1b385b7f36c6e8074fffb",
                "sha256:fd136bb85f4568fffca995bd3c8d52080b1e5b225dbf1c2b17b66b4c5fa02838"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==1.17.0"
        },
        "xarray": {
            "hashes": [
                "sha256:1ccace44573ddb862e210ad3ec204210654d2c750bec11bbe7d842dfc298591f",
                "sha256:6ee94f63ddcbdd0cf3909d1177f78cdac756640279c0e32ae36819a89cdaba37"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.10'",
            "version": "==2024.11.0"
        },
        "xyzservices": {
            "hashes": [
                "sha256:68fb8353c9dbba4f1ff6c0f2e5e4e596bb9e1db7f94f4f7dfbcb26e25aa66fde",
                "sha256:776ae82b78d6e5ca63dd6a94abb054df8130887a4a308473b54a6bd364de8644"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==2024.9.0"
        },
        "zipp": {
            "hashes": [
                "sha256:206f5a15f2af3dbaee80769fb7dc6f249695e940acca08dfb2a4769fe61e538b",
                "sha256:2884ed22e7d8961de1c9a05142eb69a247f120291bc0206a00a7642f09b5b715"
            ],
            "index": "pypi",
            "markers": "python_version >= '3.8'",
            "version": "==3.18.1"
        },
        "zope.interface": {
            "hashes": [
                "sha256:014bb94fe6bf1786da1aa044eadf65bc6437bcb81c451592987e5be91e70a91e",
                "sha256:01a0b3dd012f584afcf03ed814bce0fc40ed10e47396578621509ac031be98bf",
                "sha256:10cde8dc6b2fd6a1d0b5ca4be820063e46ddba417ab82bcf55afe2227337b130",
                "sha256:187f7900b63845dcdef1be320a523dbbdba94d89cae570edc2781eb55f8c2f86",
                "sha256:1b0c4c90e5eefca2c3e045d9f9ed9f1e2cdbe70eb906bff6b247e17119ad89a1",
                "sha256:22e8a218e8e2d87d4d9342aa973b7915297a08efbebea5b25900c73e78ed468e",
                "sha256:26c9a37fb395a703e39b11b00b9e921c48f82b6e32cc5851ad5d0618cd8876b5",
                "sha256:2bb78c12c1ad3a20c0d981a043d133299117b6854f2e14893b156979ed4e1d2c",
                "sha256:2c3cfb272bcb83650e6695d49ae0d14dd06dc694789a3d929f23758557a23d92",
                "sha256:2f32010ffb87759c6a3ad1c65ed4d2e38e51f6b430a1ca11cee901ec2b42e021",
                "sha256:3c8731596198198746f7ce2a4487a0edcbc9ea5e5918f0ab23c4859bce56055c",
                "sha256:40aa8c8e964d47d713b226c5baf5f13cdf3a3169c7a2653163b17ff2e2334d10",
                "sha256:4137025731e824eee8d263b20682b28a0bdc0508de9c11d6c6be54163e5b7c83",
                "sha256:46034be614d1f75f06e7dcfefba21d609b16b38c21fc912b01a99cb29e58febb",
                "sha256:483e118b1e075f1819b3c6ace082b9d7d3a6a5eb14b2b375f1b80a0868117920",
                "sha256:4d6b229f5e1a6375f206455cc0a63a8e502ed190fe7eb15e94a312dc69d40299",
                "sha256:567d54c06306f9c5b6826190628d66753b9f2b0422f4c02d7c6d2b97ebf0a24e",
                "sha256:5683aa8f2639016fd2b421df44301f10820e28a9b96382a6e438e5c6427253af",
                "sha256:600101f43a7582d5b9504a7c629a1185a849ce65e60fca0f6968dfc4b76b6d39",
                "sha256:62e32f02b3f26204d9c02c3539c802afc3eefb19d601a0987836ed126efb1f21",
                "sha256:69dedb790530c7ca5345899a1b4cb837cc53ba669051ea51e8c18f82f9389061",
                "sha256:72d5efecad16c619a97744a4f0b67ce1bcc88115aa82fcf1dc5be9bb403bcc0b",
                "sha256:8d407e0fd8015f6d5dfad481309638e1968d70e6644e0753f229154667dd6cd5",
                "sha256:a058e6cf8d68a5a19cb5449f42a404f0d6c2778b897e6ce8fadda9cea308b1b0",
                "sha256:a1adc14a2a9d5e95f76df625a9b39f4709267a483962a572e3f3001ef90ea6e6",
                "sha256:a56fe1261230093bfeedc1c1a6cd6f3ec568f9b07f031c9a09f46b201f793a85",
                "sha256:ad4524289d8dbd6fb5aa17aedb18f5643e7d48358f42c007a5ee51a2afc2a7c5",
                "sha256:afa0491a9f154cf8519a02026dc85a416192f4cb1efbbf32db4a173ba28b289a",
                "sha256:bf34840e102d1d0b2d39b1465918d90b312b1119552cebb61a242c42079817b9",
                "sha256:c40df4aea777be321b7e68facb901bc67317e94b65d9ab20fb96e0eb3c0b60a1",
                "sha256:d0e7321557c702bd92dac3c66a2f22b963155fdb4600133b6b29597f62b71b12",
                "sha256:d165d7774d558ea971cb867739fb334faf68fc4756a784e689e11efa3becd59e",
                "sha256:e78a183a3c2f555c2ad6aaa1ab572d1c435ba42f1dc3a7e8c82982306a19b785",
                "sha256:e8fa0fb05083a1a4216b4b881fdefa71c5d9a106e9b094cd4399af6b52873e91",
                "sha256:f83d6b4b22262d9a826c3bd4b2fbfafe1d0000f085ef8e44cd1328eea274ae6a",
                "sha256:f95bebd0afe86b2adc074df29edb6848fc4d474ff24075e2c263d698774e108d"
            ],
            "markers": "python_version >= '3.7'",
            "version": "==6.3"
        }
    },
    "develop": {}
}

```

---

## File: `README.md`

```markdown
# Custom_Labeling-Tool

## Description
This ongoing project is a custom labeling tool based on Django-Plotly-Dash, specifically designed for labeling ECG waveforms. It allows users to annotate ECG waveforms easily through a web-based interface.

## Installation

### Prerequisites
Before running the WebApp, you need to set up your environment:

1. **Redis Installation (Windows)**
      
      To install Redis on Windows, you can follow these steps:
      
      **Option 1: Install via MSI Executable in this repository**
      
      - Locate the Redis executable `Redis-x64-5.0.14.1.msi` from this repository.
      - Run the executable and follow the installation prompts.
      - During the installation process, check `Add the Redis installation folder to the PATH environment variable.`
      - Keep the rest as default and follow the remaining installation prompts.
      
      **Option 2: Download the Latest Release**
      
      - Visit the [Redis Releases](https://github.com/tporadowski/redis/releases) page.
      - Download the latest release or the same version.
      - Run the installer and follow the installation instructions.
      - During the installation process, check `Add the Redis installation folder to the PATH environment variable.`
      - Keep the rest as default and follow the remaining installation prompts.
      
      Once installed, ensure Redis is running properly by executing the following command in your terminal or command prompt:
      
      ```bash
      redis-server
      ```
      
      Then check if you get `PONG` when you run these following commands in your terminal or command prompt:
   
      ```bash
      redis-cli
      ping
      ```

2. **Virtual Environment:**
   - Create a new virtual environment in the `Label_V04` project folder.
   - Activate the virtual environment. If you're using pipenv, the commands are:
     ```bash
     cd Label-V02  # Navigate into the project folder
     pipenv shell  # Activate the virtual environment
     ```

3. **Dependencies:**
   - Install the required packages from `requirements.txt` using pipenv:
     ```bash
     pipenv install -r requirements.txt
     ```

4. **Database Setup:**
   You have two options for setting up the database: using PostgreSQL or the default SQLite.

   **Option 1: PostgreSQL**
   - Ensure the default database configuration in `settings.py` is commented out.
   - Create a PostgreSQL database named `db_label_v04`.
   - Update the database configuration in `settings.py` (look for the following in the file):

     ```python
     DATABASES = {
         'default': {
             'ENGINE': 'django.db.backends.postgresql',
             'NAME': 'db_label_v04',
             'USER': 'postgres',
             'PASSWORD': '12345',
             'HOST': 'localhost',  # It is marked as 'Server' in SQL Shell
         }

     ```

   - Run migrations to set up the database schema:
     ```bash
     python manage.py makemigrations
     python manage.py migrate
     ```
     
   - Collect static files:
     ```bash
     python manage.py collectstatic
     ```

   **Option 2: Default SQLite**
   - Ensure the PostgreSQL database configuration in `settings.py` is commented out.
   - No additional setup is required. Ensure the default database configuration in `settings.py` is uncommented (look for the following in the file):
     ```python
     DATABASES = {
         'default': {
             'ENGINE': 'django.db.backends.sqlite3',
             'NAME': BASE_DIR / 'db.sqlite3',
         }
     }
     ```

   - Run migrations to set up the database schema:
     ```bash
     python manage.py makemigrations
     python manage.py migrate
     ```
     
   - Collect static files:
     ```bash
     python manage.py collectstatic
     ```

## Running the Application

To run the application, execute the following command:

```bash
python manage.py runserver
 ```

You will see the following line in the terminal, indicating the server is running:

```bash
Starting ASGI/Daphne version 4.1.2 development server at http://127.0.0.1:8000/
 ```


Open your web browser and navigate to [http://127.0.0.1:8000/](http://127.0.0.1:8000/) to access the WebApp.

## Usage

### Select Your Directory:
- Click on the "Select your directory!" button.
- Choose the `Testing_Folder_Filtered` directory provided in the repository.

### Select a Lead:
- Use the dropdown menu right of "Choose a Lead:" to select any ECG lead.

### Viewing Waveforms:
- The waveform corresponding to the selected lead will be displayed.

### Adding Annotations:
- Click on the waveform where you want to start the annotation, and click again where it ends.
- An input field will appear. Type in your annotation description.
- Submit the annotation by clicking 'Submit' or pressing 'Enter'.
- Your annotation will be displayed below the waveform.

## Contributing
Feel free to fork this project and contribute by submitting a pull request. I appreciate your input!

## License
This project is licensed under the MIT License - see the LICENSE.md file for details.

```

---

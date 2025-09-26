from django.conf import settings  # Import Django settings
import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'label_V04.settings')

base_path = os.path.normpath(Path(settings.BASE_FILE_PATH))
base_path_norm = os.path.normpath(base_path)
print(f"base_path : {base_path}")
print(f"base_path_norm : {base_path_norm}")

base_path = os.path.join(settings.BASE_FILE_PATH)
base_path_norm = os.path.normpath(base_path)


base_path = os.path.join(settings.BASE_FILE_PATH)
base_path_norm = os.path.normpath(base_path)

print(f"base_path : {base_path}")
print(f"base_path_norm : {base_path_norm}")

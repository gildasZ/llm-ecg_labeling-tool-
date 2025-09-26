from django.conf import settings  # Import Django settings
import os

base_path = settings.BASE_DIR
base_path_norm = os.path.normpath(base_path)

print(f"base_path : {base_path}")
print(f"base_path_norm : {base_path_norm}")

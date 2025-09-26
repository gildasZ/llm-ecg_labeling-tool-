
# home/urls.py
from django.urls import path
# from django.contrib.auth import views as auth_views
from .views import (
    home, register, custom_logout, custom_login, welcome,
    upload_model_view, upload_directory_view,
    download_selected_files_view
)
from home.dash_apps.finished_apps import display_ecg_graph

app_name = 'home'

urlpatterns = [
    path('', home, name='home'),
    path('login/', custom_login, name='login'),    # Handles the behavior on clicking the logout button.
    path('logout/', custom_logout, name='logout'), # Handles the behavior on clicking the logout button.    
    path('register/', register, name='register'),
    path('welcome/', welcome, name='welcome'), 
    path('upload-model/', upload_model_view, name='upload_model'), # URL pattern for the pretrained model weights file upload view
    path('upload-directory/', upload_directory_view, name='upload_directory'), # URL for raw files directory upload
    path('download-selected/', download_selected_files_view, name='download_selected_files'), # URL Pattern for Downloading Selected Files
]

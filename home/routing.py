
# home/routing.py
from django.urls import path
from .consumers import ECGConsumer  # Make sure this references the correct consumer

websocket_urlpatterns = [
    path("ws/process-xml/", ECGConsumer.as_asgi()),
]

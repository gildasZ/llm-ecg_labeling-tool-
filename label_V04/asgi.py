"""
ASGI config for label_V04 project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os
import logging
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path, re_path
from home.consumers import ECGConsumer
from django_plotly_dash.consumers import MessageConsumer
from django_plotly_dash.util import pipe_ws_endpoint_name
from home.routing import websocket_urlpatterns # For if you later have many patterns the move them in .routing.py

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'label_V04.settings')
# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Get logger for the current file
logger = logging.getLogger('home')

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                # websocket_urlpatterns  # Use the separate routing file if there are many URLrouters
                [
                    path("ws/process-xml/", ECGConsumer.as_asgi()),
                    re_path(pipe_ws_endpoint_name(), MessageConsumer.as_asgi()),  # Routing for Django Plotly Dash
                ] 
            )
        )
    ),
})

# Log using the configured settings in Django's settings.py
logger.info(f"\nASGI configuration for DJANGO_SETTINGS_MODULE: {os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'label_V04.settings')}\n")

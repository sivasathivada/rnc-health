"""
ASGI config for rnchealth project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""
import os
import django
from django.core.asgi import get_asgi_application

# 1. Set environment variables
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rnchealth.settings')

# 2. Force Django to load everything safely
django.setup()

# 3. Initialize and capture the HTTP ASGI application variable once
django_asgi_app = get_asgi_application()

# 4. Import Channels routing components ONLY after setup is complete
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from consultations.routing import websocket_urlpatterns

# 5. Define the core Application Router
application = ProtocolTypeRouter(
    {
        #  CORRECT: Use the pre-loaded variable instead of re-running the function!
        "http": django_asgi_app,
        
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    }
)
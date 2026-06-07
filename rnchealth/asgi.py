"""
ASGI config for rnchealth project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rnchealth.settings')

# 2. FORCE Django to load all apps, models, and registries right now!
django.setup()

# 3. Initialize the standard HTTP ASGI application
django_asgi_app = get_asgi_application()


# 2. FORCE Django to load all apps, models, and registries right now!
django.setup()

# 3. Initialize the standard HTTP ASGI application
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from consultations.routing import websocket_urlpatterns


application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns),)
    }

)

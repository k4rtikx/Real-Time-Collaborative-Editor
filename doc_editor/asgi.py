"""
ASGI configuration for CollabEdit.

Wraps WebSocket connections with:
  1. AllowedHostsOriginValidator — rejects cross-origin WebSocket connections.
  2. AuthMiddlewareStack — resolves Django session to scope["user"].
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "doc_editor.settings.development")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from apps.collaboration.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)
            )
        ),
    }
)
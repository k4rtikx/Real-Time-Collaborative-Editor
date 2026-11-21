"""WebSocket URL patterns for the collaboration app."""
from django.urls import path

from .consumers import DocumentConsumer

websocket_urlpatterns = [
    path("ws/documents/<str:doc_uuid>/", DocumentConsumer.as_asgi()),
]

from django.urls import path
from .consumers import DocumentConsumer

websocket_urlpatterns = [
    path("ws/editor/", DocumentConsumer.as_asgi()),
]
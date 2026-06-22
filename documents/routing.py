from django.urls import path
from .consumers import DocumentConsumer

websocket_urlpatterns = [
    path("ws/editor/<str:room_id>/", DocumentConsumer.as_asgi()),
]
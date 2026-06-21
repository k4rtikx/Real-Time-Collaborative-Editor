from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("<str:room_id>/", views.room, name="room"),
]
from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("home",views.home,name="homepage"),
    path("<str:room_id>/", views.room, name="room"),
]
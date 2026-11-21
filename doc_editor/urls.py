"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path

from core.health_checks import health_check
from documents.views import home, index, room  # backward-compat legacy views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Health check (no auth required)
    path("health/", health_check, name="health_check"),
    # New application URLs
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("documents/", include("apps.documents.urls", namespace="documents")),
    # Legacy URLs — preserved for backward compatibility
    path("", home, name="home"),
    path("home", index, name="homepage"),
    path("<str:room_id>/", room, name="room"),
]

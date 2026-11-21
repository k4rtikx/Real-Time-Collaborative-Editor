"""Document URL configuration."""
from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("create/", views.document_create, name="create"),
    path("<str:doc_uuid>/", views.document_detail, name="editor"),
    path("<str:doc_uuid>/delete/", views.document_delete, name="delete"),
    path("<str:doc_uuid>/title/", views.title_update, name="update_title"),
    path("<str:doc_uuid>/share/", views.permission_create, name="share"),
    path("<str:doc_uuid>/share/<str:username>/revoke/", views.permission_delete, name="revoke"),
    path("<str:doc_uuid>/revisions/", views.revision_list, name="revisions"),
    path("<str:doc_uuid>/revisions/create/", views.revision_create, name="create_revision"),
    path(
        "<str:doc_uuid>/revisions/<int:revision_number>/restore/",
        views.revision_restore,
        name="restore_revision",
    ),
]

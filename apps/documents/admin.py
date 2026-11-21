"""Document admin registration."""
from django.contrib import admin

from .models import Document, DocumentPermission, DocumentRevision


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "owner", "uuid", "is_deleted", "created_at", "updated_at"]
    list_filter = ["is_deleted", "created_at"]
    search_fields = ["title", "owner__username", "group__name"]
    raw_id_fields = ["owner", "group"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]

    def uuid(self, obj):
        return obj.group.name
    uuid.short_description = "UUID"


@admin.register(DocumentPermission)
class DocumentPermissionAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "user", "role", "granted_by", "granted_at"]
    list_filter = ["role"]
    search_fields = ["document__title", "user__username"]
    raw_id_fields = ["document", "user", "granted_by"]


@admin.register(DocumentRevision)
class DocumentRevisionAdmin(admin.ModelAdmin):
    list_display = ["id", "document", "revision_number", "trigger", "created_by", "created_at"]
    list_filter = ["trigger"]
    search_fields = ["document__title"]
    raw_id_fields = ["document", "created_by"]
    readonly_fields = ["created_at"]

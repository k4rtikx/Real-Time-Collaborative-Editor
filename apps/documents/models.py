"""
Document and permission models.

Migration history:
  0001_initial (documents app) — Group table
  0002_document (documents app) — Document table (legacy; preserved)
  0003_document_v2 — adds title, owner, yjs_state, soft-delete, created_at to Document
  0004_permissions_revisions — DocumentPermission, DocumentRevision
"""
import uuid

from django.conf import settings
from django.db import models


class Group(models.Model):
    """
    Legacy room-identifier model — preserved for FK continuity.
    Group.name == document UUID (str).
    """
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = "documents_group"

    def __str__(self) -> str:
        return self.name


class Document(models.Model):
    """
    Collaborative document.

    The `group` FK to the legacy Group model is preserved for migration continuity.
    New fields are added via migration 0003.

    PostgreSQL is the authoritative store for yjs_state.
    Redis holds a TTL-bounded cache for fast WebSocket connection load.
    """

    # Legacy field — preserved; group.name == document UUID
    group = models.ForeignKey(
        "documents.Group",
        on_delete=models.CASCADE,
        related_name="new_documents",
    )

    # Legacy field — preserved for existing data; no longer written by new code
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # New fields (migration 0003)
    title = models.CharField(max_length=255, default="Untitled document")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_documents",
        null=True,  # nullable for data migration backfill
    )
    yjs_state = models.BinaryField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        db_table = "documents_document"
        indexes = [
            models.Index(fields=["owner"], name="doc_owner_idx"),
            models.Index(fields=["is_deleted", "-updated_at"], name="doc_active_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def uuid(self) -> str:
        """Return the document UUID (stored as the Group name)."""
        return self.group.name


class DocumentPermission(models.Model):
    """
    Per-user, per-document permission grant.

    Owners are NOT stored here — ownership is on Document.owner.
    One permission entry per (document, user) pair.
    """

    ROLE_EDITOR = "editor"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_EDITOR, "Editor"),
        (ROLE_VIEWER, "Viewer"),
    ]

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_permissions",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="granted_permissions",
    )

    class Meta:
        db_table = "documents_documentpermission"
        unique_together = [("document", "user")]
        indexes = [
            models.Index(fields=["user", "document"], name="perm_user_doc_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.role} on {self.document}"


class DocumentRevision(models.Model):
    """
    Immutable point-in-time snapshot of a document's Yjs state.
    """

    TRIGGER_MANUAL = "manual"
    TRIGGER_AUTO = "auto"
    TRIGGER_RESTORE = "restore"
    TRIGGER_CHOICES = [
        (TRIGGER_MANUAL, "Manual"),
        (TRIGGER_AUTO, "Automatic"),
        (TRIGGER_RESTORE, "Pre-restore snapshot"),
    ]

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    revision_number = models.PositiveIntegerField()
    yjs_state = models.BinaryField()
    content_html = models.TextField(blank=True)
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_revisions",
    )

    class Meta:
        db_table = "documents_documentrevision"
        unique_together = [("document", "revision_number")]
        indexes = [
            models.Index(fields=["document", "-revision_number"], name="rev_doc_num_idx"),
            models.Index(fields=["document", "-created_at"], name="rev_doc_time_idx"),
        ]
        ordering = ["-revision_number"]

    def __str__(self) -> str:
        return f"Revision #{self.revision_number} of {self.document}"

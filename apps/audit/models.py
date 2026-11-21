"""Audit event model — append-only."""
from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """
    Immutable audit log record.

    Records are never updated or deleted by application code.
    Purged via management command after the retention period (90 days).
    """

    event_type = models.CharField(max_length=50, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events_as_actor",
    )
    # Reference to documents_document — using integer FK to avoid circular import
    document_id = models.BigIntegerField(null=True, db_index=True)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events_as_target",
    )
    metadata = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_auditevent"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"], name="audit_actor_time_idx"),
            models.Index(fields=["event_type", "-created_at"], name="audit_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} by {self.actor} at {self.created_at}"

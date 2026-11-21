"""Audit event service — log security-relevant application events."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def log_event(
    event_type: str,
    actor=None,
    document=None,
    target_user=None,
    metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Record an audit event.

    This function is fire-and-forget — it logs a warning if the write fails
    but does not raise an exception to the caller. Audit failures must not
    interrupt the primary user action.

    Args:
        event_type: A dot-separated event identifier (e.g., 'document.created').
        actor: The User who performed the action.
        document: The Document related to the event (or None).
        target_user: The User affected by the action (e.g., in permission grant).
        metadata: Additional structured data as a dict.
        ip_address: The actor's IP address string, or None.
    """
    from apps.audit.models import AuditEvent

    try:
        AuditEvent.objects.create(
            event_type=event_type,
            actor=actor,
            document_id=document.id if document else None,
            target_user=target_user,
            metadata=metadata or {},
            ip_address=ip_address,
        )
    except Exception as e:
        logger.warning(
            "audit.log_event: failed to write audit record",
            extra={"event_type": event_type, "error": str(e)},
        )

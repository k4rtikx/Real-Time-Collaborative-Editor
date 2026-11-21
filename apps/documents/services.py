"""
Document service layer — business logic for document operations.

Services orchestrate database writes, enforce business rules,
and emit audit events. They must not contain presentation logic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from .models import Document, DocumentPermission, DocumentRevision

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)


def create_document(owner, title: str = "Untitled document") -> Document:
    """
    Create a new document owned by `owner`.

    Also creates the legacy Group entry (required by existing FK).
    Returns the created Document.
    """
    import uuid as _uuid
    from .models import Group

    with transaction.atomic():
        room_uuid = str(_uuid.uuid4())
        group = Group.objects.create(name=room_uuid)
        document = Document.objects.create(
            group=group,
            title=title,
            owner=owner,
        )

    log_event(
        event_type="document.created",
        actor=owner,
        document=document,
        metadata={"title": title},
    )
    logger.info("Document created", extra={"doc_id": document.id, "owner_id": owner.id})
    return document


def share_document(owner, document: Document, target_user, role: str, request=None) -> DocumentPermission:
    """
    Grant `target_user` the specified `role` on `document`.

    Args:
        owner: The document owner performing the action.
        document: The document to share.
        target_user: The user to grant access to.
        role: 'editor' or 'viewer'.
        request: Optional HTTP request (for IP logging in audit).

    Returns:
        The created or updated DocumentPermission.

    Raises:
        PermissionError: If `owner` is not the document owner.
        ValueError: If attempting to share with the owner themselves.
    """
    from .permissions import has_owner_permission

    if not has_owner_permission(owner, document):
        raise PermissionError("Only the document owner can share it.")
    if target_user.id == owner.id:
        raise ValueError("Cannot share a document with its own owner.")
    if role not in (DocumentPermission.ROLE_EDITOR, DocumentPermission.ROLE_VIEWER):
        raise ValueError(f"Invalid role: '{role}'. Must be 'editor' or 'viewer'.")

    perm, created = DocumentPermission.objects.update_or_create(
        document=document,
        user=target_user,
        defaults={"role": role, "granted_by": owner},
    )

    action = "permission.granted" if created else "permission.updated"
    log_event(
        event_type=action,
        actor=owner,
        document=document,
        target_user=target_user,
        metadata={"role": role},
        ip_address=_get_ip(request),
    )
    logger.info(action, extra={"doc_id": document.id, "target_user_id": target_user.id, "role": role})
    return perm


def revoke_permission(owner, document: Document, target_user, request=None) -> None:
    """
    Revoke `target_user`'s access to `document`.

    Raises:
        PermissionError: If `owner` is not the document owner.
        ValueError: If attempting to revoke the owner's own access.
    """
    from .permissions import has_owner_permission

    if not has_owner_permission(owner, document):
        raise PermissionError("Only the document owner can revoke permissions.")
    if target_user.id == owner.id:
        raise ValueError("Cannot revoke the owner's own access.")

    deleted_count, _ = DocumentPermission.objects.filter(
        document=document, user=target_user
    ).delete()

    if deleted_count > 0:
        log_event(
            event_type="permission.revoked",
            actor=owner,
            document=document,
            target_user=target_user,
            ip_address=_get_ip(request),
        )
        logger.info("permission.revoked", extra={"doc_id": document.id, "target_user_id": target_user.id})


def soft_delete_document(owner, document: Document, request=None) -> None:
    """
    Soft-delete a document (sets is_deleted=True, deleted_at=now).

    Raises:
        PermissionError: If `owner` is not the document owner.
    """
    from .permissions import has_owner_permission

    if not has_owner_permission(owner, document):
        raise PermissionError("Only the document owner can delete it.")

    document.is_deleted = True
    document.deleted_at = timezone.now()
    document.save(update_fields=["is_deleted", "deleted_at"])

    log_event(
        event_type="document.deleted",
        actor=owner,
        document=document,
        ip_address=_get_ip(request),
    )
    logger.info("Document soft-deleted", extra={"doc_id": document.id})


def create_revision(document: Document, created_by, trigger: str = "manual") -> DocumentRevision:
    """
    Create a point-in-time snapshot of the document.

    Uses select_for_update to prevent concurrent revision number conflicts.
    """
    with transaction.atomic():
        last_rev = (
            DocumentRevision.objects.filter(document=document)
            .select_for_update()
            .order_by("-revision_number")
            .first()
        )
        next_number = (last_rev.revision_number + 1) if last_rev else 1

        revision = DocumentRevision.objects.create(
            document=document,
            revision_number=next_number,
            yjs_state=document.yjs_state or b"",
            content_html=document.content or "",
            trigger=trigger,
            created_by=created_by,
        )

    logger.info(
        "Revision created",
        extra={"doc_id": document.id, "revision": next_number, "trigger": trigger},
    )
    return revision


def restore_revision(owner, document: Document, revision: DocumentRevision, request=None) -> Document:
    """
    Restore a document to a previous revision.

    1. Creates a pre-restore snapshot of the current state.
    2. Updates Document.yjs_state to the revision's state.
    3. Logs the event.

    Raises:
        PermissionError: If owner is not the document owner.
    """
    from .permissions import has_owner_permission

    if not has_owner_permission(owner, document):
        raise PermissionError("Only the document owner can restore revisions.")

    with transaction.atomic():
        # Snapshot current state before overwriting
        create_revision(document, created_by=owner, trigger="restore")

        # Apply restored state
        document.yjs_state = revision.yjs_state
        document.content = revision.content_html
        document.updated_at = timezone.now()
        document.save(update_fields=["yjs_state", "content", "updated_at"])

    log_event(
        event_type="document.restored",
        actor=owner,
        document=document,
        metadata={"restored_revision": revision.revision_number},
        ip_address=_get_ip(request),
    )
    logger.info(
        "Document restored",
        extra={"doc_id": document.id, "revision": revision.revision_number},
    )
    return document


def _get_ip(request) -> str | None:
    """Extract client IP from request, returning None if request is absent."""
    if request is None:
        return None
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

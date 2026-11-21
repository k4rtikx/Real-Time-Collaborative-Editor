"""
Document selectors — read-only database queries.

Selectors are pure functions that query the database and return
QuerySets or model instances. They contain no business logic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet

from .models import Document, DocumentPermission, DocumentRevision

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()

logger = logging.getLogger(__name__)


def get_document_by_uuid(doc_uuid: str) -> Document | None:
    """Return a non-deleted Document by its UUID (Group.name), or None."""
    try:
        return Document.objects.select_related("group", "owner").get(
            group__name=doc_uuid, is_deleted=False
        )
    except Document.DoesNotExist:
        return None


def get_document_for_user(doc_uuid: str, user) -> Document | None:
    """
    Return a Document the user has permission to access, or None.

    Returns None for non-existent, deleted, or inaccessible documents.
    Callers must distinguish 404 vs 403 themselves — this selector
    returns None in both cases to avoid revealing existence to unauthorized users.
    """
    document = get_document_by_uuid(doc_uuid)
    if document is None:
        return None

    from .permissions import has_view_permission
    if not has_view_permission(user, document):
        return None

    return document


def list_user_documents(user) -> QuerySet:
    """
    Return all non-deleted documents accessible to the user.

    Includes owned documents and documents shared with the user.
    Ordered by most recently updated.
    """
    return (
        Document.objects.select_related("group", "owner")
        .filter(
            Q(owner=user) | Q(permissions__user=user),
            is_deleted=False,
        )
        .distinct()
        .order_by("-updated_at")
    )


def get_revisions_for_document(document: Document) -> QuerySet:
    """Return revisions for a document, most recent first."""
    return DocumentRevision.objects.filter(document=document).select_related(
        "created_by"
    )

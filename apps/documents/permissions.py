"""
Document permission helpers.

These functions are the single source of truth for access control.
Views, consumers, and services must use these functions — no ad-hoc
permission checks anywhere else in the codebase.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    from .models import Document

    User = get_user_model()

from .models import DocumentPermission

logger = logging.getLogger(__name__)

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"


def get_user_role(user, document: "Document") -> str | None:
    """
    Return the user's role on the document.

    Returns:
        'owner'  — user is the document owner
        'editor' — user has editor permission
        'viewer' — user has viewer permission
        None     — user has no access
    """
    if not user or not user.is_authenticated:
        return None
    if document.owner_id == user.id:
        return ROLE_OWNER
    perm = (
        DocumentPermission.objects.filter(document=document, user=user)
        .values_list("role", flat=True)
        .first()
    )
    return perm  # 'editor', 'viewer', or None


def has_view_permission(user, document: "Document") -> bool:
    """Return True if the user can read the document."""
    return get_user_role(user, document) is not None


def has_edit_permission(user, document: "Document") -> bool:
    """Return True if the user can edit the document."""
    return get_user_role(user, document) in (ROLE_OWNER, ROLE_EDITOR)


def has_owner_permission(user, document: "Document") -> bool:
    """Return True if the user owns the document."""
    return get_user_role(user, document) == ROLE_OWNER

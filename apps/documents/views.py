"""Document views.

URL name conventions (must match urls.py):
  documents:list              GET  /documents/
  documents:create            POST /documents/create/
  documents:editor            GET  /documents/<uuid>/
  documents:delete            POST /documents/<uuid>/delete/
  documents:share             POST /documents/<uuid>/share/
  documents:revoke            POST /documents/<uuid>/share/<username>/revoke/
  documents:revisions         GET  /documents/<uuid>/revisions/
  documents:create_revision   POST /documents/<uuid>/revisions/create/
  documents:restore_revision  POST /documents/<uuid>/revisions/<int>/restore/
  documents:update_title      POST /documents/<uuid>/title/
"""
import json
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import Document, DocumentPermission, DocumentRevision
from .permissions import (
    get_user_role,
    has_edit_permission,
    has_owner_permission,
    has_view_permission,
)
from .selectors import (
    get_document_by_uuid,
    get_revisions_for_document,
    list_user_documents,
)
from .services import (
    create_document,
    create_revision,
    restore_revision,
    revoke_permission,
    share_document,
    soft_delete_document,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document list / create
# ---------------------------------------------------------------------------

@login_required
def document_list(request):
    """List all documents the user owns or has access to."""
    user = request.user
    owned = (
        Document.objects.select_related("group", "owner")
        .filter(owner=user, is_deleted=False)
        .order_by("-updated_at")
    )
    shared = (
        DocumentPermission.objects.select_related("document__group", "document__owner")
        .filter(user=user, document__is_deleted=False)
        .order_by("-document__updated_at")
    )
    return render(request, "documents/list.html", {
        "owned_documents": owned,
        "shared_documents": shared,
    })


@login_required
@require_http_methods(["POST"])
def document_create(request):
    """Create a new document and redirect to its editor."""
    title = request.POST.get("title", "Untitled document")[:255]
    document = create_document(owner=request.user, title=title)
    return redirect("documents:editor", doc_uuid=document.uuid)


# ---------------------------------------------------------------------------
# Document detail (editor)
# ---------------------------------------------------------------------------

@login_required
def document_detail(request, doc_uuid: str):
    """Render the collaborative editor for an accessible document."""
    document = get_document_by_uuid(doc_uuid)
    if document is None:
        raise Http404

    if not has_view_permission(request.user, document):
        return render(request, "documents/403.html", {"document": document}, status=403)

    role = get_user_role(request.user, document)
    permissions = DocumentPermission.objects.select_related("user").filter(document=document)

    return render(request, "documents/editor.html", {
        "document": document,
        "group_name": doc_uuid,
        "role": role,
        "can_edit": role in ("owner", "editor"),
        "permissions": permissions,
    })


# ---------------------------------------------------------------------------
# Title update (AJAX)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def title_update(request, doc_uuid: str):
    """Update the document title via JSON AJAX request."""
    document = _get_edit_document_or_error(request, doc_uuid)
    try:
        body = json.loads(request.body)
        title = str(body.get("title", ""))[:255]
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    if not title.strip():
        return JsonResponse({"error": "Title must not be blank."}, status=400)

    document.title = title
    document.save(update_fields=["title"])
    return JsonResponse({"status": "ok", "title": document.title})


# ---------------------------------------------------------------------------
# Permission management
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def permission_create(request, doc_uuid: str):
    """Grant a user access to a document (owner only)."""
    document = _get_owned_document_or_error(request, doc_uuid)

    username = request.POST.get("username", "").strip()
    role = request.POST.get("role", "").strip()

    try:
        target_user = User.objects.get(username=username)
    except User.DoesNotExist:
        messages.error(request, f"User '{username}' not found.")
        return redirect("documents:editor", doc_uuid=doc_uuid)

    try:
        share_document(request.user, document, target_user, role, request=request)
        messages.success(request, f"Shared with {username} as {role}.")
    except (PermissionError, ValueError) as e:
        messages.error(request, str(e))

    return redirect("documents:editor", doc_uuid=doc_uuid)


@login_required
@require_http_methods(["POST"])
def permission_delete(request, doc_uuid: str, username: str):
    """Revoke a user's access to a document (owner only)."""
    document = _get_owned_document_or_error(request, doc_uuid)

    try:
        target_user = User.objects.get(username=username)
    except User.DoesNotExist:
        raise Http404

    try:
        revoke_permission(request.user, document, target_user, request=request)
        messages.success(request, f"Access revoked for {username}.")
    except (PermissionError, ValueError) as e:
        messages.error(request, str(e))

    return redirect("documents:editor", doc_uuid=doc_uuid)


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------

@login_required
def revision_list(request, doc_uuid: str):
    """List revisions for a document."""
    document = _get_accessible_document_or_error(request, doc_uuid)
    role = get_user_role(request.user, document)
    revisions = get_revisions_for_document(document)
    return render(request, "documents/revisions.html", {
        "document": document,
        "revisions": revisions,
        "role": role,
        "auto_snapshot_every": 100,
    })


@login_required
@require_http_methods(["POST"])
def revision_create(request, doc_uuid: str):
    """Manually create a revision snapshot."""
    document = _get_accessible_document_or_error(request, doc_uuid)
    if not has_edit_permission(request.user, document):
        raise PermissionDenied
    revision = create_revision(document, created_by=request.user, trigger="manual")
    messages.success(request, f"Revision #{revision.revision_number} saved.")
    return redirect("documents:revisions", doc_uuid=doc_uuid)


@login_required
@require_http_methods(["POST"])
def revision_restore(request, doc_uuid: str, revision_number: int):
    """Restore a document to a previous revision."""
    document = _get_owned_document_or_error(request, doc_uuid)
    revision = get_object_or_404(
        DocumentRevision, revision_number=revision_number, document=document
    )
    try:
        restore_revision(request.user, document, revision, request=request)
        messages.success(request, f"Document restored to revision #{revision_number}.")
    except PermissionError as e:
        messages.error(request, str(e))
    return redirect("documents:editor", doc_uuid=doc_uuid)


# ---------------------------------------------------------------------------
# Document delete
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def document_delete(request, doc_uuid: str):
    """Soft-delete a document."""
    document = _get_owned_document_or_error(request, doc_uuid)
    soft_delete_document(request.user, document, request=request)
    messages.success(request, "Document deleted.")
    return redirect("documents:list")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_owned_document_or_error(request, doc_uuid: str) -> Document:
    document = get_document_by_uuid(doc_uuid)
    if document is None:
        raise Http404
    if not has_owner_permission(request.user, document):
        raise PermissionDenied
    return document


def _get_edit_document_or_error(request, doc_uuid: str) -> Document:
    document = get_document_by_uuid(doc_uuid)
    if document is None:
        raise Http404
    if not has_edit_permission(request.user, document):
        raise PermissionDenied
    return document


def _get_accessible_document_or_error(request, doc_uuid: str) -> Document:
    document = get_document_by_uuid(doc_uuid)
    if document is None:
        raise Http404
    if not has_view_permission(request.user, document):
        raise PermissionDenied
    return document

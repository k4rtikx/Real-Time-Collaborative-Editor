"""
Legacy views — preserved for backward-compat URLs: /, /home, /<room_id>/

The /<room_id>/ URL now redirects to /documents/<uuid>/ if the document
exists, or the new editor after creating it. This bridges old shared links.
"""
import uuid as _uuid

from django.shortcuts import redirect, render


def home(request):
    """Landing page — redirect authenticated users to their document list."""
    if request.user.is_authenticated:
        return redirect("documents:list")
    return render(request, "documents/home.html")


def index(request):
    """Create a new document and go to its editor."""
    if request.user.is_authenticated:
        from apps.documents.services import create_document
        document = create_document(owner=request.user)
        return redirect("documents:editor", doc_uuid=document.uuid)
    # Unauthenticated — just generate a room UUID and show legacy editor
    room_id = str(_uuid.uuid4())
    return redirect(f"/{room_id}/")


def room(request, room_id: str):
    """
    Legacy room view.
    If the room has an associated Document, redirect to the new editor.
    Otherwise fall back to the legacy index template so old links still open.
    """
    from documents.models import Group, Document as LegacyDocument

    try:
        group = Group.objects.get(name=room_id)
        doc = LegacyDocument.objects.get(group=group)
        # If the document has been migrated (has an owner), use new editor
        if doc.owner_id is not None:
            return redirect("documents:editor", doc_uuid=room_id)
    except (Group.DoesNotExist, LegacyDocument.DoesNotExist):
        pass

    # Fall back to legacy unauthenticated editor
    from documents.models import Group, Document as LegacyDocument
    group, _ = Group.objects.get_or_create(name=room_id)
    document, _ = LegacyDocument.objects.get_or_create(group=group)

    return render(request, "documents/index.html", {
        "group_name": room_id,
        "docs_json": {"content": document.content},
    })

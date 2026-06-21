import uuid
from django.shortcuts import render, redirect

from .models import Group, Document


def index(request):
    room_id = str(uuid.uuid4())
    return redirect(f"/{room_id}/") #Go to this URL


def room(request, room_id):

    group, created = Group.objects.get_or_create(
        name=room_id
    )   # Find room OR Create room

    document, created = Document.objects.get_or_create(
        group=group
    )   # Find document OR Create document
    if request.method == "POST":
        document.content = request.POST.get("content")
        document.save()

    return render(
        request,
        "documents/index.html",
        {
            "room_id": room_id,
            "document": document
        }
    )

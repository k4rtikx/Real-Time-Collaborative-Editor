import uuid
from django.shortcuts import render, redirect

from .models import Group, Document
import redis,os
redis_client = redis.Redis(host=os.getenv("REDIS_HOST"), port=6379, db=0, decode_responses=True)

def home(request):
    return render(request, "documents/home.html")
    
def index(request):
    room_id = str(uuid.uuid4())
    return redirect(f"/{room_id}/") #Go to this URL
    
    
def room(request, room_id):
    group, created = Group.objects.get_or_create(name=room_id)
    document, created = Document.objects.get_or_create(group=group)
    
    # Load from Redis cache first (fast), fall back to DB (slow)
    cached = redis_client.get(f"doc:{room_id}")# checking cache first
    content = cached if cached else document.content# if cached is there then use it else use db

    return render(request, "documents/index.html", {
        "group_name": room_id,
        "docs_json": {"content": content}
    })

























"""
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
        "group_name": room_id,
        "docs_json": {
            "content": document.content
        }
    }
) The POST block was from your original code when you were saving 
via HTTP form. Now you're saving via WebSocket, so that POST block 
is never used  — no form submits to it."""


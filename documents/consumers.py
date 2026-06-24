from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from .models import Group, Document
import redis, json, threading, os

redis_url = os.getenv("REDIS_URL")

if redis_url:
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
else:
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=6379,
        db=0,# Redis database number (0-15), we use default db 0
        decode_responses=True # automatically decode byte responses into strings
    )

def save_to_db_background(room_name, content):
    """Runs in a separate thread — doesn't block WebSocket at all"""
    try:
        group = Group.objects.get(name=room_name)
        document = Document.objects.get(group=group)
        document.content = content
        document.save()
    except Exception as e:
        print(f"DB SAVE ERROR: {e}")

class DocumentConsumer(WebsocketConsumer):

    def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_id"]
        async_to_sync(self.channel_layer.group_add)(self.room_name, self.channel_name)
        self.accept()

        count = redis_client.incr(f"users:{self.room_name}") # increments user count
        async_to_sync(self.channel_layer.group_send)(
            self.room_name, {"type": "user_count", "count": count}
        )
        print(f"CONNECTED: {self.channel_name} | room={self.room_name} | online={count}")

    def user_count(self, event):
        self.send(text_data=json.dumps({"type": "count", "count": event["count"]})) 

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(self.room_name, self.channel_name)
        count = redis_client.decr(f"users:{self.room_name}")
        async_to_sync(self.channel_layer.group_send)(
            self.room_name, {"type": "user_count", "count": count}
        )
        print(f"DISCONNECTED: {self.channel_name} | room={self.room_name} | online={count}")

    def receive(self, text_data):
        #  Save to Redis cache INSTANTLY
        redis_client.set(f"doc:{self.room_name}", text_data)

        #  Broadcast to others immediately (from Redis, no DB involved)
        async_to_sync(self.channel_layer.group_send)(
            self.room_name,
            {
                "type": "chat_message",
                "message": text_data,
                "sender_channel": self.channel_name # recieving the sender client
            }
        )

        # Save to Neon DB in background thread (slow, doesn't block anything)
        thread = threading.Thread(
            target=save_to_db_background,
            args=(self.room_name, text_data)
        )
        thread.daemon = True #daemon true means thread will automatically close when the main thread closes
        thread.start()

    def chat_message(self, event):
        if event.get("sender_channel") == self.channel_name:
            return
        self.send(text_data=json.dumps({
            "type": "editor",#label
            "message": event["message"]
        }))



# """group_add()     → Join a room/group
# group_discard() → Leave a room/group
# group_send()    → Send message to everyone in the room
# chat_message()  → Receive broadcasted message"""

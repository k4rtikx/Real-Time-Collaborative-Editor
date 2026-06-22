from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from .models import Group, Document
import redis,json 
redis_client = redis.Redis(
    host="127.0.0.1",
    port=6379,
    db=0,
    decode_responses=True
)
class DocumentConsumer(WebsocketConsumer):

    def connect(self): # Browser opens WebSocket
        self.room_name = self.scope["url_route"]["kwargs"]["room_id"] # Get room id from url
        async_to_sync(
            self.channel_layer.group_add #Join/add the channal_name / client to the route/channal 
        )(
            self.room_name, #Room name
            self.channel_name # Channel name given by the django to specific client 
        )
        print("WebSocket Connected")
        self.accept()
        # basically here we are joining the channal_name / client to the route/channal 
        # it help to send the message to the specific client
        count = redis_client.incr(
            f"users:{self.room_name}"
        )
        async_to_sync(
            self.channel_layer.group_send
        )(
            self.room_name,
            {
                "type": "user_count",
                "count": count
            }
        )

    def user_count(self, event):
        self.send(
            text_data=json.dumps({
                "type": "count",
                "count": event["count"]
            })
        )



    def disconnect(self, close_code): #Runs when browser closes tab.
        async_to_sync(
            self.channel_layer.group_discard #Leave a room/group
        )(
            self.room_name,
            self.channel_name # Channel name for this browser
        )
        print("WebSocket Disconnected")
        # basically here we are leaving the channal_name / client from the route/channal 
        count = redis_client.decr(
            f"users:{self.room_name}"
        )

        async_to_sync(
            self.channel_layer.group_send
        )(
            self.room_name,
            {
                "type": "user_count",
                "count": count
            }
        )




    def receive(self, text_data): #Runs when browser sends message.
        group = Group.objects.get(name=self.room_name)
        document = Document.objects.get(group=group)
        document.content = text_data 
        document.save() # it save the data into the db

        async_to_sync(
            self.channel_layer.group_send #Send message to everyone in the room
        )(
            self.room_name,
            {
                "type": "chat_message", # goes to chat_message() function 
                "message": text_data # send the text to every one in room 
            }
        )

    def chat_message(self, event):
        self.send(
            text_data=json.dumps({
                "type": "editor",
                "message": event["message"]
            })
        )
"""group_add()     → Join a room/group
group_discard() → Leave a room/group
group_send()    → Send message to everyone in the room
chat_message()  → Receive broadcasted message"""
#-------------------------before redis --------------------
# from channels.generic.websocket import WebsocketConsumer


# class DocumentConsumer(WebsocketConsumer):

#     def connect(self):#Runs when browser opens WebSocket connection.
#         print("WebSocket Connected")
#         self.accept()

#     def disconnect(self, close_code):#Runs when browser closes tab.
#         print("WebSocket Disconnected")

#     def receive(self, text_data): #Runs when browser sends message.
#         print(text_data)
#         self.send(text_data=text_data) 
#         #Echoes same message back.
#         #Used only to verify WebSocket works.
#         # Example:

#         # Browser -> Hello
#         # Server -> Hello
#         # This is called an echo consumer.
    



#---------------1st time ----------------------------------------
# class DocumentConsumer(WebsocketConsumer):

#     def connect(self):
#         print("CONNECTED")
#         self.accept()

#     def disconnect(self, close_code):
#         print("DISCONNECTED")

#     def receive(self, text_data):
#         print(text_data)
#         self.send(text_data=text_data)

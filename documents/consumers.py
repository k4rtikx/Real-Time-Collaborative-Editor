from channels.generic.websocket import WebsocketConsumer


class DocumentConsumer(WebsocketConsumer):

    def connect(self):#Runs when browser opens WebSocket connection.
        print("WebSocket Connected")
        self.accept()

    def disconnect(self, close_code):#Runs when browser closes tab.
        print("WebSocket Disconnected")

    def receive(self, text_data): #Runs when browser sends message.
        print(text_data)
        self.send(text_data=text_data) 
        #Echoes same message back.
        #Used only to verify WebSocket works.
        # Example:

        # Browser -> Hello
        # Server -> Hello
        # This is called an echo consumer.
    



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

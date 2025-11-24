import json
import jwt
from django.conf import settings
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

class ChatConsumer(AsyncWebsocketConsumer):


    # Conneect

    async def connect(self):
        cookies = self.scope["cookies"]
        token = cookies.get("token")
        if not token:
            print("No token found in cookies")
            await self.close()
            return


        # Decode JWT and authenticate user

        try:
            # Decode JWT
            decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user_id = decoded.get("user_id")

            if not user_id:
                print("User ID not found in token")
                await self.close()
                return

            # Get user object
            self.user = await self.get_user(user_id)
            user = self.user
            if not self.user:
                print("User not found")
                await self.close()
                return

            # Create a unique group for this user
            self.user_group_name = f"user_{self.user.id}"

            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )

            # Connected ✔
            await self.accept()



            await self.send(text_data=json.dumps({
                "user": {
                    "id": str(user.id),
                    "name": user.name,
                    "email": user.email,
                },
            }))

        # Handle JWT errors

        except jwt.ExpiredSignatureError:
            print("Token has expired")
            await self.close()
        except jwt.InvalidTokenError:
            print("Invalid token")
            await self.close()
        except Exception as e:
            print(f"Error during connection: {e}")
            await self.close()



    # Disconnect

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected with code: {close_code}")


    # Receive


    async def receive(self, text_data):
        from api.models import User, Chat, Messages

        data   = json.loads(text_data)
        action = data.get("action")
        message = data.get("message")


        #
        #    Handle new chat message
        #

        if action == "new_chat":
            receiver_id     = message["receiver_id"]
            sender_id       = message["sender_id"]
            text            = message["text"]  

            receiver_group_name = f"user_{receiver_id}"

            # create chat and message in DB
            chat = Chat(type="private", users_id=[receiver_id, sender_id])
            await database_sync_to_async(chat.save)()

            message_db = Messages(chat_id=chat.id, sender_id=sender_id, text=text)
            await database_sync_to_async(message_db.save)()


            # Fetch message again to access created_at
            saved_message = await database_sync_to_async(
                lambda: Messages.objects.get(id=message_db.id)
            )()

            # Add time to message object
            message["time"] = str(saved_message.time)


            user = await self.get_user(receiver_id)

             # -------  SEND NEW CHAT CREATED -------
            chat_obj = {
                "chat_id": str(chat.id),
                "user_id": str(receiver_id),      # or the user's id you're chatting with
                "name": user.name,                  # you can put username here
                "last_message": text,
                "last_message_time": message["time"]
            }

            # Send new chat event to BOTH users
            for uid in [sender_id, receiver_id]:
                await self.channel_layer.group_send(
                    f"user_{uid}",
                    {
                        "type": "new_chat_created",
                        "chat": chat_obj
                    }
                )
            # ----------------------------------------

            # Send message to receiver's group
            await self.channel_layer.group_send(
                receiver_group_name,
                {
                    "type": "chat_message",
                    "message": message,
                    "sender_id": sender_id,
                }
            )

            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": message,
                "sender_id": sender_id,
            }))


        #
        #    Handle get chats
        #


        if action == "get_user_chats":
            user_id = message["user_id"]

            chats_from_db = await database_sync_to_async(list)(
                Chat.objects.filter(users_id__contains=[user_id])
            )

            # Map of { "other_user_id": chat_id }
            map_user_to_chat = {}

            for chat in chats_from_db:
                for uid in chat.users_id:
                    if str(uid) != str(user_id):
                        map_user_to_chat[str(uid)] = str(chat.id)

            other_user_ids = list(map_user_to_chat.keys())

            # Get user objects
            users_from_db = await database_sync_to_async(list)(
                User.objects.filter(id__in=other_user_ids)
            )

            chats = []
            for user in users_from_db:
                uid = str(user.id)
                chat_id = map_user_to_chat[uid]

                # --- get last message ---
                last_msg = await database_sync_to_async(
                    lambda: Messages.objects.filter(chat_id=chat_id)
                    .order_by("-time")
                    .first()
                )()

                chats.append({
                    "user_id": uid,
                    "name": user.name,
                    "chat_id": chat_id,
                    "last_message": last_msg.text if last_msg else None,
                    "last_message_time": last_msg.time.isoformat() if last_msg else None,
                })

            await self.send(text_data=json.dumps({
                "action": "user_chats",
                "chats": chats,
            }))



        #
        #    Handle get messages
        #

        if action == 'get_messages':
            chat_id = message["chat_id"]

            messages = await self.get_messages(chat_id)

            await self.send(text_data=json.dumps({
                "action": "chat_messages",
                "messages": messages,
            }))
        

        #
        #    Handle send message
        #
    
        if action == 'send_message':
            receiver_id     = message["receiver_id"]
            sender_id       = message["sender_id"]
            text            = message["text"]  
            chat_id         = message["chat_id"]  

            receiver_group_name = f"user_{receiver_id}"
            message_db = await self.create_message(chat_id, sender_id, text)

            await self.channel_layer.group_send(
                receiver_group_name,
                {
                    "type": "chat_message",
                    "message": message_db,
                    "sender_id": sender_id,
                }
            )

            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": message_db,
                "sender_id": sender_id,
            }))


        #
        #    Handle send message
        #

        if action == 'get_all_users':
            users = await self.get_all_users()
            await self.send(text_data=json.dumps({
                "action": "all_users",
                "users": users
            }))

    # Handle chat message event

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "chat_message",
            "message": event["message"],
            "sender_id": event["sender_id"],
        }))

    async def new_chat_created(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_chat_created",
            "chat": event["chat"],
        }))


    # 
    #   Helpers
    #

    # Getting user from DB
    @database_sync_to_async
    def get_user(self, user_id):
        from api.models import User  

        try:
            return User.objects.get(id=user_id)
        
        except User.DoesNotExist:
            return None
        
    @database_sync_to_async
    def get_messages(self, chat_id):
        from api.models import Messages

        messages = list(Messages.objects.filter(chat_id=chat_id).values())

        # Convert UUIDs to strings
        for msg in messages:
            msg["id"] = str(msg["id"])
            msg["chat_id"] = str(msg["chat_id"])
            msg["sender_id"] = str(msg["sender_id"])
            msg["text"] = str(msg["text"])
            msg["time"] = str(msg["time"])

        return messages
    
    @database_sync_to_async
    def create_message(self, chat_id, sender_id, text):
        from api.models import Messages
        msg = Messages.objects.create(chat_id=chat_id, sender_id=sender_id, text=text)
        return {
            "id": str(msg.id),
            "chat_id": str(msg.chat_id),
            "sender_id": str(msg.sender_id),
            "text": msg.text,
            "time": str(msg.time),
        }

    @database_sync_to_async
    def get_all_users(self):
        from api.models import User
        users = User.objects.all().values("id", "name")
        # Django ORM here is safe
        return [
            {
                "id": str(user["id"]),
                "name": user["name"]
            }
            for user in users
        ]


import jwt

class JWTAuthMiddleware:
    """
    Reads 'token' from query string, verifies JWT (like your REST views), and sets scope['user'].
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):

        
        from django.contrib.auth.models import AnonymousUser
        from channels.db import database_sync_to_async
        from django.conf import settings
        from urllib.parse import parse_qs
        from django.contrib.auth import get_user_model
        from uuid import UUID

        User = get_user_model()

        scope['user'] = AnonymousUser()

        query_string = scope['query_string'].decode()
        params = parse_qs(query_string)
        token = params.get("token", [None])[0]

        print("Query string:", query_string)
        print("Token:", token)

        if not token:
            print("No token in query string")
            return await self.inner(scope, receive, send)

        try:
            # decode same as your _get_user_from_token()
            decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user_id = decoded.get("user_id")
            print("Decoded payload:", decoded)

            if user_id:
                try:
                    # convert to UUID if needed
                    user = await database_sync_to_async(User.objects.get)(id=UUID(user_id))
                except (ValueError, User.DoesNotExist):
                    user = await database_sync_to_async(User.objects.get)(id=user_id)

                scope['user'] = user
                print("✅ User fetched:", user)

        except jwt.ExpiredSignatureError:
            print("❌ Token expired")
        except jwt.InvalidTokenError:
            print("❌ Invalid token")
        except Exception as e:
            print("❌ Unexpected error:", e)

        return await self.inner(scope, receive, send)

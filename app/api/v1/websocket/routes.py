# External imports
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List
import json
import logging
from openai import OpenAI
import redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Internal imports
from ....services.auth.security_service import SecurityService
from ....services.entity_tracker import EntityTrackingService
from ....services.document_processor import DocumentProcessor
from ....core.config import settings
from ....models.user import User
from ....database import async_session


router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize services
security_service = SecurityService(settings.SECRET_KEY, settings.ALGORITHM)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB
)

document_processor = DocumentProcessor()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug("New WebSocket connection accepted")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.debug("WebSocket connection removed")

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data[:100]}...")
            
            message_data = json.loads(data)
            
            # Check message type
            if message_data.get('type') == 'command':
                # Handle command messages
                command = message_data.get('command')
                payload = message_data.get('payload', {})
                logger.debug(f"Received command: {command} with payload: {payload}")
                
                # Handle project_context command
                if command == 'project_context':
                    await websocket.send_json({
                        "type": "command_response",
                        "command": command,
                        "status": "success",
                        "payload": payload
                    })
                    continue
                
                # Add entity tracking commands
                # if command == 'track_entity':
                #     # Initialize services
                #     async with async_session() as session:
                #         entity_tracker = EntityTrackingService(session, document_processor)
                        
                #         try:
                #             entity = await entity_tracker.add_tracked_entity(
                #                 name=payload['name'],
                #                 entity_type=payload.get('type', 'CUSTOM'),
                #                 metadata=payload.get('metadata')
                #             )
                            
                #             await websocket.send_json({
                #                 "type": "command_response",
                #                 "command": command,
                #                 "status": "success",
                #                 "data": {
                #                     "entity_id": str(entity.entity_id),
                #                     "name": entity.name
                #                 }
                #             })
                #         except Exception as e:
                #             await websocket.send_json({
                #                 "type": "error",
                #                 "command": command,
                #                 "error": str(e)
                #             })
                
                # elif command == 'get_entity_mentions':
                #     async with async_session() as session:
                #         entity_tracker = EntityTrackingService(session, document_processor)
                        
                #         try:
                #             mentions = await entity_tracker.get_entity_mentions(
                #                 entity_name=payload['name'],
                #                 limit=payload.get('limit', 50),
                #                 offset=payload.get('offset', 0)
                #             )
                            
                #             await websocket.send_json({
                #                 "type": "command_response",
                #                 "command": command,
                #                 "status": "success",
                #                 "data": mentions
                #             })
                #         except Exception as e:
                #             await websocket.send_json({
                #                 "type": "error",
                #                 "command": command,
                #                 "error": str(e)
                #             })
            
            # Handle regular chat messages
            elif message_data.get('type') == 'chat':
                user_message = message_data.get('message')
                logger.debug(f"Received chat message: {user_message[:100]}...")
                
                # Check if this is a command message
                if user_message.startswith('/'):
                    logger.debug(f"Received command: {user_message}")
                    # Handle commands without sending to OpenAI
                    if user_message.startswith('/select_project'):
                        # You can add any project-specific handling here
                        continue
                    # Add other command handlers as needed
                    continue
                
                try:
                    # Get the auth cookie from the WebSocket headers
                    cookies = websocket.headers.get('cookie', '')
                    auth_token = None
                    
                    # Parse cookies string to find auth token
                    if cookies:
                        for cookie in cookies.split(';'):
                            cookie = cookie.strip()
                            if '=' in cookie:  # Make sure there's a key-value pair
                                name, value = cookie.split('=', 1)
                                if name.strip() == 'auth_token':  # Use your actual cookie name here
                                    auth_token = value.strip()
                                    break
                    
                    if not auth_token:
                        raise ValueError("No authentication token found in cookies")
                    
                    logger.debug(f"Found auth token in cookies: {auth_token[:20]}...")
                    
                    token_data = security_service.decode_token(auth_token)
                    logger.debug(f"Decoded token data: {token_data}")
                    # user_id = token_data.get('user_id')
                    user_id = "aa5c38ff-7fb4-41d0-9fb3-ed2d67d3b4c3" # for use in development
                    
                    if not user_id:
                        raise ValueError("No user_id in token")
                    
                    logger.debug(f"Looking up API key for user_id: {user_id}")
                    
                    # Get the API key from Redis first (faster)
                    redis_key = f"openai_key:{user_id}"
                    # Clear any existing cached key
                    redis_client.delete(redis_key)
                    api_key = redis_client.get(redis_key)
                    
                    if not api_key:
                        logger.debug("API key not found in Redis, checking database...")
                        # If not in Redis, get from database
                        async with async_session() as session:
                            # Debug: List all users in the database
                            all_users_result = await session.execute(
                                select(User)
                            )
                            all_users = all_users_result.scalars().all()
                            logger.debug("All users in database:")
                            for user in all_users:
                                logger.debug(f"User ID: {user.user_id}, Email: {user.email}, Has API Key: {bool(user.openai_api_key)}")
                            
                            # Now try to find our specific user
                            result = await session.execute(
                                select(User).where(User.user_id == user_id)
                            )
                            user = result.scalar_one_or_none()
                            
                            if not user:
                                logger.error(f"User lookup failed for ID: {user_id}")
                                # Try to find by email if it's in the token
                                email = token_data.get('email')
                                if email:
                                    email_result = await session.execute(
                                        select(User).where(User.email == email)
                                    )
                                    user = email_result.scalar_one_or_none()
                                    if user:
                                        logger.debug(f"Found user by email instead: {email}")
                                
                                if not user:
                                    raise ValueError(f"No user found for ID: {user_id}")
                            
                            if not user.openai_api_key:
                                raise ValueError("No OpenAI API key found for user")
                            
                            logger.debug(f"Found API key in database for user: {user_id}")
                            api_key = user.openai_api_key.encode()
                            
                            # Cache in Redis for future use
                            redis_client.setex(
                                redis_key,
                                2592000,  # 30 days
                                api_key
                            )
                            await session.commit()
                    else:
                        logger.debug("Found API key in Redis cache")
                    
                    # Process the message with the API key
                    client = OpenAI(api_key=api_key.decode())
                    response = await process_chat_message(client, user_message)
                    
                    # Send response as JSON
                    await websocket.send_json({
                        "type": "chat",
                        "content": response,
                        "role": "assistant"
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e)
                    })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.debug("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })

async def process_chat_message(client: OpenAI, message: str) -> str:
    """Process chat message with OpenAI"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "user",
                "content": message
            }],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        raise
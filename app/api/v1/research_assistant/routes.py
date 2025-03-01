from contextlib import asynccontextmanager
from fastapi import APIRouter, WebSocket, HTTPException, Depends, Body, Cookie
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import logging


from app.database import get_db
from app.models.news_article import NewsArticle
from app.models.conversation import Conversation, Message
from app.services.research_assistant import ResearchAssistant
from app.services.conversation_service import ConversationService
from app.services.security_service import SecurityService
from app.core.config import settings    

logger = logging.getLogger(__name__)


# Global service instances
conversation_service = None
research_assistant = ResearchAssistant()
security_service = SecurityService(settings.SECRET_KEY, settings.ALGORITHM)

@asynccontextmanager
async def lifespan(app):
    # Initialize services on startup
    global conversation_service
    conversation_service = ConversationService(get_db(), research_assistant)
    
    yield
    
    # Cleanup on shutdown
    # Add any cleanup code here if needed

router = APIRouter(lifespan=lifespan)

print("Initializing research_assistant router")  # Debug log

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    stream: bool = True

class StructuredChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    output_schema: Dict[str, Any]

class NewsAnalysisRequest(BaseModel):
    messages: List[Dict[str, str]]

@router.post("/chat")
async def chat(request: ChatRequest):
    """Handle chat requests with optional streaming"""
    if request.stream:
        return StreamingResponse(
            research_assistant.chat(request.messages),
            media_type="text/event-stream"
        )
    return await research_assistant.chat(request.messages, stream=False)

@router.post("/structured-chat")
async def structured_chat(request: StructuredChatRequest):
    """Handle structured chat requests"""
    return await research_assistant.structured_chat(
        request.messages,
        request.output_schema
    )

@router.post("/generate-analysis-from-news-article")
async def generate_analysis_from_news_article(
    request: NewsAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate analysis for a news article"""
    try:
        print(f"Received request body: {request}")  # Debug log to see raw request
        
        # Find the user message in the messages list
        user_message = next(
            (msg for msg in request.messages if msg.get("role") == "user"),
            None
        )
        
        if not user_message:
            raise HTTPException(
                status_code=400,
                detail="No user message found in request"
            )

        # Extract URL using more robust parsing
        content_lines = user_message.get("content", "").split('\n')
        url_line = next(
            (line.strip() for line in content_lines if 'URL:' in line),
            None
        )
        
        if not url_line:
            print(f"Debug - Message content: {user_message}")  # Debug log
            raise HTTPException(
                status_code=400,
                detail="Article URL not found in message content"
            )
            
        article_url = url_line.split('URL:')[1].strip()
        
        print(f"Debug - Extracted URL: {article_url}")  # Debug log

        # Query the database for the article
        query = select(NewsArticle).where(NewsArticle.url == article_url)
        result = await db.execute(query)
        article = result.scalar_one_or_none()

        if not article:
            raise HTTPException(
                status_code=404,
                detail=f"Article not found for URL: {article_url}"
            )

        # Generate the analysis
        result = await research_assistant.generate_analysis_from_news_article(request.messages)
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating analysis: {str(e)}")  # Debug log
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """Handle WebSocket chat connections"""
    print("New WebSocket connection attempt")  # Debug log
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            print(f"Received data: {data}")  # Debug log
            
            # Check message type and extract messages
            if data.get("type") != "chat":
                print(f"Invalid message type: {data.get('type')}")  # Debug log
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid message type. Expected 'chat'"
                })
                continue
                
            messages_data = data.get("messages", [])
            print(f"Messages data: {messages_data}")  # Debug log
            
            if not messages_data:
                print("No messages found")  # Debug log
                await websocket.send_json({
                    "type": "error",
                    "error": "No messages found in request"
                })
                continue
                
            try:
                messages = messages_data
                print(f"Parsed messages: {messages}")  # Debug log
            except Exception as e:
                print(f"Message parsing error: {e}")  # Debug log
                await websocket.send_json({
                    "type": "error",
                    "error": f"Invalid message format: {str(e)}"
                })
                continue
            
            # Process through research assistant
            try:
                print("Starting chat with research assistant")  # Debug log
                async for chunk in research_assistant.chat(messages):
                    print(f"Received chunk: {chunk}")  # Debug log
                    if isinstance(chunk, dict):
                        await websocket.send_json(chunk)
                    else:
                        print(f"Unexpected chunk format: {chunk}")
                        
            except Exception as e:
                print(f"Research assistant error: {str(e)}")  # Debug log
                await websocket.send_json({
                    "type": "error",
                    "error": f"Error processing chat: {str(e)}"
                })
                
    except Exception as e:
        print(f"WebSocket error: {str(e)}")  # Debug log
        await websocket.send_json({
            "type": "error",
            "error": f"WebSocket error: {str(e)}"
        })
    finally:
        await websocket.close()



@router.websocket("/ws/conversations/{conversation_id}/chat")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Handle WebSocket chat connections for a specific conversation"""
    print(f"New WebSocket connection attempt for conversation {conversation_id}")
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") != "chat":
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid message type. Expected 'chat'"
                })
                continue
            
            messages_data = data.get("messages", [])
            if not messages_data:
                await websocket.send_json({
                    "type": "error",
                    "error": "No messages found in request"
                })
                continue
            
            try:
                # Process message and get response
                response = await conversation_service.process_message(
                    conversation_id,
                    messages_data[-1]["content"]  # Get the last message
                )
                
                # Send response chunks to client
                async for chunk in research_assistant.chat([{
                    "role": "user",
                    "content": messages_data[-1]["content"]
                }]):
                    if isinstance(chunk, dict):
                        await websocket.send_json(chunk)
                    
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "error": f"Error processing message: {str(e)}"
                })
                
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
    finally:
        await websocket.close()

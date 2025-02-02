from fastapi import APIRouter, WebSocket, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.research_assistant import ResearchAssistant, Message
from app.database import get_db
from app.models.news_article import NewsArticle

router = APIRouter()
research_assistant = ResearchAssistant()

print("Initializing research_assistant router")  # Debug log

class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = True

class StructuredChatRequest(BaseModel):
    messages: List[Message]
    output_schema: Dict[str, Any]

class NewsAnalysisRequest(BaseModel):
    messages: List[Message]

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
        # Extract article ID from the first message
        # Assuming the message contains the article ID in a consistent format
        first_message = request.messages[0].content
        article_info = first_message.split('\n')
        article_url = next((line.split('URL: ')[1] for line in article_info if line.startswith('URL: ')), None)

        if not article_url:
            raise HTTPException(status_code=400, detail="Article URL not found in request")

        # Query the database for the article
        query = select(NewsArticle).where(NewsArticle.url == article_url)
        result = await db.execute(query)
        article = result.scalar_one_or_none()

        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # If content isn't available, try to get it
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content not available")

        # Create a new message with the full article content
        analysis_message = Message(
            role="user",
            content=f"""Please analyze this news article:
Title: {article.title}
URL: {article.url}
Content: {article.content}

Please provide a detailed analysis focusing on:
1. Key facts and claims
2. Sources cited
3. Context and background
4. Potential biases or missing information
5. Related topics for further research"""
        )

        # Generate the analysis
        result = await research_assistant.generate_analysis_from_news_article([analysis_message])
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating analysis: {str(e)}")  # Debug log
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate analysis: {str(e)}"
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
                messages = [Message(**msg) for msg in messages_data]
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

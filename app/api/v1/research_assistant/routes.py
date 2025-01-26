from fastapi import APIRouter, WebSocket
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any
from pydantic import BaseModel

from app.services.research_assistant import ResearchAssistant, Message

router = APIRouter()
research_assistant = ResearchAssistant()

class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = True

class StructuredChatRequest(BaseModel):
    messages: List[Message]
    output_schema: Dict[str, Any]

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

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """Handle WebSocket chat connections"""
    await websocket.accept()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            messages = [Message(**msg) for msg in data.get("messages", [])]
            
            # Process through research assistant
            async for chunk in research_assistant.chat(messages):
                if chunk.get("message", {}).get("content"):
                    await websocket.send_json(chunk)
                    
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

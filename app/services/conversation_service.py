from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.conversation import Conversation, Message
from app.services.research_assistant import ResearchAssistant
from uuid import UUID

class ConversationService:
    def __init__(self, db: Session, research_assistant: ResearchAssistant):
        self.db = db
        self.research_assistant = research_assistant

    async def create_conversation(self, project_id: UUID, name: str) -> Conversation:
        """Create a new conversation in a project"""
        conversation = Conversation(
            project_id=project_id,
            name=name,
            meta_data={
                "document_references": [],
                "key_findings": [],
                "tags": []
            }
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    async def add_message(self, 
                         conversation_id: int, 
                         role: str, 
                         content: str,
                         meta_data: Dict = None) -> Message:
        """Add a new message to the conversation"""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            meta_data=meta_data or {}
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    async def get_conversation_history(self, conversation_id: int) -> List[Dict]:
        """Get all messages in a conversation"""
        conversation = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()
        
        if not conversation:
            raise ValueError("Conversation not found")
            
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "meta_data": msg.meta_data
            }
            for msg in conversation.messages
        ]

    async def process_message(self, 
                            conversation_id: int, 
                            user_message: str) -> Dict:
        """Process a user message and get AI response"""
        # Get conversation history
        history = await self.get_conversation_history(conversation_id)
        
        # Add user message to database
        await self.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message
        )
        
        # Get AI response
        response = await self.research_assistant.chat(messages=history + [
            {"role": "user", "content": user_message}
        ])
        
        # Add AI response to database
        await self.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response["message"]["content"],
            meta_data=response.get("meta_data", {})
        )
        
        return response

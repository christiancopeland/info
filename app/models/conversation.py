from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    project_id = Column(UUID, ForeignKey("research_projects.project_id"))
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    # Rename metadata to meta_data to avoid conflict with SQLAlchemy's reserved word
    meta_data = Column(JSON, default=dict)
    
    # Relationships
    project = relationship("ResearchProject", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.timestamp")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    role = Column(String)  # 'user' or 'assistant'
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    
    # Rename metadata to meta_data
    meta_data = Column(JSON, default=dict)
    
    # Relationship
    conversation = relationship("Conversation", back_populates="messages")

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('research_projects.project_id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    meta_data = Column(JSON, default=dict)
    
    # Relationships
    project = relationship("ResearchProject", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.timestamp")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id', ondelete='CASCADE'))
    role = Column(String(50), nullable=False)
    content = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    meta_data = Column(JSON, default=dict)
    
    # Relationship
    conversation = relationship("Conversation", back_populates="messages")

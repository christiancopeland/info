from typing import Dict, Optional
from sqlalchemy import Column, String, JSON, ForeignKey, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
from ..database import Base

class TrackedEntity(Base):
    """
    Model for storing tracked entities.
    
    Attributes:
        entity_id (UUID): Unique identifier for the entity
        user_id (UUID): ID of the user who created/owns this entity
        name (str): Name of the entity (stored in lowercase for case-insensitive matching)
        entity_type (str): Type of entity (PERSON, ORG, LOCATION, CUSTOM)
        created_at (str): ISO format timestamp of when the entity was created
        entity_metadata (JSON): Additional metadata about the entity
    """
    __tablename__ = "tracked_entities"
    
    entity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    name_lower = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc))
    entity_metadata = Column(JSON, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'name_lower', name='uq_user_entity_name'),
        Index('ix_tracked_entities_name_lower_trgm', 'name_lower', postgresql_using='gist', postgresql_ops={'name_lower': 'gist_trgm_ops'}),
    )
    
    def __repr__(self):
        return f"<TrackedEntity(name='{self.name}', type='{self.entity_type}')>"
    
    def to_dict(self) -> Dict:
        """Convert entity to dictionary representation"""
        return {
            "entity_id": str(self.entity_id),
            "user_id": str(self.user_id),
            "name": self.name,
            "entity_type": self.entity_type,
            "created_at": self.created_at,
            "entity_metadata": self.entity_metadata or {}
        }

class EntityMention(Base):
    """
    Model for storing entity mentions in documents and news articles.
    
    Attributes:
        mention_id (UUID): Unique identifier for the mention
        entity_id (UUID): ID of the referenced tracked entity
        document_id (UUID): ID of the document containing the mention (if from document)
        news_article_id (UUID): ID of the news article containing the mention (if from news)
        user_id (UUID): ID of the user who owns this mention
        chunk_id (str): ID of the document chunk containing the mention
        context (str): Surrounding text context of the mention
        timestamp (str): ISO format timestamp of when the mention was found
    """
    __tablename__ = "entity_mentions"
    
    mention_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("tracked_entities.entity_id", ondelete="CASCADE"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=True)
    news_article_id = Column(UUID(as_uuid=True), ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    chunk_id = Column(String, nullable=False)
    context = Column(String, nullable=False)
    timestamp = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    
    __table_args__ = (
        # Ensure at least one of document_id or news_article_id is set
        CheckConstraint(
            '(document_id IS NOT NULL AND news_article_id IS NULL) OR '
            '(document_id IS NULL AND news_article_id IS NOT NULL)',
            name='check_one_source_id'
        ),
    )
    
    def __repr__(self):
        source_id = self.document_id or self.news_article_id
        source_type = "document" if self.document_id else "news"
        return f"<EntityMention(entity_id='{self.entity_id}', {source_type}_id='{source_id}')>"
    
    def to_dict(self) -> Dict:
        """Convert mention to dictionary representation"""
        return {
            "mention_id": str(self.mention_id),
            "entity_id": str(self.entity_id),
            "document_id": str(self.document_id) if self.document_id else None,
            "news_article_id": str(self.news_article_id) if self.news_article_id else None,
            "user_id": str(self.user_id),
            "chunk_id": self.chunk_id,
            "context": self.context,
            "timestamp": self.timestamp
        }

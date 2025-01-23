from typing import List, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, JSON, ForeignKey, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import logging
from ..database import Base
import uuid

logger = logging.getLogger(__name__)

# Database Models
class TrackedEntity(Base):
    """Model for storing tracked entities"""
    __tablename__ = "tracked_entities"
    
    entity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)  # PERSON, ORG, LOCATION, CUSTOM
    created_at = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())
    metadata = Column(JSON, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_user_entity_name'),
    )

class EntityMention(Base):
    """Model for storing entity mentions"""
    __tablename__ = "entity_mentions"
    
    mention_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("tracked_entities.entity_id", ondelete="CASCADE"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    chunk_id = Column(String, nullable=False)  # Qdrant chunk ID
    context = Column(String, nullable=False)
    timestamp = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())

class EntityTrackingService:
    """Service for tracking and analyzing entities across documents"""
    
    def __init__(self, session: AsyncSession, document_processor):
        self.session = session
        self.document_processor = document_processor
        self.active_entities: Set[str] = set()  # Cache of currently tracked entities
    
    async def add_tracked_entity(
        self,
        name: str,
        entity_type: str = "CUSTOM",
        metadata: Optional[Dict] = None
    ) -> TrackedEntity:
        """Add a new entity to track"""
        try:
            entity = TrackedEntity(
                name=name.lower(),  # Store lowercase for case-insensitive matching
                entity_type=entity_type,
                metadata=metadata or {}
            )
            self.session.add(entity)
            await self.session.commit()
            await self.session.refresh(entity)
            
            # Add to active entities cache
            self.active_entities.add(name.lower())
            
            logger.info(f"Added new tracked entity: {name} ({entity_type})")
            return entity
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error adding tracked entity: {str(e)}")
            raise
    
    async def scan_document_for_entities(
        self,
        document_id: uuid.UUID,
        content: str
    ) -> List[Dict]:
        """Scan document content for tracked entities"""
        mentions = []
        
        try:
            # Get chunks from document processor
            chunks = self.document_processor._chunk_text(content)
            
            for chunk_idx, chunk in enumerate(chunks):
                chunk_lower = chunk.lower()
                
                # Check for each tracked entity
                for entity_name in self.active_entities:
                    if entity_name in chunk_lower:
                        # Find the original case in the chunk
                        start_idx = chunk_lower.index(entity_name)
                        end_idx = start_idx + len(entity_name)
                        
                        # Get surrounding context
                        context_start = max(0, start_idx - 100)
                        context_end = min(len(chunk), end_idx + 100)
                        context = chunk[context_start:context_end]
                        
                        mention = EntityMention(
                            entity_id=await self._get_entity_id(entity_name),
                            document_id=document_id,
                            chunk_id=f"{document_id}_{chunk_idx}",
                            context=context
                        )
                        self.session.add(mention)
                        mentions.append(mention)
            
            await self.session.commit()
            logger.info(f"Found {len(mentions)} entity mentions in document {document_id}")
            return mentions
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error scanning document: {str(e)}")
            raise
    
    async def get_entity_mentions(
        self,
        entity_name: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """Get recent mentions of an entity"""
        try:
            entity_id = await self._get_entity_id(entity_name)
            
            mentions = await self.session.execute(
                """
                SELECT m.context, m.timestamp, d.filename
                FROM entity_mentions m
                JOIN documents d ON m.document_id = d.document_id
                WHERE m.entity_id = :entity_id
                ORDER BY m.timestamp DESC
                LIMIT :limit OFFSET :offset
                """,
                {"entity_id": entity_id, "limit": limit, "offset": offset}
            )
            
            return [dict(m) for m in mentions]
            
        except Exception as e:
            logger.error(f"Error getting entity mentions: {str(e)}")
            raise
    
    async def _get_entity_id(self, entity_name: str) -> uuid.UUID:
        """Get entity ID from name"""
        result = await self.session.execute(
            """
            SELECT entity_id FROM tracked_entities
            WHERE name = :name
            """,
            {"name": entity_name.lower()}
        )
        entity_id = result.scalar_one_or_none()
        if not entity_id:
            raise ValueError(f"Entity not found: {entity_name}")
        return entity_id

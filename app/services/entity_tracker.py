from typing import List, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import logging
from ..models.entities import TrackedEntity, EntityMention
from ..models.news_article import NewsArticle
import uuid

logger = logging.getLogger(__name__)

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
        metadata: Optional[Dict] = None,
        user_id: uuid.UUID = None
    ) -> TrackedEntity:
        """Add a new entity to track and scan existing articles"""
        try:
            # Create the entity
            entity = TrackedEntity(
                name=name.lower(),  # Store lowercase for case-insensitive matching
                entity_type=entity_type,
                entity_metadata=metadata or {},
                user_id=user_id
            )
            self.session.add(entity)
            await self.session.commit()
            await self.session.refresh(entity)
            
            # Add to active entities cache
            self.active_entities.add(name.lower())
            
            # Scan existing articles for mentions
            await self._scan_existing_articles(entity)
            
            logger.info(f"Added new tracked entity: {name} ({entity_type})")
            return entity
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error adding tracked entity: {str(e)}")
            raise

    async def _scan_existing_articles(self, entity: TrackedEntity):
        """Scan existing news articles for entity mentions"""
        try:
            # Get all news articles
            query = select(NewsArticle)
            result = await self.session.execute(query)
            articles = result.scalars().all()
            
            for article in articles:
                # Combine title and content for scanning
                content = f"{article.title}\n{article.content}" if article.content else article.title
                
                # Check for entity mention
                if entity.name.lower() in content.lower():
                    # Create mention record
                    mention = EntityMention(
                        entity_id=entity.entity_id,
                        document_id=article.id,
                        context=self._extract_context(content, entity.name),
                        chunk_id=f"{article.id}_0"  # Using single chunk for articles
                    )
                    self.session.add(mention)
            
            await self.session.commit()
            logger.info(f"Scanned existing articles for entity: {entity.name}")
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error scanning existing articles: {str(e)}")
            raise

    def _extract_context(self, content: str, entity_name: str, context_window: int = 100) -> str:
        """Extract context around entity mention"""
        content_lower = content.lower()
        entity_lower = entity_name.lower()
        
        # Find the position of the entity
        pos = content_lower.find(entity_lower)
        if pos == -1:
            return ""
        
        # Calculate context window
        start = max(0, pos - context_window)
        end = min(len(content), pos + len(entity_name) + context_window)
        
        # Extract and clean context
        context = content[start:end].strip()
        return context

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
            logger.debug(f"Found entity_id {entity_id} for entity name '{entity_name}'")
            
            query = text("""
                SELECT m.context, m.timestamp, d.filename
                FROM entity_mentions m
                JOIN documents d ON m.document_id = d.document_id
                WHERE m.entity_id = :entity_id
                ORDER BY m.timestamp DESC
                LIMIT :limit OFFSET :offset
            """)
            
            logger.debug(f"Executing query for mentions with params: entity_id={entity_id}, limit={limit}, offset={offset}")
            mentions = await self.session.execute(
                query,
                {"entity_id": entity_id, "limit": limit, "offset": offset}
            )
            
            results = [dict(m) for m in mentions]
            logger.debug(f"Found {len(results)} mentions for entity '{entity_name}'")
            
            if not results:
                logger.debug("No mentions found - verifying entity mentions table has entries...")
                # Debug query to check if we have any mentions at all
                count_query = text("""
                    SELECT COUNT(*) FROM entity_mentions WHERE entity_id = :entity_id
                """)
                count_result = await self.session.execute(count_query, {"entity_id": entity_id})
                total_mentions = count_result.scalar()
                logger.debug(f"Total mentions in database for entity: {total_mentions}")
                
                # Debug query to check the documents table join
                doc_query = text("""
                    SELECT COUNT(*) 
                    FROM entity_mentions m 
                    LEFT JOIN documents d ON m.document_id = d.document_id 
                    WHERE m.entity_id = :entity_id
                """)
                doc_result = await self.session.execute(doc_query, {"entity_id": entity_id})
                joined_mentions = doc_result.scalar()
                logger.debug(f"Mentions with successful document join: {joined_mentions}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting entity mentions: {str(e)}")
            logger.exception("Full traceback:")
            raise
    
    async def _get_entity_id(self, entity_name: str) -> uuid.UUID:
        """Get entity ID from name"""
        result = await self.session.execute(
            text("""
            SELECT entity_id FROM tracked_entities
            WHERE name = :name
            """),
            {"name": entity_name.lower()}
        )
        entity_id = result.scalar_one_or_none()
        if not entity_id:
            raise ValueError(f"Entity not found: {entity_name}")
        return entity_id

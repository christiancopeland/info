from typing import List, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import logging
import uuid
import os
from datetime import datetime
from pathlib import Path


from ..models.entities import TrackedEntity, EntityMention
from ..models.news_article import NewsArticle
from ..models.project import Document


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
        """Add a new entity to track and scan existing documents"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = f"entity_add_{timestamp}.log"
        
        try:
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(f"Adding new entity: {name}\n")
                f.write("=" * 80 + "\n\n")
                
                # Create the entity
                entity = TrackedEntity(
                    name=name,
                    name_lower=name.lower(),
                    entity_type=entity_type,
                    entity_metadata=metadata or {},
                    user_id=user_id
                )
                self.session.add(entity)
                await self.session.commit()
                await self.session.refresh(entity)
                
                # Add to active entities cache
                self.active_entities.add(name.lower())
                
                # Get all documents
                query = text("""
                    SELECT d.document_id, d.raw_content, d.filename
                    FROM documents d
                    JOIN project_folders f ON d.folder_id = f.folder_id
                    JOIN research_projects p ON f.project_id = p.project_id
                    WHERE d.raw_content IS NOT NULL
                    AND p.owner_id = :user_id
                """)
                
                result = await self.session.execute(query, {"user_id": user_id})
                documents = result.fetchall()
                
                mentions_added = 0
                for doc in documents:
                    content = doc.raw_content
                    if not content:
                        continue
                    
                    f.write(f"\nScanning document: {doc.filename}\n")
                    content_lower = content.lower()
                    entity_lower = name.lower()
                    occurrences = content_lower.count(entity_lower)
                    
                    if occurrences > 0:
                        f.write(f"Found {occurrences} occurrences\n")
                        
                        # Find each occurrence
                        pos = 0
                        while True:
                            pos = content_lower.find(entity_lower, pos)
                            if pos == -1:
                                break
                                
                            # Extract context
                            context_start = max(0, pos - 100)
                            context_end = min(len(content), pos + len(name) + 100)
                            context = content[context_start:context_end].strip()
                            
                            # Create mention
                            mention = EntityMention(
                                entity_id=entity.entity_id,
                                document_id=doc.document_id,
                                user_id=user_id,
                                context=context,
                                chunk_id=f"{doc.document_id}_0"
                            )
                            self.session.add(mention)
                            mentions_added += 1
                            f.write(f"\nMention #{mentions_added}:\n{context}\n")
                            
                            # Move to next occurrence
                            pos += 1
                        
                        await self.session.flush()
                
                await self.session.commit()
                
                # Verify mentions were added
                verify_query = text("SELECT COUNT(*) FROM entity_mentions WHERE entity_id = :entity_id")
                result = await self.session.execute(verify_query, {"entity_id": entity.entity_id})
                total_mentions = result.scalar()
                
                f.write(f"\nTotal mentions added: {mentions_added}\n")
                f.write(f"Total mentions in database: {total_mentions}\n")
                
                logger.info(f"Added new tracked entity: {name} ({entity_type})")
                logger.info(f"Debug log written to: {debug_file}")
                
                return entity
                
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error adding tracked entity: {str(e)}")
            raise

    async def _scan_existing_documents(self, entity: TrackedEntity):
        """Scan existing documents for entity mentions"""
        try:
            # Simple debug file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = f"entity_scan_{timestamp}.log"
            
            logger.debug(f"Writing debug log to: {debug_file}")
            
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(f"Entity Scan Debug Log for: {entity.name}\n")
                f.write("=" * 80 + "\n\n")
                
                # Get all documents for this user's projects
                query = text("""
                    SELECT d.document_id, d.raw_content, d.folder_id, d.filename
                    FROM documents d
                    JOIN project_folders f ON d.folder_id = f.folder_id
                    JOIN research_projects p ON f.project_id = p.project_id
                    WHERE d.raw_content IS NOT NULL
                    AND p.owner_id = :user_id
                """)
                
                result = await self.session.execute(query, {"user_id": entity.user_id})
                documents = result.fetchall()
                
                mentions_added = 0
                for doc in documents:
                    content = doc.raw_content
                    if not content:
                        continue
                    
                    # Write document info
                    f.write(f"\nDocument: {doc.filename}\n")
                    f.write(f"Content Length: {len(content)} chars\n")
                    f.write("-" * 80 + "\n\n")
                    f.write(content)
                    f.write("\n" + "-" * 80 + "\n")
                    
                    # Count occurrences
                    content_lower = content.lower()
                    entity_lower = entity.name.lower()
                    total_occurrences = content_lower.count(entity_lower)
                    
                    f.write(f"\nFound {total_occurrences} occurrences of '{entity.name}'\n")
                    
                    if total_occurrences > 0:
                        contexts = self._extract_context(content, entity.name)
                        f.write(f"\nExtracted {len(contexts)} contexts:\n")
                        
                        for i, context in enumerate(contexts, 1):
                            f.write(f"\nContext #{i}:\n{context}\n")
                            
                            mention = EntityMention(
                                entity_id=entity.entity_id,
                                document_id=doc.document_id,
                                user_id=entity.user_id,
                                context=context,
                                chunk_id=f"{doc.document_id}_0"
                            )
                            self.session.add(mention)
                            mentions_added += 1
                
                await self.session.commit()
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"Total mentions added: {mentions_added}\n")
            
            logger.info(f"Debug log written to: {debug_file}")
            return mentions_added
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error scanning existing documents: {str(e)}")
            raise

    def _extract_context(self, content: str, entity_name: str, context_window: int = 100) -> List[str]:
        """Extract all contexts around entity mentions"""
        content_lower = content.lower()
        entity_lower = entity_name.lower()
        contexts = []
        
        # Debug logging
        logger.debug(f"Extracting contexts for '{entity_name}' in content of length {len(content)}")
        
        # First, count total occurrences for verification
        total_occurrences = content_lower.count(entity_lower)
        logger.debug(f"Total occurrences of '{entity_name}' in text: {total_occurrences}")
        
        # Find all occurrences of the entity
        start_pos = 0
        found_count = 0
        
        while True:
            pos = content_lower.find(entity_lower, start_pos)
            if pos == -1:  # No more occurrences
                break
            
            found_count += 1
            # Calculate context window
            context_start = max(0, pos - context_window)
            context_end = min(len(content), pos + len(entity_name) + context_window)
            
            # Extract and clean context
            context = content[context_start:context_end].strip()
            
            # Debug logging
            logger.debug(f"Found mention {found_count}/{total_occurrences} at position {pos}")
            logger.debug(f"Context: {context[:50]}...")
            
            contexts.append(context)
            
            # Move start position to just after the current match
            start_pos = pos + 1  # Changed from pos + len(entity_name) to ensure we don't miss overlapping matches
        
        # Verify we found all occurrences
        logger.debug(f"Found {found_count} mentions, extracted {len(contexts)} contexts")
        if found_count != total_occurrences:
            logger.warning(f"Mismatch between found mentions ({found_count}) and total occurrences ({total_occurrences})")
        
        return contexts

    async def scan_document_for_entities(
        self,
        document_id: uuid.UUID,
        content: str
    ) -> List[Dict]:
        """Scan document content for tracked entities"""
        mentions = []
        
        try:
            # First scan the entire document for each entity
            for entity_name in self.active_entities:
                if entity_name.lower() in content.lower():
                    # Get entity details including user_id
                    entity_id = await self._get_entity_id(entity_name)
                    entity = await self.session.execute(
                        select(TrackedEntity).where(TrackedEntity.entity_id == entity_id)
                    )
                    entity = entity.scalar_one()
                    
                    # Get all contexts from the full document
                    contexts = self._extract_context(content, entity_name)
                    
                    # Create mention for each context found
                    for context in contexts:
                        mention = EntityMention(
                            entity_id=entity.entity_id,
                            document_id=document_id,
                            user_id=entity.user_id,
                            context=context,
                            chunk_id=f"{document_id}_0"  # Single chunk since we're scanning whole document
                        )
                        self.session.add(mention)
                        mentions.append(mention)
            
            await self.session.commit()
            logger.info(f"Found {len(mentions)} entity mentions in document {document_id}")
            
            # Log each context for debugging
            for mention in mentions:
                logger.debug(f"Found mention context: {mention.context[:100]}...")
            
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
            # Create debug log
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = f"entity_mentions_{timestamp}.log"
            
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(f"Entity Mentions Debug Log for: {entity_name}\n")
                f.write("=" * 80 + "\n\n")
                
                entity_id = await self._get_entity_id(entity_name)
                f.write(f"Found entity_id: {entity_id}\n\n")
                
                # First, get total count for debugging
                count_query = text("SELECT COUNT(*) FROM entity_mentions WHERE entity_id = :entity_id")
                count_result = await self.session.execute(count_query, {"entity_id": entity_id})
                total_mentions = count_result.scalar()
                f.write(f"Total mentions in database: {total_mentions}\n\n")
                
                # Get document content for verification
                doc_query = text("""
                    SELECT DISTINCT d.document_id, d.raw_content, d.filename
                    FROM documents d
                    JOIN entity_mentions m ON d.document_id = m.document_id
                    WHERE m.entity_id = :entity_id
                """)
                doc_result = await self.session.execute(doc_query, {"entity_id": entity_id})
                documents = doc_result.fetchall()
                
                f.write(f"Found {len(documents)} documents with mentions:\n")
                for doc in documents:
                    f.write(f"\nDocument: {doc.filename}\n")
                    f.write(f"Content Length: {len(doc.raw_content)} chars\n")
                    f.write("-" * 80 + "\n")
                    f.write(doc.raw_content)
                    f.write("\n" + "-" * 80 + "\n")
                    
                    # Count actual occurrences in content
                    content_lower = doc.raw_content.lower()
                    entity_lower = entity_name.lower()
                    total_occurrences = content_lower.count(entity_lower)
                    f.write(f"\nActual occurrences in document: {total_occurrences}\n")
                
                # Get mentions
                query = text("""
                    SELECT 
                        m.context, 
                        m.timestamp, 
                        d.filename,
                        d.document_id,
                        f.project_id
                    FROM entity_mentions m
                    JOIN documents d ON m.document_id = d.document_id
                    JOIN project_folders f ON d.folder_id = f.folder_id
                    WHERE m.entity_id = :entity_id
                    ORDER BY m.timestamp DESC
                    LIMIT :limit OFFSET :offset
                """)
                
                result = await self.session.execute(
                    query,
                    {"entity_id": entity_id, "limit": limit, "offset": offset}
                )
                
                results = [{
                    "context": row.context,
                    "timestamp": row.timestamp,
                    "filename": row.filename,
                    "document_id": str(row.document_id),
                    "project_id": str(row.project_id)
                } for row in result]
                
                f.write(f"\nReturning {len(results)} mentions\n")
                for i, mention in enumerate(results, 1):
                    f.write(f"\nMention #{i}:\n")
                    f.write(f"File: {mention['filename']}\n")
                    f.write(f"Context: {mention['context']}\n")
                
                logger.info(f"Debug log written to: {debug_file}")
                return results
                
        except Exception as e:
            logger.error(f"Error getting entity mentions: {str(e)}")
            logger.exception("Full traceback:")
            raise
    
    async def _get_entity_id(self, entity_name: str) -> uuid.UUID:
        """Get entity ID from name using fuzzy matching"""
        result = await self.session.execute(
            text("""
            SELECT entity_id, name 
            FROM tracked_entities
            WHERE name_lower = :exact_match
               OR similarity(name_lower, :fuzzy_match) > 0.3
            ORDER BY 
                CASE WHEN name_lower = :exact_match THEN 1
                     ELSE 2 
                END,
                similarity(name_lower, :fuzzy_match) DESC
            LIMIT 1
            """),
            {
                "exact_match": entity_name.lower(),
                "fuzzy_match": entity_name.lower()
            }
        )
        entity = result.first()
        if not entity:
            raise ValueError(f"Entity not found: {entity_name}")
        
        if entity.name.lower() != entity_name.lower():
            logger.info(f"Fuzzy matched '{entity_name}' to existing entity '{entity.name}'")
        
        return entity.entity_id

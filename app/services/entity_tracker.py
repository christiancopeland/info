from typing import List, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import logging
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
import networkx as nx


from ..models.entities import TrackedEntity, EntityMention
from ..models.news_article import NewsArticle
from ..models.project import Document


logger = logging.getLogger(__name__)

class EntityTrackingService:
    """Service for tracking and analyzing entities across documents"""
    
    def __init__(self, session: AsyncSession, document_processor, user_id: uuid.UUID = None, debug: bool = False):
        self.session = session
        self.document_processor = document_processor
        self.user_id = user_id
        self.active_entities: Set[str] = set()  # Cache of currently tracked entities
        self.entity_graph = nx.Graph()
        self.debug = debug
        self.debug_file = None

    def _init_debug_file(self, entity_name: str) -> None:
        """Initialize debug file if debug mode is enabled"""
        if self.debug:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_dir = "debug_logs"
            os.makedirs(debug_dir, exist_ok=True)
            self.debug_file = f"{debug_dir}/relationship_analysis_{entity_name}_{timestamp}.log"
            
            with open(self.debug_file, "w", encoding="utf-8") as f:
                f.write(f"Relationship Analysis Debug Log\n")
                f.write(f"Entity: {entity_name}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write("=" * 80 + "\n\n")

    def _write_debug(self, message: str) -> None:
        """Write debug message to both logger and file if enabled"""
        logger.debug(message)
        if self.debug and self.debug_file:
            with open(self.debug_file, "a", encoding="utf-8") as f:
                f.write(f"{message}\n")
    
    async def add_tracked_entity(
        self,
        name: str,
        entity_type: str = "CUSTOM",
        metadata: Optional[Dict] = None,
        user_id: uuid.UUID = None
    ) -> TrackedEntity:
        """Add a new entity to track and scan existing documents and news articles"""
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
                
                # Get all documents and news articles
                doc_query = text("""
                    SELECT d.document_id, d.raw_content, d.filename
                    FROM documents d
                    JOIN project_folders f ON d.folder_id = f.folder_id
                    JOIN research_projects p ON f.project_id = p.project_id
                    WHERE d.raw_content IS NOT NULL
                    AND p.owner_id = :user_id
                """)

                news_query = text("""
                    SELECT id as document_id, content as raw_content, title as filename
                    FROM news_articles
                    WHERE content IS NOT NULL
                """)

                doc_result = await self.session.execute(doc_query, {"user_id": user_id})
                news_result = await self.session.execute(news_query)

                documents = doc_result.fetchall()
                news_articles = news_result.fetchall()

                # Process both documents and news articles
                mentions_added = 0
                for doc in documents + news_articles:
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

    async def _scan_existing_documents(self, entity: TrackedEntity) -> int:
        """Scan existing documents and news articles for entity mentions"""
        mentions_added = 0
        
        try:
            # Scan news articles
            news_query = text("""
                SELECT id as source_id, content as raw_content
                FROM news_articles
                WHERE content IS NOT NULL
            """)
            
            news_result = await self.session.execute(news_query)
            news_articles = news_result.fetchall()
            
            for article in news_articles:
                mentions = await self._find_mentions_in_text(
                    entity.name,
                    article.raw_content,
                    article.source_id
                )
                for context, chunk_id in mentions:
                    await self.add_mention(
                        entity_id=entity.entity_id,
                        source_id=article.source_id,
                        is_news_article=True,
                        context=context,
                        chunk_id=chunk_id
                    )
                    mentions_added += 1
            
            # Scan documents (if you have any)
            doc_query = text("""
                SELECT document_id as source_id, raw_content
                FROM documents
                WHERE raw_content IS NOT NULL
            """)
            
            doc_result = await self.session.execute(doc_query)
            documents = doc_result.fetchall()
            
            for doc in documents:
                mentions = await self._find_mentions_in_text(
                    entity.name,
                    doc.raw_content,
                    doc.source_id
                )
                for context, chunk_id in mentions:
                    await self.add_mention(
                        entity_id=entity.entity_id,
                        source_id=doc.source_id,
                        is_news_article=False,
                        context=context,
                        chunk_id=chunk_id
                    )
                    mentions_added += 1
            
            await self.session.commit()
            return mentions_added
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error scanning documents: {str(e)}")
            raise

    async def add_mention(self, entity_id: uuid.UUID, source_id: uuid.UUID, is_news_article: bool, context: str, chunk_id: str = None):
        """Add a mention of an entity"""
        try:
            mention_id = uuid.uuid4()
            current_time = str(datetime.now(timezone.utc))  # Simple str() cast
            
            # Set the appropriate source ID field
            document_id = None
            news_article_id = None
            if is_news_article:
                news_article_id = source_id
            else:
                document_id = source_id

            query = text("""
                INSERT INTO entity_mentions 
                (mention_id, entity_id, document_id, news_article_id, user_id, chunk_id, context, timestamp)
                VALUES (:mention_id, :entity_id, :document_id, :news_article_id, :user_id, :chunk_id, :context, :timestamp)
            """)
            
            await self.session.execute(
                query,
                {
                    "mention_id": mention_id,
                    "entity_id": entity_id,
                    "document_id": document_id,
                    "news_article_id": news_article_id,
                    "user_id": self.user_id,
                    "chunk_id": chunk_id,
                    "context": context,
                    "timestamp": current_time
                }
            )
            
            return mention_id
        except Exception as e:
            logger.error(f"Error adding mention: {str(e)}")
            raise

    def _extract_context(self, text: str, term: str, case_sensitive: bool = True, context_chars: int = 200) -> List[str]:
        """Extract context around each occurrence of a term in text"""
        contexts = []
        if not case_sensitive:
            search_text = text.lower()
            search_term = term.lower()
        else:
            search_text = text
            search_term = term
        
        start = 0
        while True:
            pos = search_text.find(search_term, start)
            if pos == -1:
                break
            
            # Get context window
            context_start = max(0, pos - context_chars)
            context_end = min(len(text), pos + len(term) + context_chars)
            
            # Get the actual text from the original (preserving case)
            context = text[context_start:context_end].strip()
            
            # Add ellipsis if context is truncated
            if context_start > 0:
                context = "..." + context
            if context_end < len(text):
                context = context + "..."
            
            contexts.append(context)
            start = pos + len(search_term)
        
        return contexts

    async def scan_document_for_entities(
        self,
        document_id: uuid.UUID,
        content: str
    ) -> List[Dict]:
        """Scan document content for tracked entities"""
        mentions = []
        
        try:
            # Debug logging
            logger.debug(f"Scanning document {document_id}")
            logger.debug(f"Content length: {len(content) if content else 0}")
            logger.debug(f"Active entities: {self.active_entities}")
            
            # First scan the entire document for each entity
            for entity_name in self.active_entities:
                entity_lower = entity_name.lower()
                content_lower = content.lower() if content else ""
                
                # Debug logging
                count = content_lower.count(entity_lower)
                logger.debug(f"Found {count} occurrences of '{entity_name}' in document")
                
                if entity_lower in content_lower:
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
        """Get recent mentions of an entity from both documents and news articles"""
        try:
            entity_id = await self._get_entity_id(entity_name)
            
            # Updated query to handle both document and news article mentions
            query = text("""
                WITH document_mentions AS (
                    SELECT 
                        m.context,
                        m.timestamp,
                        d.filename,
                        m.document_id::text as document_id,
                        NULL::text as news_article_id,
                        p.project_id::text as project_id,
                        'document' as source_type
                    FROM entity_mentions m
                    JOIN documents d ON d.document_id = m.document_id
                    JOIN project_folders f ON d.folder_id = f.folder_id
                    JOIN research_projects p ON f.project_id = p.project_id
                    WHERE m.entity_id = :entity_id
                    AND m.document_id IS NOT NULL
                ),
                news_mentions AS (
                    SELECT 
                        m.context,
                        m.timestamp,
                        na.title as filename,
                        NULL::text as document_id,
                        m.news_article_id::text as news_article_id,
                        NULL::text as project_id,
                        'news' as source_type
                    FROM entity_mentions m
                    JOIN news_articles na ON na.id = m.news_article_id
                    WHERE m.entity_id = :entity_id
                    AND m.news_article_id IS NOT NULL
                )
                SELECT * FROM (
                    SELECT * FROM document_mentions
                    UNION ALL
                    SELECT * FROM news_mentions
                ) combined
                ORDER BY timestamp DESC
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
                "document_id": row.document_id,
                "news_article_id": row.news_article_id,
                "project_id": row.project_id,
                "source_type": row.source_type
            } for row in result]
            
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

    async def analyze_entity_relationships(self, entity_name: str) -> Dict:
        """Analyze relationships for a specific entity"""
        self._init_debug_file(entity_name)
        self._write_debug(f"Starting relationship analysis for: {entity_name}")
        
        try:
            # First check for mentions
            mention_check = await self.session.execute(
                text("""
                    SELECT COUNT(*) as mention_count
                    FROM entity_mentions em
                    JOIN tracked_entities te ON em.entity_id = te.entity_id
                    WHERE te.name_lower = :entity_name
                """),
                {"entity_name": entity_name.lower()}
            )
            mention_count = mention_check.scalar()
            self._write_debug(f"Found {mention_count} mentions for {entity_name}")

            if mention_count == 0:
                self._write_debug(f"No mentions found for entity: {entity_name}")
                return {"nodes": [], "edges": [], "central_entities": []}

            # Updated query to ensure truly unique contexts
            related_query = text("""
                WITH base_mentions AS (
                    SELECT em.*, te.name_lower
                    FROM entity_mentions em
                    JOIN tracked_entities te ON em.entity_id = te.entity_id
                    WHERE te.name_lower = :entity_name
                ),
                shared_contexts AS (
                    -- First get unique contexts where entities appear together
                    SELECT DISTINCT
                        te2.name,
                        te2.entity_id,
                        bm.context
                    FROM base_mentions bm
                    JOIN entity_mentions em2 ON 
                        (bm.document_id = em2.document_id OR bm.news_article_id = em2.news_article_id)
                        AND (
                            bm.chunk_id = em2.chunk_id  -- Exact chunk match
                            OR (  -- Adjacent chunk match
                                SPLIT_PART(bm.chunk_id, '_', 1) = SPLIT_PART(em2.chunk_id, '_', 1)
                                AND ABS(
                                    CAST(NULLIF(SPLIT_PART(bm.chunk_id, '_', 2), '') AS INTEGER) - 
                                    CAST(NULLIF(SPLIT_PART(em2.chunk_id, '_', 2), '') AS INTEGER)
                                ) <= 1
                            )
                        )
                    JOIN tracked_entities te2 ON em2.entity_id = te2.entity_id
                    WHERE te2.name_lower != :entity_name
                    AND bm.context IS NOT NULL
                ),
                related_mentions AS (
                    SELECT 
                        name,
                        entity_id,
                        COUNT(DISTINCT context) as shared_docs,
                        COUNT(*) as total_mentions,
                        SUM(CASE 
                            WHEN context IS NOT NULL THEN 3  -- Weight for each unique context
                            ELSE 1
                        END) as relationship_strength,
                        array_agg(DISTINCT context) as contexts
                    FROM shared_contexts
                    GROUP BY name, entity_id
                    HAVING COUNT(DISTINCT context) > 0
                )
                SELECT * FROM related_mentions
                ORDER BY relationship_strength DESC, shared_docs DESC
            """)
            
            self._write_debug("Executing related entities query")
            result = await self.session.execute(
                related_query,
                {"entity_name": entity_name.lower()}
            )
            
            entities = [{
                "name": row.name,
                "shared_docs": row.shared_docs,
                "total_mentions": row.total_mentions,
                "relationship_strength": float(row.relationship_strength),
                "contexts": row.contexts if row.contexts else []
            } for row in result]
            
            self._write_debug(f"Found {len(entities)} related entities")

            # Build network response
            nodes = [{"id": entity_name, "group": 1}]  # Central node
            edges = []
            central_entities = []  # Format: [entity_name, normalized_strength]

            # Find max relationship strength for normalization
            max_strength = max((e["relationship_strength"] for e in entities), default=1)

            for entity in entities:
                nodes.append({
                    "id": entity["name"],
                    "group": 2
                })
                
                normalized_strength = entity["relationship_strength"] / max_strength
                
                edges.append({
                    "source": entity_name,
                    "target": entity["name"],
                    "value": normalized_strength,
                    "weight": normalized_strength,  # Frontend expects 'weight'
                    "contexts": [{"context": ctx} for ctx in entity["contexts"][:5]]  # Limit to top 5 contexts
                })
                
                # Add to central_entities as [name, score] pairs
                central_entities.append([
                    entity["name"],
                    normalized_strength
                ])

            return {
                "nodes": nodes,
                "edges": edges,
                "central_entities": central_entities
            }
            
        except Exception as e:
            self._write_debug(f"Error in relationship analysis: {str(e)}")
            raise

    async def _find_related_entities_in_docs(self, entity_name: str) -> List[str]:
        """Find entities that appear in the same documents"""
        self._write_debug(f"Finding related entities for: {entity_name}")
        try:
            # First, verify the entity exists and get its ID
            entity_check_query = text("""
                SELECT entity_id, name 
                FROM tracked_entities 
                WHERE name_lower = :entity_name
            """)
            result = await self.session.execute(
                entity_check_query,
                {"entity_name": entity_name.lower()}
            )
            entity = result.first()
            self._write_debug(f"Found entity record: {entity}")

            # Check if we have any mentions for this entity
            mentions_check_query = text("""
                SELECT COUNT(*) as mention_count, 
                       COUNT(DISTINCT document_id) as doc_count
                FROM entity_mentions
                WHERE entity_id = :entity_id
            """)
            result = await self.session.execute(
                mentions_check_query,
                {"entity_id": entity.entity_id if entity else None}
            )
            mention_stats = result.first()
            self._write_debug(f"Entity mention stats: {mention_stats}")

            # Now proceed with finding related entities
            query = text("""
                WITH entity_documents AS (
                    SELECT DISTINCT document_id 
                    FROM entity_mentions 
                    WHERE entity_id = (
                        SELECT entity_id 
                        FROM tracked_entities 
                        WHERE name_lower = :entity_name
                    )
                )
                SELECT DISTINCT te.name, te.entity_id,
                       COUNT(DISTINCT em.document_id) as shared_docs
                FROM entity_mentions em
                JOIN tracked_entities te ON em.entity_id = te.entity_id
                WHERE em.document_id IN (SELECT document_id FROM entity_documents)
                AND te.name_lower != :entity_name
                GROUP BY te.name, te.entity_id
            """)
            
            self._write_debug("Executing related entities query")
            result = await self.session.execute(
                query,
                {"entity_name": entity_name.lower()}
            )
            
            entities = [{"name": row.name, "shared_docs": row.shared_docs} for row in result]
            self._write_debug(f"Found {len(entities)} related entities")
            self._write_debug(f"Related entities with stats: {entities}")
            
            return [e["name"] for e in entities]
            
        except Exception as e:
            self._write_debug(f"Error finding related entities: {str(e)}")
            raise

    async def _find_related_entities_in_news(self, entity_name: str) -> List[str]:
        """Find entities that appear in the same news articles"""
        self._write_debug(f"Finding related entities in news articles for: {entity_name}")
        try:
            # Debug current entity mentions
            debug_query = text("""
                SELECT em.*, na.content, na.title
                FROM entity_mentions em
                JOIN tracked_entities te ON em.entity_id = te.entity_id
                JOIN news_articles na ON em.news_article_id = na.id
                WHERE te.name_lower = :entity_name
            """)
            debug_result = await self.session.execute(
                debug_query,
                {"entity_name": entity_name.lower()}
            )
            self._write_debug(f"Debug: Found mentions for {entity_name}:")
            for row in debug_result:
                self._write_debug(f"Article: {row.title}")
                self._write_debug(f"Context: {row.context}")

            # Enhanced query to find related entities
            query = text("""
                WITH target_mentions AS (
                    -- Get all news articles and chunks where target entity appears
                    SELECT 
                        em.news_article_id,
                        em.chunk_id,
                        na.content,
                        COUNT(*) as mention_count
                    FROM entity_mentions em
                    JOIN tracked_entities te ON em.entity_id = te.entity_id
                    JOIN news_articles na ON em.news_article_id = na.id
                    WHERE te.name_lower = :entity_name
                    GROUP BY em.news_article_id, em.chunk_id, na.content
                )
                SELECT 
                    te2.name,
                    te2.entity_id,
                    COUNT(DISTINCT em2.news_article_id) as shared_articles,
                    COUNT(*) as total_mentions,
                    SUM(CASE 
                        WHEN em2.chunk_id = tm.chunk_id THEN 3  -- Same chunk: strongest relationship
                        WHEN ABS(
                            CAST(SPLIT_PART(em2.chunk_id, '_', 2) AS INTEGER) - 
                            CAST(SPLIT_PART(tm.chunk_id, '_', 2) AS INTEGER)
                        ) <= 1 THEN 2  -- Adjacent chunks: strong relationship
                        ELSE 1  -- Same article: basic relationship
                    END) as relationship_strength
                FROM target_mentions tm
                JOIN entity_mentions em2 ON em2.news_article_id = tm.news_article_id
                JOIN tracked_entities te2 ON em2.entity_id = te2.entity_id
                WHERE 
                    te2.name_lower != :entity_name
                    AND em2.news_article_id IS NOT NULL
                GROUP BY te2.name, te2.entity_id
                HAVING COUNT(DISTINCT em2.news_article_id) > 0
                ORDER BY relationship_strength DESC, shared_articles DESC
            """)
            
            self._write_debug("Executing enhanced related entities query")
            result = await self.session.execute(
                query,
                {"entity_name": entity_name.lower()}
            )
            
            entities = [{
                "name": row.name,
                "shared_articles": row.shared_articles,
                "total_mentions": row.total_mentions,
                "relationship_strength": float(row.relationship_strength)
            } for row in result]
            
            self._write_debug(f"Found {len(entities)} related entities")
            for entity in entities:
                self._write_debug(f"Related entity: {entity['name']}")
                self._write_debug(f"  Shared articles: {entity['shared_articles']}")
                self._write_debug(f"  Total mentions: {entity['total_mentions']}")
                self._write_debug(f"  Relationship strength: {entity['relationship_strength']}")
            
            return [e["name"] for e in entities]
            
        except Exception as e:
            self._write_debug(f"Error finding related entities in news: {str(e)}")
            raise

    async def _get_cooccurrence_contexts(
        self,
        entity1: str,
        entity2: str
    ) -> List[Dict]:
        """Get contexts where two entities co-occur in both documents and news articles"""
        try:
            # First, let's debug the mentions for each entity
            debug_query = text("""
                SELECT 
                    entity_id,
                    document_id,
                    news_article_id,
                    chunk_id,
                    context
                FROM entity_mentions
                WHERE entity_id IN (
                    SELECT entity_id FROM tracked_entities 
                    WHERE name_lower IN (:entity1_name, :entity2_name)
                )
            """)
            
            debug_result = await self.session.execute(
                debug_query,
                {
                    "entity1_name": entity1.lower(),
                    "entity2_name": entity2.lower()
                }
            )
            
            self._write_debug(f"\nDebug mentions for {entity1} and {entity2}:")
            for row in debug_result:
                self._write_debug(f"Entity: {row.entity_id}, Doc: {row.document_id}, News: {row.news_article_id}, Chunk: {row.chunk_id}")

            query = text("""
                WITH entity1_mentions AS (
                    SELECT 
                        document_id,
                        news_article_id,
                        context,
                        chunk_id
                    FROM entity_mentions
                    WHERE entity_id = (
                        SELECT entity_id FROM tracked_entities 
                        WHERE name_lower = :entity1_name
                    )
                ),
                entity2_mentions AS (
                    SELECT 
                        document_id,
                        news_article_id,
                        context,
                        chunk_id
                    FROM entity_mentions
                    WHERE entity_id = (
                        SELECT entity_id FROM tracked_entities 
                        WHERE name_lower = :entity2_name
                    )
                )
                SELECT 
                    COALESCE(e1.document_id, e1.news_article_id) as source_id,
                    e1.context as context1,
                    e2.context as context2,
                    COALESCE(d.filename, n.title) as filename,
                    CASE 
                        WHEN e1.document_id IS NOT NULL THEN 'document'
                        ELSE 'news'
                    END as source_type,
                    e1.chunk_id as chunk1,
                    e2.chunk_id as chunk2
                FROM entity1_mentions e1
                JOIN entity2_mentions e2 
                    ON (
                        (e1.document_id IS NOT NULL AND e1.document_id = e2.document_id) OR
                        (e1.news_article_id IS NOT NULL AND e1.news_article_id = e2.news_article_id)
                    )
                    -- Relaxed chunk matching condition
                    AND (
                        e1.chunk_id = e2.chunk_id 
                        OR (
                            -- For documents that might have multiple chunks
                            SPLIT_PART(e1.chunk_id, '_', 1) = SPLIT_PART(e2.chunk_id, '_', 1)
                            AND ABS(
                                CAST(SPLIT_PART(e1.chunk_id, '_', 2) AS INTEGER) - 
                                CAST(SPLIT_PART(e2.chunk_id, '_', 2) AS INTEGER)
                            ) <= 1
                        )
                    )
                LEFT JOIN documents d ON e1.document_id = d.document_id
                LEFT JOIN news_articles n ON e1.news_article_id = n.id
                LIMIT 10
            """)
            
            self._write_debug("\nExecuting co-occurrence query")
            result = await self.session.execute(
                query,
                {
                    "entity1_name": entity1.lower(),
                    "entity2_name": entity2.lower()
                }
            )
            
            # Format contexts for better display
            contexts = []
            for row in result:
                # Clean and truncate the contexts
                context1 = ' '.join(row.context1.split())[:200]  # Clean whitespace and truncate
                context2 = ' '.join(row.context2.split())[:200]  # Clean whitespace and truncate
                
                contexts.append({
                    "document_id": str(row.source_id),
                    "context": f"...{context1}... and ...{context2}...",  # Combined context
                    "filename": row.filename,
                    "source_type": row.source_type,
                    "chunks": f"{row.chunk1} - {row.chunk2}"  # Add chunk info for debugging
                })
                self._write_debug(f"\nFound co-occurrence in chunks: {row.chunk1} - {row.chunk2}")
            
            self._write_debug(f"Found {len(contexts)} co-occurrence contexts")
            if contexts:
                self._write_debug(f"Sample context: {contexts[0]}")
            
            return contexts
            
        except Exception as e:
            self._write_debug(f"Error getting co-occurrence contexts: {str(e)}")
            raise

    async def _calculate_relationship_strength(
        self,
        entity1: str,
        entity2: str,
        contexts: List[Dict]
    ) -> float:
        """Calculate relationship strength based on multiple factors"""
        try:
            # Count co-occurrences and unique documents
            cooccurrence_count = len(contexts)
            unique_docs = len({ctx['document_id'] for ctx in contexts})
            
            # Get mention counts and document counts for each entity
            async def get_entity_stats(entity_name):
                result = await self.session.execute(
                    text("""
                        SELECT 
                            COUNT(*) as mention_count,
                            COUNT(DISTINCT document_id) as doc_count
                        FROM entity_mentions em
                        JOIN tracked_entities te ON em.entity_id = te.entity_id
                        WHERE te.name_lower = :entity_name
                    """),
                    {"entity_name": entity_name.lower()}
                )
                return result.first()
            
            entity1_stats = await get_entity_stats(entity1)
            entity2_stats = await get_entity_stats(entity2)
            
            # Calculate Jaccard similarity of document sets
            jaccard = unique_docs / (
                entity1_stats.doc_count + 
                entity2_stats.doc_count - 
                unique_docs
            ) if (entity1_stats.doc_count + entity2_stats.doc_count - unique_docs) > 0 else 0
            
            # Calculate normalized co-occurrence score
            # Consider both document-level and mention-level frequencies
            doc_frequency = unique_docs / max(entity1_stats.doc_count, entity2_stats.doc_count)
            mention_frequency = cooccurrence_count / min(
                entity1_stats.mention_count,
                entity2_stats.mention_count
            )
            
            # Combine scores with weights
            strength = (
                (jaccard * 0.3) +               # Document overlap
                (doc_frequency * 0.3) +         # Document frequency
                (mention_frequency * 0.4)       # Mention frequency
            )
            
            self._write_debug(f"""
                Relationship strength calculation for {entity1} - {entity2}:
                - Co-occurrences: {cooccurrence_count}
                - Unique documents: {unique_docs}
                - Entity1 docs: {entity1_stats.doc_count} ({entity1_stats.mention_count} mentions)
                - Entity2 docs: {entity2_stats.doc_count} ({entity2_stats.mention_count} mentions)
                - Jaccard similarity: {jaccard:.3f}
                - Document frequency: {doc_frequency:.3f}
                - Mention frequency: {mention_frequency:.3f}
                - Final strength: {strength:.3f}
            """)
            
            return strength
            
        except Exception as e:
            self._write_debug(f"Error calculating relationship strength: {str(e)}")
            raise

    async def _get_entity_network(
        self,
        entity_name: str,
        depth: int = 2
    ) -> Dict:
        """Get network of related entities with their relationships"""
        if not self.entity_graph.has_node(entity_name):
            return {
                "nodes": [],
                "edges": [],
                "central_entities": []
            }
            
        # Get subgraph centered on entity
        neighbors = nx.single_source_shortest_path_length(
            self.entity_graph,
            entity_name,
            cutoff=depth
        )
        subgraph = self.entity_graph.subgraph(neighbors.keys())
        
        # Calculate node importance
        pagerank = nx.pagerank(subgraph, weight='weight')
        
        # Format for frontend visualization
        nodes = [{
            "id": node,
            "score": pagerank[node],
            "depth": neighbors[node]
        } for node in subgraph.nodes()]
        
        edges = [{
            "source": e[0],
            "target": e[1],
            "weight": subgraph.edges[e]['weight'],
            "contexts": subgraph.edges[e].get('contexts', [])
        } for e in subgraph.edges()]
        
        return {
            "nodes": nodes,
            "edges": edges,
            "central_entities": sorted(
                pagerank.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }

    async def _find_mentions_in_text(
        self,
        entity_name: str,
        text: str,
        source_id: uuid.UUID,
        context_chars: int = 100
    ) -> List[tuple[str, str]]:
        """Find mentions of an entity in text and return context snippets with chunk IDs"""
        if not text:
            return []
        
        mentions = []
        text_lower = text.lower()
        entity_lower = entity_name.lower()
        
        pos = 0
        while True:
            pos = text_lower.find(entity_lower, pos)
            if pos == -1:
                break
            
            # Extract context
            context_start = max(0, pos - context_chars)
            context_end = min(len(text), pos + len(entity_name) + context_chars)
            context = text[context_start:context_end].strip()
            
            # Add ellipsis if context is truncated
            if context_start > 0:
                context = "..." + context
            if context_end < len(text):
                context = context + "..."
            
            # Create chunk ID using source_id and position
            chunk_id = f"{source_id}_{pos}"
            
            mentions.append((context, chunk_id))
            pos += len(entity_name)
        
        return mentions

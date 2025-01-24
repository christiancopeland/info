from typing import List, Dict, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import logging
import uuid
import os
from datetime import datetime
from pathlib import Path
import networkx as nx


from ..models.entities import TrackedEntity, EntityMention
from ..models.news_article import NewsArticle
from ..models.project import Document


logger = logging.getLogger(__name__)

class EntityTrackingService:
    """Service for tracking and analyzing entities across documents"""
    
    def __init__(self, session: AsyncSession, document_processor, debug: bool = False):
        self.session = session
        self.document_processor = document_processor
        self.active_entities: Set[str] = set()  # Cache of currently tracked entities
        self.entity_graph = nx.Graph()
        self.debug = debug
        self.debug_file = None
    
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

    async def analyze_entity_relationships(self, entity_name: str) -> Dict:
        """Analyze relationships for a specific entity"""
        self._init_debug_file(entity_name)
        self._write_debug(f"Starting relationship analysis for: {entity_name}")
        
        try:
            # First check if we have mentions for this entity
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

            # Get related entities
            related_entities = await self._find_related_entities(entity_name)
            self._write_debug(f"Found {len(related_entities)} related entities: {related_entities}")
            
            # Build relationship graph
            self._write_debug("Building relationship graph")
            for related_entity in related_entities:
                self._write_debug(f"Analyzing relationship with: {related_entity}")
                
                contexts = await self._get_cooccurrence_contexts(
                    entity1=entity_name,
                    entity2=related_entity
                )
                
                if contexts:
                    strength = await self._calculate_relationship_strength(
                        entity1=entity_name,
                        entity2=related_entity,
                        contexts=contexts
                    )
                    
                    self.entity_graph.add_edge(
                        entity_name,
                        related_entity,
                        weight=strength,
                        contexts=contexts[:5]
                    )
                    self._write_debug(f"Added edge to graph: {entity_name} - {related_entity} (strength: {strength:.3f})")
            
            network = await self._get_entity_network(entity_name)
            self._write_debug(f"Network analysis complete. Nodes: {len(network['nodes'])}, Edges: {len(network['edges'])}")
            
            if self.debug:
                self._write_debug("\nFinal Network Data:")
                self._write_debug(f"Nodes: {network['nodes']}")
                self._write_debug(f"Edges: {network['edges']}")
                self._write_debug(f"Central entities: {network['central_entities']}")
                
                logger.info(f"Debug log written to: {self.debug_file}")
            
            return network
            
        except Exception as e:
            self._write_debug(f"Error in relationship analysis: {str(e)}")
            raise
            
    async def _find_related_entities(self, entity_name: str) -> List[str]:
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

    async def _get_cooccurrence_contexts(
        self,
        entity1: str,
        entity2: str
    ) -> List[Dict]:
        """Get contexts where two entities co-occur"""
        try:
            query = text("""
                WITH entity1_mentions AS (
                    SELECT document_id, context, chunk_id
                    FROM entity_mentions
                    WHERE entity_id = (
                        SELECT entity_id FROM tracked_entities 
                        WHERE name_lower = :entity1_name
                    )
                ),
                entity2_mentions AS (
                    SELECT document_id, context, chunk_id
                    FROM entity_mentions
                    WHERE entity_id = (
                        SELECT entity_id FROM tracked_entities 
                        WHERE name_lower = :entity2_name
                    )
                )
                SELECT 
                    e1.document_id as doc_id,
                    e1.context as context1,
                    e2.context as context2,
                    d.filename as filename
                FROM entity1_mentions e1
                JOIN entity2_mentions e2 
                    ON e1.document_id = e2.document_id 
                    AND e1.chunk_id = e2.chunk_id
                JOIN documents d ON e1.document_id = d.document_id
                LIMIT 10
            """)
            
            self._write_debug("Executing co-occurrence query")
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
                    "document_id": str(row.doc_id),
                    "context": f"...{context1}... and ...{context2}...",  # Combined context
                    "filename": row.filename
                })
            
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

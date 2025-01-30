from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from pydantic import BaseModel
from sqlalchemy import select, text
import logging

from ....database import get_db
from ....services.entity_tracker import EntityTrackingService
from ....services.document_processor import DocumentProcessor
from ....models.entities import TrackedEntity

router = APIRouter()
document_processor = DocumentProcessor()
logger = logging.getLogger(__name__)

class EntityTrackRequest(BaseModel):
    name: str
    entity_type: str = "CUSTOM"
    metadata: Optional[Dict] = None

# Add this class to represent the current user
class CurrentUser:
    def __init__(self, user_id: uuid.UUID):
        self.user_id = user_id

# Add this dependency to get the current user
# This is a temporary solution - you'll want to replace this with proper authentication
async def get_current_user():
    # TODO: Replace this with proper user authentication
    # For now, using a hardcoded user_id for testing
    return CurrentUser(user_id="aa5c38ff-7fb4-41d0-9fb3-ed2d67d3b4c3")


@router.post("/entities/track")
async def track_entity(
    entity: EntityTrackRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Add a new entity to track"""
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id
    )
    try:
        tracked_entity = await entity_tracker.add_tracked_entity(
            name=entity.name,
            entity_type=entity.entity_type,
            metadata=entity.metadata,
            user_id=current_user.user_id
        )
        return tracked_entity
    except Exception as e:
        logger.error(f"Error tracking entity: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
    
@router.delete("/entities/{entity_name}")
async def delete_entity(
    entity_name: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Delete a tracked entity"""
    try:
        # Find the entity
        query = select(TrackedEntity).where(
            TrackedEntity.name_lower == entity_name.lower(),
            TrackedEntity.user_id == current_user.user_id
        )
        result = await session.execute(query)
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise HTTPException(
                status_code=404,
                detail=f"Entity '{entity_name}' not found"
            )
        
        # Delete related mentions first (if your DB doesn't handle cascading deletes)
        delete_mentions = text("""
            DELETE FROM entity_mentions 
            WHERE entity_id = :entity_id
        """)
        await session.execute(delete_mentions, {"entity_id": entity.entity_id})
        
        # Delete the entity
        await session.delete(entity)
        await session.commit()
        
        return {"status": "success", "message": f"Entity '{entity_name}' deleted"}
        
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete entity: {str(e)}"
        )


@router.get("/entities/{entity_name}/mentions")
async def get_entity_mentions(
    entity_name: str,
    limit: int = 50,
    offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get mentions for an entity"""
    logger.debug(f"Getting mentions for entity: {entity_name}")
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id
    )
    try:
        mentions = await entity_tracker.get_entity_mentions(
            entity_name=entity_name,
            limit=limit,
            offset=offset
        )
        return mentions
    except Exception as e:
        logger.error(f"Error getting mentions for {entity_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("/entities")
async def get_tracked_entities(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = 100
) -> List[dict]:
    """
    Get tracked entities for the current user
    
    Args:
        limit: Maximum number of entities to return
    """
    try:
        query = (
            select(TrackedEntity)
            .where(TrackedEntity.user_id == current_user.user_id)
            .order_by(TrackedEntity.created_at.desc())
            .limit(limit)
        )
        
        result = await session.execute(query)
        entities = result.scalars().all()
        
        return [
            {
                "entity_id": str(entity.entity_id),
                "name": entity.name,
                "entity_type": entity.entity_type,
                "created_at": str(entity.created_at)  # Convert to string instead of calling isoformat()
            }
            for entity in entities
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tracked entities: {str(e)}"
        )

@router.get("/entities/{entity_name}/relationships")
async def get_entity_relationships(
    entity_name: str,
    include_news: bool = True,
    include_docs: bool = True,
    min_shared: int = 1,
    debug: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get relationship network for an entity"""
    logger.debug(f"Getting relationships for entity: {entity_name}")
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id,
        debug=debug
    )
    try:
        # First check if we have any mentions for this entity
        mentions_check = await session.execute(
            text("""
                SELECT COUNT(*) 
                FROM entity_mentions em
                JOIN tracked_entities te ON em.entity_id = te.entity_id
                WHERE te.name_lower = :entity_name
            """),
            {"entity_name": entity_name.lower()}
        )
        mention_count = mentions_check.scalar()
        
        if mention_count == 0:
            logger.debug(f"No mentions found for {entity_name}, triggering scan...")
            # Get entity details
            entity = await session.execute(
                select(TrackedEntity)
                .where(TrackedEntity.name_lower == entity_name.lower())
            )
            entity = entity.scalar_one()
            
            # Scan for mentions
            await entity_tracker._scan_existing_documents(entity)
        
        # Now analyze relationships
        network = await entity_tracker.analyze_entity_relationships(
            entity_name=entity_name
        )
        return network
        
    except Exception as e:
        logger.error(f"Error getting relationships for {entity_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/entities/{entity_name}/scan")
async def scan_entity_mentions(
    entity_name: str,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Manually trigger a scan for entity mentions"""
    logger.debug(f"Starting scan for entity: {entity_name}")
    entity_tracker = EntityTrackingService(
        session=session, 
        document_processor=document_processor,
        user_id=current_user.user_id
    )
    try:
        # Get entity details
        entity = await session.execute(
            select(TrackedEntity)
            .where(TrackedEntity.name_lower == entity_name.lower())
        )
        entity = entity.scalar_one()
        logger.debug(f"Found entity: {entity.name} (ID: {entity.entity_id})")
        
        # Scan for mentions
        mentions_added = await entity_tracker._scan_existing_documents(entity)
        
        return {
            "status": "success",
            "mentions_found": mentions_added,
            "message": f"Successfully scanned for mentions of '{entity_name}'"
        }
    except Exception as e:
        logger.error(f"Error scanning for {entity_name}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/entities/diagnostic")
async def diagnostic_check(
    session: AsyncSession = Depends(get_db)
):
    """Check database state for troubleshooting"""
    try:
        # Check news articles
        news_query = text("SELECT COUNT(*) as count, COUNT(CASE WHEN content IS NOT NULL THEN 1 END) as with_content FROM news_articles")
        news_result = await session.execute(news_query)
        news_stats = news_result.first()
        
        # Check tracked entities
        entity_query = text("SELECT COUNT(*) FROM tracked_entities")
        entity_result = await session.execute(entity_query)
        entity_count = entity_result.scalar()
        
        # Check mentions
        mention_query = text("SELECT COUNT(*) FROM entity_mentions")
        mention_result = await session.execute(mention_query)
        mention_count = mention_result.scalar()
        
        return {
            "news_articles": {
                "total": news_stats.count,
                "with_content": news_stats.with_content
            },
            "tracked_entities": entity_count,
            "entity_mentions": mention_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Diagnostic check failed: {str(e)}"
        )

@router.get("/entities/diagnostic/articles")
async def diagnostic_check_articles(
    limit: int = 5,
    session: AsyncSession = Depends(get_db)
):
    """Check sample of articles for troubleshooting"""
    try:
        # Get sample of articles with their content status
        article_query = text("""
            SELECT 
                id,
                title,
                url,
                scraped_at,
                CASE 
                    WHEN content IS NULL THEN 'missing'
                    WHEN content = '' THEN 'empty'
                    ELSE 'present'
                END as content_status,
                CASE 
                    WHEN content IS NOT NULL THEN length(content)
                    ELSE 0
                END as content_length
            FROM news_articles
            ORDER BY scraped_at DESC
            LIMIT :limit
        """)
        
        result = await session.execute(article_query, {"limit": limit})
        articles = result.fetchall()
        
        return {
            "articles": [
                {
                    "id": str(article.id),
                    "title": article.title,
                    "url": article.url,
                    "scraped_at": str(article.scraped_at),
                    "content_status": article.content_status,
                    "content_length": article.content_length
                }
                for article in articles
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Article diagnostic check failed: {str(e)}"
        )


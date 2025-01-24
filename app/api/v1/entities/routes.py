from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from pydantic import BaseModel
from sqlalchemy import select

from ....database import get_db
from ....services.entity_tracker import EntityTrackingService
from ....services.document_processor import DocumentProcessor
from ....models.entities import TrackedEntity

router = APIRouter()
document_processor = DocumentProcessor()

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
    request: EntityTrackRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    """Add a new entity to track"""
    entity_tracker = EntityTrackingService(session, document_processor)
    try:
        entity = await entity_tracker.add_tracked_entity(
            name=request.name,
            entity_type=request.entity_type,
            metadata=request.metadata,
            user_id=current_user.user_id  # Add the user_id parameter
        )
        return {
            "entity_id": str(entity.entity_id),
            "name": entity.name
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/entities/{entity_name}/mentions")
async def get_entity_mentions(
    entity_name: str,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db)
):
    """Get mentions for an entity"""
    entity_tracker = EntityTrackingService(session, document_processor)
    try:
        mentions = await entity_tracker.get_entity_mentions(
            entity_name=entity_name,
            limit=limit,
            offset=offset
        )
        
        # Format the mentions to match frontend expectations
        return [
            {
                "context": mention["context"],
                "filename": mention["filename"],
                "timestamp": str(mention["timestamp"])  # Ensure timestamp is a string
            }
            for mention in mentions
        ]
    except Exception as e:
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
    depth: int = 2,
    debug: bool = True,
    session: AsyncSession = Depends(get_db)
):
    """Get relationship network for an entity"""
    entity_tracker = EntityTrackingService(session, document_processor, debug=debug)
    try:
        network = await entity_tracker.analyze_entity_relationships(entity_name)
        return network
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

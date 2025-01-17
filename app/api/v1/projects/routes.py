# External imports
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Cookie, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from uuid import UUID
import magic
from sqlalchemy import select, delete
import redis
from datetime import datetime, timezone

# Internal imports
from ....database import get_db
from ....models.project import ResearchProject
from ....services.project_service import ProjectService
from ....services.document_processor import DocumentProcessor
from ....services.auth.security_service import SecurityService
from ....core.config import settings


# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


router = APIRouter()

# Initialize services
document_processor = DocumentProcessor()
project_service = ProjectService(document_processor)
security_service = SecurityService(settings.SECRET_KEY, settings.ALGORITHM)

# Initialize Redis client
redis_client = redis.Redis(host='localhost', port=6379, db=0)



@router.post("/projects")
async def create_project(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    auth_token: Optional[str] = Cookie(None)
):
    """Create a new project"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token found")
    
    try:
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        owner_id = token_data.get('user_id')
        try:
            owner_uuid = UUID(owner_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")
        
        # Create project using service
        new_project = await project_service.create_project(
            db=db,
            name=name,
            description=description or '',
            owner_id=owner_uuid
        )
        
        return {
            "id": str(new_project.project_id),
            "name": new_project.name,
            "description": new_project.description,
            "created_at": new_project.created_at.isoformat() if new_project.created_at else None,
            "owner_id": str(new_project.owner_id)
        }
        
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")

@router.post("/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[UUID] = Form(default=None),
    folder_id: Optional[UUID] = Form(default=None),
    auth_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
):
    logger.info("=== Document Upload Request Started ===")
    
    try:
        content = await file.read()
        logger.info(f"File successfully read. Size: {len(content)} bytes")
        
        if not auth_token:
            logger.error("No auth token found in request")
            raise HTTPException(status_code=401, detail="No authentication token found")
        
        # Get client_id from auth token
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        client_id = token_data['client_id']
        
        # Verify API key exists in Redis
        api_key = redis_client.get(f"api_key:{client_id}")
        if not api_key:
            raise HTTPException(
                status_code=401, 
                detail="No API key found. Please ensure you've set up your API key."
            )
        
        # If project_id is provided, validate it exists and user has access
        if project_id:
            logger.info(f"Validating project_id: {project_id}")
            project = await db.execute(
                select(ResearchProject)
                .where(
                    ResearchProject.project_id == project_id,
                    ResearchProject.owner_id == token_data['user_id']  # Add owner check
                )
            )
            project = project.scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        # Verify file type
        mime = magic.Magic(mime=True)
        file_type = mime.from_buffer(content)
        logger.info(f"Detected file type: {file_type}")
        if file_type != 'application/pdf':
            logger.error(f"Invalid file type: {file_type}")
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Process document with client_id
        try:
            document = await project_service.add_document(
                session=db,
                project_id=project_id,
                folder_id=folder_id,
                file_content=content,
                filename=file.filename,
                client_id=client_id
            )
            logger.info(f"Document successfully processed. ID: {document.document_id}")

            return {
                "document_id": document.document_id,
                "filename": document.filename,
                "status": document.processing_status
            }

        except Exception as e:
            logger.error(f"Error in document processing: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

    except ValueError as ve:
        logger.error(f"Value error in request processing: {str(ve)}", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid project_id or folder_id format: {str(ve)}"
        )

@router.get("/projects")
async def get_projects(
    db: AsyncSession = Depends(get_db),
    auth_token: Optional[str] = Cookie(None)
) -> List[dict]:
    """Get all projects for authenticated user"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token found")
    
    try:
        # DEBUG: Query all projects in database
        debug_query = select(ResearchProject)
        debug_result = await db.execute(debug_query)
        all_projects = debug_result.scalars().all()
        logger.debug("=== DEBUG: ALL PROJECTS IN DATABASE ===")
        for proj in all_projects:
            logger.debug(f"""
Project Details:
    ID: {proj.project_id}
    Name: {proj.name}
    Description: {proj.description}
    Owner ID: {proj.owner_id}
    Created At: {proj.created_at}
    Updated At: {proj.updated_at}
    Status: {proj.status}
    Settings: {proj.settings}
====================================
            """)
        
        # Original authentication logic continues...
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        owner_id = token_data.get('user_id')
        logger.debug(f"Looking for projects with owner_id: {owner_id}")
        
        # Rest of the original function...
        query = select(ResearchProject).where(ResearchProject.owner_id == owner_id)
        result = await db.execute(query)
        projects = result.scalars().all()
        
        logger.debug(f"Found {len(projects)} projects for user {owner_id}")
        
        return [
            {
                "id": str(project.project_id),
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "owner_id": project.owner_id
            }
            for project in projects
        ]
    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {str(e)}")

@router.post("/projects/{project_id}/select")
async def select_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth_token: Optional[str] = Cookie(None)
):
    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token found")
    
    token_data = security_service.decode_token(auth_token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    try:
        # Verify project exists and belongs to user
        query = select(ResearchProject).where(
            ResearchProject.project_id == project_id,
            ResearchProject.owner_id == token_data['user_id']
        )
        result = await db.execute(query)
        project = result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {"status": "success", "project_id": str(project_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to select project: {str(e)}")

@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    auth_token: Optional[str] = Cookie(None)
):
    """Delete a project"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token found")
    
    try:
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        owner_id = token_data.get('user_id')
        try:
            project_uuid = UUID(project_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid project ID format")
        
        # Delete project using direct query to match string owner_id
        query = delete(ResearchProject).where(
            ResearchProject.project_id == project_uuid,
            ResearchProject.owner_id == str(owner_id)  # Convert UUID to string for comparison
        )
        result = await db.execute(query)
        await db.commit()
        
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        return {"message": "Project deleted successfully"}
        
    except ValueError as e:
        logger.error(f"Value error in delete project: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid ID format: {str(e)}")
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")

@router.put("/projects/{project_id}")
async def update_project(
    project_id: UUID,
    name: str = Body(...),
    description: str = Body(None),
    db: AsyncSession = Depends(get_db),
    auth_token: Optional[str] = Cookie(None)
):
    """Update a project's details"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token found")
    
    try:
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        owner_id = token_data.get('user_id')
        
        # Get the project and verify ownership
        query = select(ResearchProject).where(
            ResearchProject.project_id == project_id,
            ResearchProject.owner_id == owner_id
        )
        result = await db.execute(query)
        project = result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        # Update project details
        project.name = name
        project.description = description
        project.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(project)
        
        return {
            "id": str(project.project_id),
            "name": project.name,
            "description": project.description,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "owner_id": project.owner_id
        }
        
    except Exception as e:
        logger.error(f"Error updating project: {str(e)}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update project: {str(e)}")

@router.get("/projects/{project_id}/documents")
async def get_project_documents(
    project_id: UUID,
    folder_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    auth_token: Optional[str] = Cookie(None)
):
    """Get all documents for a project or specific folder"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="No authentication token found")
    
    try:
        # Verify token and ownership
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        owner_id = token_data.get('user_id')
        
        # Verify project exists and user has access
        project = await project_service.get_project(db, project_id, owner_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        
        # Get documents using the project service
        documents = await project_service.get_project_documents(
            session=db,
            project_id=str(project_id),
            folder_id=str(folder_id) if folder_id else None
        )
        
        return documents
        
    except ValueError as e:
        logger.error(f"Value error in get documents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting project documents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get documents: {str(e)}")
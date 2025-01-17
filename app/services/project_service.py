from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from fastapi import HTTPException
from uuid import UUID
import logging
from datetime import datetime, timezone
from io import BytesIO
import magic

from ..models.project import ResearchProject, ProjectFolder, Document
from .document_processor import DocumentProcessor
from ..core.exceptions import DocumentExistsError, InvalidFileTypeError


logger = logging.getLogger(__name__)

class DocumentExistsError(Exception):
    """Raised when attempting to add a document that already exists in the project"""
    pass

class ProjectService:
    def __init__(self, document_processor: Optional[DocumentProcessor] = None):
        self.document_processor = document_processor

    async def create_project(
        self,
        db: AsyncSession,
        name: str,
        owner_id: UUID,
        description: str = ''
    ) -> ResearchProject:
        """Create a new project"""
        try:
            logger.debug(f"Creating project: name={name}, owner_id={owner_id}")
            
            project = ResearchProject(
                name=name,
                description=description,
                owner_id=str(owner_id)
            )
            
            db.add(project)
            await db.commit()
            await db.refresh(project)
            
            logger.debug(f"Created project with ID: {project.project_id}")
            return project
            
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}", exc_info=True)
            await db.rollback()
            raise

    async def get_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        owner_id: UUID
    ) -> Optional[ResearchProject]:
        """Get a project by ID and verify ownership"""
        try:
            logger.debug(f"Fetching project: project_id={project_id}, owner_id={owner_id}")
            query = select(ResearchProject).where(
                ResearchProject.project_id == project_id,
                ResearchProject.owner_id == str(owner_id)
            )
            result = await db.execute(query)
            project = result.scalar_one_or_none()
            
            if project:
                logger.debug(f"Found project: {project.name}")
            else:
                logger.debug("No project found")
                
            return project
        except Exception as e:
            logger.error(f"Error fetching project: {str(e)}", exc_info=True)
            raise

    async def get_project_documents(
        self,
        session: AsyncSession,
        project_id: str,
        folder_id: Optional[str] = None
    ) -> List[Dict]:
        """Get all documents for a project or specific folder"""
        try:
            logger.debug(f"Fetching documents for project: {project_id}, folder: {folder_id}")
            
            query = select(Document)
            if folder_id:
                logger.debug(f"Filtering by folder_id: {folder_id}")
                query = query.where(Document.folder_id == folder_id)
            else:
                # If no folder_id, get all documents in project through folder relationship
                logger.debug("No folder_id specified, getting all project documents")
                query = query.join(ProjectFolder).where(ProjectFolder.project_id == project_id)
            
            result = await session.execute(query)
            documents = result.scalars().all()
            
            logger.debug(f"Found {len(documents)} documents")
            for doc in documents:
                logger.debug(f"""
                Document details:
                - ID: {doc.document_id}
                - Filename: {doc.filename}
                - Status: {doc.processing_status}
                - Folder ID: {doc.folder_id}
                - Size: {doc.file_size} bytes
                """)
            
            return [
                {
                    "document_id": str(doc.document_id),
                    "filename": doc.filename,
                    "status": doc.processing_status,
                    "folder_id": str(doc.folder_id) if doc.folder_id else None,
                    "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
                    "file_size": doc.file_size
                }
                for doc in documents
            ]
            
        except Exception as e:
            logger.error(f"Error getting project documents: {str(e)}", exc_info=True)
            raise

    async def delete_project(
        self,
        db: AsyncSession,
        project_id: UUID,
        owner_id: UUID
    ) -> bool:
        """Delete a project and verify ownership"""
        try:
            logger.debug(f"Deleting project: project_id={project_id}, owner_id={owner_id}")
            query = delete(ResearchProject).where(
                ResearchProject.project_id == project_id,
                ResearchProject.owner_id == owner_id
            )
            result = await db.execute(query)
            await db.commit()
            
            success = result.rowcount > 0
            logger.debug(f"Project deletion {'successful' if success else 'failed'}")
            return success
            
        except Exception as e:
            logger.error(f"Error deleting project: {str(e)}", exc_info=True)
            await db.rollback()
            raise

    async def check_document_exists(
        self,
        session: AsyncSession,
        project_id: UUID,
        filename: str
    ) -> Optional[Document]:
        """Check if a document with the same filename exists in the project"""
        try:
            query = select(Document).join(ProjectFolder).where(
                ProjectFolder.project_id == project_id,
                Document.filename == filename
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error checking document existence: {str(e)}", exc_info=True)
            raise

    def validate_file_type(self, file_content: bytes) -> None:
        """Validate that the file is a PDF"""
        mime = magic.Magic(mime=True)
        file_type = mime.from_buffer(file_content)
        
        if file_type != 'application/pdf':
            logger.error(f"Invalid file type detected: {file_type}")
            raise InvalidFileTypeError(f"Only PDF files are supported. Detected type: {file_type}")

    async def add_document(
        self,
        session: AsyncSession,
        project_id: UUID,
        folder_id: Optional[UUID],
        file_content: bytes,
        filename: str,
        client_id: str
    ) -> Document:
        """Add a new document to a project"""
        try:
            # Validate file type first
            self.validate_file_type(file_content)
            
            # Check if document already exists in this project
            existing_doc = await self.check_document_exists(session, project_id, filename)
            if existing_doc:
                logger.info(f"Document '{filename}' already exists in project {project_id}")
                raise DocumentExistsError(
                    f"Document '{filename}' already exists in this project. "
                    f"Document ID: {existing_doc.document_id}"
                )

            # If no folder_id provided, use project's root folder
            if not folder_id:
                root_folder = await self.get_project_root_folder(session, project_id)
                if not root_folder:
                    raise ValueError("No root folder found for project")
                folder_id = root_folder.folder_id

            # Process document
            document = await self.document_processor.process_document(
                session=session,
                project_id=project_id,
                folder_id=folder_id,
                file_content=file_content,
                filename=filename,
                client_id=client_id
            )

            return document

        except (DocumentExistsError, InvalidFileTypeError):
            raise
        except Exception as e:
            logger.error(f"Error adding document: {str(e)}", exc_info=True)
            raise

    async def get_project_root_folder(
        self,
        session: AsyncSession,
        project_id: UUID
    ) -> Optional[ProjectFolder]:
        """Get or create the root folder for a project"""
        try:
            # First, try to get the root folder
            query = select(ProjectFolder).where(
                and_(
                    ProjectFolder.project_id == project_id,
                    ProjectFolder.parent_folder_id.is_(None)
                )
            ).order_by(ProjectFolder.created_at)  # Order by creation date to get the oldest one
            
            result = await session.execute(query)
            root_folders = result.scalars().all()
            
            if not root_folders:
                # No root folder exists, create one
                root_folder = ProjectFolder(
                    project_id=project_id,
                    name="root",
                    parent_folder_id=None,
                    path_array=[]
                )
                session.add(root_folder)
                await session.commit()
                await session.refresh(root_folder)
                return root_folder
                
            elif len(root_folders) > 1:
                # Multiple root folders found - this is an error state
                # Keep the oldest one and delete the others
                logger.warning(f"Found {len(root_folders)} root folders for project {project_id}. Cleaning up duplicates.")
                root_folder = root_folders[0]  # Keep the first (oldest) one
                
                # Delete the duplicates
                for duplicate in root_folders[1:]:
                    await session.delete(duplicate)
                
                await session.commit()
                return root_folder
                
            else:
                # Single root folder found
                return root_folders[0]
                
        except Exception as e:
            logger.error(f"Error getting/creating root folder: {str(e)}")
            raise

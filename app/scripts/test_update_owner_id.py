import asyncio
from typing import Optional
import logging
from uuid import UUID 
import uuid 
from datetime import datetime, timezone
import os

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, BigInteger, ARRAY, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create declarative base using new style
Base = declarative_base()

class ProjectFolder(Base):
    __tablename__ = 'project_folders'
    
    folder_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey('research_projects.project_id', ondelete='CASCADE'))
    parent_folder_id = Column(UUID(as_uuid=True), ForeignKey('project_folders.folder_id', ondelete='SET NULL'), nullable=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    path_array = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    project = relationship("ResearchProject", back_populates="folders")
    documents = relationship("Document", back_populates="folder", cascade="all, delete-orphan")
    parent = relationship("ProjectFolder", remote_side=[folder_id])

class Document(Base):
    __tablename__ = 'documents'
    
    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    folder_id = Column(UUID(as_uuid=True), ForeignKey('project_folders.folder_id', ondelete='CASCADE'))
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    upload_date = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    processing_status = Column(String(50), nullable=False)
    doc_metadata = Column(JSONB, default={})
    file_size = Column(BigInteger)
    hash_id = Column(String(64))
    qdrant_chunks = Column(ARRAY(String), default=[])
    
    folder = relationship("ProjectFolder", back_populates="documents")

class ResearchProject(Base):
    __tablename__ = 'research_projects'
    
    project_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    owner_id = Column(String, nullable=False)  # Changed to String to match auth_token
    status = Column(String(50), default='active')
    settings = Column(JSONB, default={})
    
    folders = relationship("ProjectFolder", back_populates="project", cascade="all, delete-orphan")

# Get database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost/research_platform"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    future=True,
    pool_size=20,
    max_overflow=0
)

# Create async session maker
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def update_project_owner(
    session: AsyncSession,
    old_owner_id: str,
    new_owner_id: str,
    project_id: Optional[UUID] = None
) -> int:
    """
    Update owner_id for projects matching the old_owner_id.
    Returns number of records updated.
    """
    try:
        # Build update query
        query = update(ResearchProject).where(
            ResearchProject.owner_id == old_owner_id
        )
        
        # Add project_id filter if specified
        if project_id:
            query = query.where(ResearchProject.project_id == project_id)
            
        query = query.values(owner_id=new_owner_id)
        
        # Execute update
        result = await session.execute(query)
        await session.commit()
        
        rows_updated = result.rowcount
        logger.info(f"Updated {rows_updated} projects from owner_id {old_owner_id} to {new_owner_id}")
        return rows_updated
        
    except Exception as e:
        logger.error(f"Error updating owner_id: {str(e)}")
        await session.rollback()
        raise

async def main():
    # Replace these values with your actual owner IDs
    NEW_OWNER_ID = "aa5c38ff-7fb4-41d0-9fb3-ed2d67d3b4c3"  # The JWT token that was incorrectly stored
    OLD_OWNER_ID = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjbGllbnRfaWQiOiI3ZGU1NjQyNC03YmZhLTQ5MzAtOTcyOC02ZGNlYWY4YzdjNzAiLCJ1c2VyX2lkIjoiMTY0YmM1MDAtZjJkMC00ZmRkLTg3M2UtNjAxMGJiN2RkOTgzIiwiZXhwIjoxNzM5MTMwMjIzfQ.60X3wV_39JTCcCaiWcvfzCBqVXhwragnyzEYf6n3Rz0"  
    
    async with async_session() as session:
        # DEBUG: First, let's see ALL projects in the database
        debug_query = select(ResearchProject)
        debug_result = await session.execute(debug_query)
        all_projects = debug_result.scalars().all()
        
        logger.info("=== DEBUG: ALL PROJECTS IN DATABASE ===")
        for proj in all_projects:
            logger.info(f"""
Project Details:
    ID: {proj.project_id}
    Name: {proj.name}
    Description: {proj.description}
    Owner ID: {proj.owner_id}
    Created At: {proj.created_at}
    Updated At: {proj.updated_at}
    Status: {proj.status}
====================================
            """)
            
        # Now continue with the original search
        logger.info(f"Searching for projects with owner_id: {OLD_OWNER_ID}")
        query = select(ResearchProject).where(ResearchProject.owner_id == OLD_OWNER_ID)
        result = await session.execute(query)
        projects = result.scalars().all()
        
        logger.info(f"Found {len(projects)} projects to update:")
        for project in projects:
            logger.info(f"Project ID: {project.project_id}, Name: {project.name}")
        
        if projects:
            # Confirm before updating
            confirmation = input("Do you want to proceed with the update? (y/N): ")
            if confirmation.lower() == 'y':
                updated = await update_project_owner(session, OLD_OWNER_ID, NEW_OWNER_ID)
                logger.info(f"Successfully updated {updated} projects")
            else:
                logger.info("Update cancelled")
        else:
            logger.info("No projects found with the specified old owner ID")

if __name__ == "__main__":
    asyncio.run(main()) 
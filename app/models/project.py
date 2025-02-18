from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, BigInteger, ARRAY, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from ..database import Base

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
    conversations = relationship("Conversation", back_populates="project", lazy="dynamic")

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
    raw_content = Column(String)
    
    folder = relationship("ProjectFolder", back_populates="documents")

# Remove ProjectCollaborator for now as it's not being used

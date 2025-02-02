from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone

from app.database import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    heading = Column(String)
    url = Column(String, nullable=False)
    source_site = Column(String, nullable=False)
    content = Column(String)
    analysis = Column(String)
    scraped_at = Column(DateTime(timezone=True), nullable=False)
    is_liveblog = Column(Boolean, default=False)
    last_updated = Column(DateTime(timezone=True))

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone

from app.database import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    heading = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    source_site = Column(String, nullable=False)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

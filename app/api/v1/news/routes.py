from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone, timedelta

from ....database import get_db
from ....models.news_article import NewsArticle

router = APIRouter()

@router.get("/articles")
async def get_news_articles(
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    days: int = 7
) -> List[dict]:
    """
    Get recent news articles, ordered by scraped_at date.
    
    Args:
        limit: Maximum number of articles to return
        days: Number of days to look back for articles
    """
    try:
        # Calculate the cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Query for recent articles
        query = (
            select(NewsArticle)
            .where(NewsArticle.scraped_at >= cutoff_date)
            .order_by(NewsArticle.scraped_at.desc())
            .limit(limit)
        )
        
        result = await db.execute(query)
        articles = result.scalars().all()
        
        return [
            {
                "id": str(article.id),
                "title": article.title,
                "heading": article.heading,
                "url": article.url,
                "source_site": article.source_site,
                "scraped_at": article.scraped_at.isoformat()
            }
            for article in articles
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch news articles: {str(e)}"
        )

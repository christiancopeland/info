from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from datetime import datetime, timezone, timedelta
import asyncio
import logging

from ....database import get_db
from ....models.news_article import NewsArticle
from ....services.news_extraction_service import NewsExtractionService

router = APIRouter()

# Initialize the news extraction service
NEWS_SERVICE = NewsExtractionService(
    api_url="http://localhost:3002/v1"
)

logger = logging.getLogger(__name__)

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
                "scraped_at": article.scraped_at.isoformat(),
                "is_liveblog": article.is_liveblog,
                "last_updated": article.last_updated.isoformat() if article.last_updated else None
            }
            for article in articles
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch news articles: {str(e)}"
        )

@router.get("/articles/{article_id}/content")
async def get_article_content(
    article_id: str,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get or scrape the content of a specific article."""
    try:
        # Query for the article
        query = select(NewsArticle).where(NewsArticle.id == article_id)
        result = await db.execute(query)
        article = result.scalar_one_or_none()
        
        if not article:
            raise HTTPException(
                status_code=404,
                detail=f"Article with ID {article_id} not found"
            )
        
        # If content exists and article is not a liveblog, return cached content
        if article.content and not article.is_liveblog:
            return {
                "id": str(article.id),
                "title": article.title,
                "url": article.url,
                "content": article.content,
                "is_liveblog": article.is_liveblog,
                "last_updated": article.last_updated.isoformat() if article.last_updated else None,
                "scraped_at": article.scraped_at.isoformat()
            }
        
        # Otherwise, scrape fresh content
        try:
            # Determine if it's a liveblog
            is_liveblog = 'liveblog' in article.url.lower()
            current_time = datetime.now(timezone.utc)
            
            # Scrape the content
            content = await NEWS_SERVICE.scrape_article_content(article.url)
            
            # Update the article in the database
            update_stmt = (
                update(NewsArticle)
                .where(NewsArticle.id == article_id)
                .values(
                    content=content,
                    is_liveblog=is_liveblog,
                    last_updated=current_time
                )
            )
            await db.execute(update_stmt)
            await db.commit()
            
            return {
                "id": str(article.id),
                "title": article.title,
                "url": article.url,
                "content": content,
                "is_liveblog": is_liveblog,
                "last_updated": current_time.isoformat(),
                "scraped_at": article.scraped_at.isoformat()
            }
            
        except ValueError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to scrape article content: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch article: {str(e)}"
        )

@router.post("/articles/rescrape")
async def rescrape_articles(
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Force a rescrape of all articles and default sources."""
    try:
        # First, scrape all default sources
        source_results = await NEWS_SERVICE.scrape_default_sources()
        
        # Then, rescrape existing articles without content
        query = select(NewsArticle).where(NewsArticle.content.is_(None))
        result = await db.execute(query)
        articles = result.scalars().all()
        
        processed = 0
        failed = 0
        
        for article in articles:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Force scrape the content
                content = await NEWS_SERVICE.scrape_article_content(
                    article.url,
                    force_scrape=True
                )
                
                # Update the article
                update_stmt = (
                    update(NewsArticle)
                    .where(NewsArticle.id == article.id)
                    .values(
                        content=content,
                        is_liveblog='liveblog' in article.url.lower(),
                        last_updated=current_time
                    )
                )
                await db.execute(update_stmt)
                await db.commit()
                
                processed += 1
                
                # Add a small delay to be nice to the servers
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to scrape article {article.id}: {str(e)}")
                failed += 1
                continue
        
        return {
            "message": "Rescrape completed",
            "existing_articles": {
                "processed": processed,
                "failed": failed,
                "total": len(articles)
            },
            "default_sources": source_results
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rescrape articles: {str(e)}"
        )

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from .news_extraction_service import NewsExtractionService
from ..database import get_db
from ..models.news_article import NewsArticle

# Initialize the news extraction service
news_extraction_service = NewsExtractionService(
    api_url="http://localhost:3002/v1/scrape",
    api_key=None  # Set your API key if needed
)

async def scrape_and_store_news():
    """Scrape news articles and store them in the database."""
    async with get_db() as session:
        try:
            # Example URL list to scrape
            urls = ["https://www.local3news.com", "https://www.propublica.org/", "https://www.aljazeera.com/", "https://apnews.com/", ]
            for url in urls:
                articles = news_extraction_service.extract_articles(url)
                for article in articles:
                    # Check if the article already exists
                    existing_article = await session.execute(
                        select(NewsArticle).where(NewsArticle.url == article.url)
                    )
                    if existing_article.scalar_one_or_none():
                        continue  # Skip if already exists

                    # Create a new NewsArticle instance
                    news_article = NewsArticle(
                        title=article.title,
                        heading=article.heading,
                        url=article.url,
                        source_site=url
                    )
                    session.add(news_article)
            
            await session.commit()
            print("News articles scraped and stored successfully.")
        except Exception as e:
            print(f"Error during scraping and storing: {str(e)}")
            await session.rollback()

def start_scheduler():
    """Start the APScheduler to run the scraping task."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scrape_and_store_news, 'interval', hours=6)  # Run every 6 hours
    scheduler.start()

if __name__ == "__main__":
    asyncio.run(start_scheduler())

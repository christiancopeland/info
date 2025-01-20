from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import requests
import time
from datetime import datetime, timezone
import json
from typing import List
from pydantic import BaseModel

from app.services.news_extraction_service import NewsExtractionService
from app.database import get_db, async_session
from app.models.news_article import NewsArticle

class Article(BaseModel):
    title: str
    heading: str
    url: str

class Extract(BaseModel):
    articles: List[Article]

class Metadata(BaseModel):
    title: str
    description: str
    favicon: str
    language: str
    keywords: str | None = None
    robots: str | None = None
    ogTitle: str | None = None
    ogUrl: str | None = None
    ogImage: str | None = None
    ogLocaleAlternate: List[str] | None = None
    ogSiteName: str | None = None

class FirecrawlData(BaseModel):
    metadata: Metadata
    extract: Extract
    warning: str | None = None

class BatchResponse(BaseModel):
    success: bool
    id: str
    url: str

class BatchResultResponse(BaseModel):
    success: bool
    status: str
    completed: int
    total: int
    creditsUsed: int
    expiresAt: str
    data: List[FirecrawlData]

class BatchScraper:
    def __init__(self, api_url: str, api_key: str = None):
        self.api_url = api_url.rstrip('/')
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def extract_articles_batch(self, urls: List[str], max_retries: int = 10, retry_delay: int = 2) -> List[Article]:
        # Step 1: Initialize batch job
        batch_payload = {
            "urls": urls,
            "formats": ["extract"],
            "onlyMainContent": True,
            "extract": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "articles": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "heading": {"type": "string"},
                                    "url": {"type": "string"}
                                },
                                "required": ["title", "heading", "url"]
                            }
                        }
                    },
                    "required": ["articles"]
                },
                "systemPrompt": """You are a specialized news article extractor.
                Extract articles that cover:
                - Political activities and developments
                - Criminal cases, investigations, and law enforcement
                - Government operations, policies, and decisions
                - Public corruption or misconduct
                - Legislative updates and regulatory changes
                - Court proceedings and legal matters
                
                Don't neglect any of the above, but feel free to include other relevant news articles as well.""",
                
                "prompt": """Analyze the webpage and extract news articles related to:
                1. Political events and developments
                2. Criminal activities, investigations, law enforcement, and any general crime news
                3. Government operations and policy changes
                4. Public official activities and decisions
                5. Court cases and legal proceedings
                
                Exclude articles about weather, sports, entertainment, or general human interest stories unless they directly relate to government activities, criminal investigations/activities, or the other topics listed previously.
                
                For each relevant article, return its title, heading, and URL in the specified format."""
            }
        }

        try:
            # Initialize batch job
            init_response = requests.post(
                f"{self.api_url}/batch/scrape",
                json=batch_payload,
                headers=self.headers
            )
            init_response.raise_for_status()
            batch_data = BatchResponse.model_validate_json(init_response.text)
            
            # Ensure we're using http instead of https for local development
            result_url = batch_data.url.replace('https://', 'http://')
            
            print(f"Batch job initialized with ID: {batch_data.id}")
            print(f"Results URL: {result_url}")

            # Step 2: Poll for results
            for attempt in range(max_retries):
                time.sleep(retry_delay)  # Wait before checking results
                
                result_response = requests.get(result_url, headers=self.headers)
                result_response.raise_for_status()
                
                result_data = BatchResultResponse.model_validate_json(result_response.text)
                
                if result_data.status == "completed":
                    print(f"Batch job completed. Credits used: {result_data.creditsUsed}")
                    
                    # Collect all articles from all responses
                    all_articles = []
                    for data in result_data.data:
                        all_articles.extend(data.extract.articles)
                    return all_articles
                
                print(f"Job status: {result_data.status} ({result_data.completed}/{result_data.total})")
            
            raise TimeoutError("Batch job did not complete within the maximum retries")

        except Exception as e:
            print(f"Error in batch scraping: {type(e).__name__}: {str(e)}")
            raise

async def scrape_and_store_news():
    """Scrape news articles and store them in the database."""
    async for session in get_db():
        try:
            # Initialize batch scraper
            scraper = BatchScraper(api_url="http://localhost:3002/v1")
            
            # Target URLs to scrape
            urls = [
                "https://www.local3news.com",
                "https://www.propublica.org/",
                "https://www.aljazeera.com/",
                "https://apnews.com/"
            ]
            
            # Get all articles in one batch request
            articles = scraper.extract_articles_batch(urls)
            print(f"Retrieved {len(articles)} articles in total")
            
            # Store articles
            for article in articles:
                # Check if the article already exists
                query = select(NewsArticle).where(NewsArticle.url == article.url)
                result = await session.execute(query)
                if result.scalar_one_or_none():
                    print(f"Skipping existing article: {article.title}")
                    continue

                print(f"Storing new article: {article.title}")
                print(f"Article URL: {article.url}")

                # Create a new NewsArticle instance with explicit timezone handling
                news_article = NewsArticle(
                    title=article.title,
                    heading=article.heading,
                    url=article.url,
                    source_site=next(url for url in urls if url in article.url),
                    # Let the model handle the timestamp with its default value
                    scraped_at=datetime.now(timezone.utc)
                )
                session.add(news_article)
            
            await session.commit()
            print("News articles scraped and stored successfully.")
            
        except Exception as e:
            print(f"Error during scraping and storing: {str(e)}")
            await session.rollback()
            raise

async def main():
    try:
        await scrape_and_store_news()
    except Exception as e:
        print(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
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
import os
from pathlib import Path
from playwright.async_api import async_playwright

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

    def extract_articles_batch(self, urls: List[str], max_retries: int = 20, retry_delay: int = 5) -> List[Article]:
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
                
                MAKE SURE TO INCLUDE ANY LIVEBLOG ARTICLES FOUND IF THEY ARE RELEVANT TO THE TOPICS LISTED ABOVE.

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

            # Step 2: Poll for results with exponential backoff
            backoff = retry_delay
            for attempt in range(max_retries):
                time.sleep(backoff)  # Wait before checking results
                
                try:
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
                    
                    # If we're making progress, reset the backoff
                    if result_data.completed > 0:
                        backoff = retry_delay
                    else:
                        # Exponential backoff up to 30 seconds
                        backoff = min(backoff * 1.5, 30)
                    
                    print(f"Job status: {result_data.status} ({result_data.completed}/{result_data.total})")
                
                except requests.RequestException as e:
                    print(f"Request error during attempt {attempt + 1}: {str(e)}")
                    # Continue retrying on request errors
                    continue
            
            raise TimeoutError(f"Batch job did not complete within {max_retries} retries. Last status: {result_data.status} ({result_data.completed}/{result_data.total})")

        except Exception as e:
            print(f"Error in batch scraping: {type(e).__name__}: {str(e)}")
            raise

async def scrape_liveblog_content(url: str, filtered_phrases: List[str]) -> str:
    """Test function to scrape liveblog content using Playwright"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Increase timeout and add loading state check
            try:
                # Navigate with a longer timeout
                await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                
                # Wait for either the content or an error state
                try:
                    await page.wait_for_selector('.wysiwyg-content, .timeline-item', timeout=30000)
                except:
                    print(f"Warning: Could not find main content selectors for {url}")
                
                # Add a small delay to allow dynamic content to load
                await page.wait_for_timeout(2000)
                
            except Exception as e:
                print(f"Navigation error for {url}: {str(e)}")
                return f"Error loading page: {str(e)}"
            
            text_content = []
            
            # Get the main headline/title
            try:
                main_title = await page.query_selector('h1')
                if main_title:
                    title_text = await main_title.text_content()
                    text_content.append(f"# {title_text.strip()}\n")
            except Exception as e:
                print(f"Error extracting title: {str(e)}")
            
            # Get the summary content
            try:
                summary = await page.query_selector('.wysiwyg-content')
                if summary:
                    summary_text = await summary.text_content()
                    if summary_text.strip():
                        text_content.append("SUMMARY:")
                        text_content.append(summary_text.strip())
            except Exception as e:
                print(f"Error extracting summary: {str(e)}")
            
            # Get all liveblog entries with error handling
            try:
                entries = await page.query_selector_all('.timeline-item')
                
                for entry in entries:
                    try:
                        # Extract timestamp
                        timestamp = await entry.query_selector('.timeline-item__time')
                        if timestamp:
                            time_text = await timestamp.text_content()
                            text_content.append(f"\n[{time_text.strip()}]\n")
                        
                        # Extract content
                        content = await entry.query_selector('.timeline-item__content')
                        if content:
                            # Get headers
                            headers = await content.query_selector_all('h2, h3, h4')
                            for header in headers:
                                header_text = await header.text_content()
                                if (header_text.strip() and 
                                    not any(phrase in header_text.lower() for phrase in filtered_phrases)):
                                    text_content.append(f"\n## {header_text.strip()}\n")
                            
                            # Get paragraphs
                            paragraphs = await content.query_selector_all('p')
                            for p in paragraphs:
                                p_text = await p.text_content()
                                if (p_text.strip() and 
                                    not any(phrase in p_text.lower() for phrase in filtered_phrases)):
                                    text_content.append(p_text.strip())
                            
                            # Get list items
                            list_items = await content.query_selector_all('li')
                            for item in list_items:
                                item_text = await item.text_content()
                                if (item_text.strip() and 
                                    not any(phrase in item_text.lower() for phrase in filtered_phrases)):
                                    text_content.append(f"• {item_text.strip()}")
                    except Exception as e:
                        print(f"Error processing entry: {str(e)}")
                        continue
                
            except Exception as e:
                print(f"Error processing timeline entries: {str(e)}")
            
            # If no timeline items found, try to get content from wysiwyg sections
            if not entries:
                try:
                    wysiwyg_content = await page.query_selector_all('.wysiwyg-content h2, .wysiwyg-content h3, .wysiwyg-content p, .wysiwyg-content li')
                    for content in wysiwyg_content:
                        try:
                            tag_name = await content.evaluate('element => element.tagName.toLowerCase()')
                            content_text = await content.text_content()
                            
                            if (content_text.strip() and 
                                not any(phrase in content_text.lower() for phrase in filtered_phrases)):
                                if tag_name in ['h2', 'h3']:
                                    text_content.append(f"\n## {content_text.strip()}\n")
                                elif tag_name == 'li':
                                    text_content.append(f"• {content_text.strip()}")
                                else:
                                    text_content.append(content_text.strip())
                        except Exception as e:
                            print(f"Error processing wysiwyg content item: {str(e)}")
                            continue
                except Exception as e:
                    print(f"Error processing wysiwyg content: {str(e)}")
            
            # Remove duplicate paragraphs that are next to each other
            filtered_content = []
            prev_content = None
            for content in text_content:
                if content != prev_content:
                    filtered_content.append(content)
                prev_content = content
            
            final_content = '\n\n'.join(filtered_content)
            if not final_content.strip():
                return "No content could be extracted from the page."
                
            return final_content
            
        except Exception as e:
            print(f"Unexpected error in scrape_liveblog_content: {str(e)}")
            return f"Error scraping content: {str(e)}"
            
        finally:
            await browser.close()

async def scrape_and_store_news():
    """Scrape news articles and store them in a test output file and database."""
    filtered_phrases = [
        "Support ProPublica's investigative reporting today.",
        "Donate Now",
        "We're trying something new.",
        "was it helpful",
        "recommended stories",
        "Do You Work for the Federal Government? ProPublica Wants to Hear From You.",
        "propublica wants to hear from you",
        "We're expanding our coverage of government agencies and federal policy",
        "with your help, we can dig deeper",
        "Read More",
        # Al Jazeera video player phrases
        "watch below",
        "chapters",
        "descriptions off",
        "captions settings",
        "captions off",
        "this is a modal window",
        "beginning of dialog window",
        "end of dialog window",
        "escape will cancel",
        "modal can be closed",
        "activating the close button",
        "selected",
        "opens captions settings dialog"
    ]

    try:
        # Initialize batch scraper and news extraction service
        scraper = BatchScraper(api_url="http://localhost:3002/v1")
        news_service = NewsExtractionService(api_url="http://localhost:3002/v1", filtered_phrases=filtered_phrases)
        
        # Create output directory if it doesn't exist
        output_dir = Path("test_output")
        output_dir.mkdir(exist_ok=True)
        
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
        
        # Create a test output file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"scraped_articles_{timestamp}.txt"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Scraping Results - {datetime.now()}\n")
            f.write("=" * 80 + "\n\n")
            
            # Store articles
            for i, article in enumerate(articles, 1):
                print(f"Processing article {i}/{len(articles)}: {article.title}")
                
                f.write(f"Article {i}:\n")
                f.write(f"Title: {article.title}\n")
                f.write(f"Heading: {article.heading}\n")
                f.write(f"URL: {article.url}\n")
                f.write(f"Source: {next(url for url in urls if url in article.url)}\n")
                
                try:
                    # Check if it's a liveblog
                    if 'liveblog' in article.url.lower():
                        print(f"Detected liveblog: {article.url}")
                        content = await scrape_liveblog_content(article.url, filtered_phrases=filtered_phrases)
                    else:
                        # Use regular scraping for non-liveblog articles
                        content = await news_service.scrape_article_content(article.url)
                    
                    # Filter out unwanted phrases from the content
                    filtered_content = content
                    for phrase in filtered_phrases:
                        filtered_content = filtered_content.replace(phrase.lower(), '')
                        filtered_content = filtered_content.replace(phrase.capitalize(), '')
                        filtered_content = filtered_content.replace(phrase.upper(), '')
                    
                    # Clean up any double newlines or spaces created by filtering
                    filtered_content = '\n'.join(line.strip() for line in filtered_content.split('\n') if line.strip())
                    
                    f.write("\nContent:\n")
                    f.write("-" * 40 + "\n")
                    f.write(filtered_content)
                    f.write("\n" + "-" * 40 + "\n")
                except Exception as e:
                    f.write(f"\nError scraping content: {str(e)}\n")
                
                f.write("\n" + "=" * 80 + "\n\n")
                
                # Add a small delay between requests to be polite
                await asyncio.sleep(2)
        
        print(f"Results written to: {output_file}")
        
        # Store articles in database
        async for session in get_db():
            try:
                for article in articles:
                    # Check if the article already exists
                    query = select(NewsArticle).where(NewsArticle.url == article.url)
                    existing_article = await session.execute(query)
                    existing_article = existing_article.scalar_one_or_none()

                    current_time = datetime.now(timezone.utc)
                    is_liveblog = 'liveblog' in article.url.lower()
                    
                    if existing_article:
                        print(f"Skipping existing article: {article.title}")
                        continue

                    # Get and filter content BEFORE creating the NewsArticle
                    try:
                        # Check if it's a liveblog
                        if is_liveblog:
                            content = await scrape_liveblog_content(article.url, filtered_phrases=filtered_phrases)
                        else:
                            content = await news_service.scrape_article_content(article.url)
                        
                        # Filter out unwanted phrases from the content
                        filtered_content = content
                        for phrase in filtered_phrases:
                            filtered_content = filtered_content.replace(phrase.lower(), '')
                            filtered_content = filtered_content.replace(phrase.capitalize(), '')
                            filtered_content = filtered_content.replace(phrase.upper(), '')
                        
                        # Clean up any double newlines or spaces created by filtering
                        filtered_content = '\n'.join(line.strip() for line in filtered_content.split('\n') if line.strip())
                        
                    except Exception as e:
                        print(f"Error scraping content for {article.url}: {str(e)}")
                        filtered_content = None

                    print(f"Storing new article: {article.title}")
                    print(f"Content length: {len(filtered_content) if filtered_content else 0} characters")
                    
                    news_article = NewsArticle(
                        title=article.title,
                        heading=article.heading,
                        url=article.url,
                        content=filtered_content,  # Now filtered_content is properly scoped
                        source_site=next(url for url in urls if url in article.url),
                        scraped_at=current_time,
                        is_liveblog=is_liveblog,
                        last_updated=current_time if is_liveblog else None
                    )
                    session.add(news_article)
                
                await session.commit()
                print("News articles stored successfully in database.")
                
            except Exception as e:
                print(f"Error storing articles in database: {str(e)}")
                await session.rollback()
                raise

    except Exception as e:
        print(f"Error during scraping: {str(e)}")
        raise

async def main():
    try:
        await scrape_and_store_news()
    except Exception as e:
        print(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
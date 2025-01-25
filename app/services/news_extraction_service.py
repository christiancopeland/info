from pydantic import BaseModel
import requests
from typing import List
import json
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from playwright.async_api import async_playwright

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
    keywords: str

class FirecrawlData(BaseModel):
    metadata: Metadata
    extract: Extract

class FirecrawlResponse(BaseModel):
    success: bool
    data: FirecrawlData

class NewsExtractionService:
    def __init__(self, api_url: str, api_key: str = None, filtered_phrases: List[str] = None):
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        # Add common headers to mimic a browser
        self.scraper_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        # Default filtered phrases if none provided
        self.filtered_phrases = filtered_phrases or [
            "support propublica's investigative reporting",
            "donate now",
            "we're trying something new",
            "was it helpful",
            "recommended stories",
            "do you work for",
            "propublica wants to hear from you",
            "we're expanding our coverage",
            "with your help, we can dig deeper",
            "read more",
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

    def _filter_content(self, content: str) -> str:
        """Filter out unwanted phrases from content."""
        filtered_content = content
        for phrase in self.filtered_phrases:
            filtered_content = filtered_content.replace(phrase.lower(), '')
            filtered_content = filtered_content.replace(phrase.capitalize(), '')
            filtered_content = filtered_content.replace(phrase.upper(), '')
        
        # Clean up any double newlines or spaces created by filtering
        return '\n'.join(line.strip() for line in filtered_content.split('\n') if line.strip())

    def extract_articles(self, target_url: str) -> List[Article]:
        payload = {
            "url": target_url,
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
            },
            "timeout": 30000,
            "removeBase64Images": True,
            "waitFor": 500
        }

        try:
            print(f"Making request to {self.api_url} for URL: {target_url}")
            response = requests.post(self.api_url, json=payload, headers=self.headers)
            
            print(f"Response status code: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            
            # Save raw response to debug log file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_filename = f'firecrawl_debug_{timestamp}.json'
            
            with open(debug_filename, 'w') as f:
                try:
                    if response.status_code != 200:
                        print(f"Error response body: {response.text}")
                        f.write(f"Status Code: {response.status_code}\n")
                        f.write(f"Headers: {dict(response.headers)}\n")
                        f.write(f"Body: {response.text}")
                    else:
                        formatted_json = json.dumps(response.json(), indent=2)
                        f.write(formatted_json)
                except Exception as e:
                    print(f"Error saving debug file: {e}")
                    f.write(response.text)

            # Raise for status before parsing
            response.raise_for_status()

            # Parse the response into Pydantic model
            try:
                firecrawl_response = FirecrawlResponse.model_validate_json(response.text)
                if not firecrawl_response.success:
                    raise ValueError(f"Firecrawl returned error: {response.text}")
                return firecrawl_response.data.extract.articles
            except Exception as e:
                print(f"Error parsing response: {e}")
                print("Raw response:", response.text[:500])
                raise ValueError(f"Failed to parse Firecrawl response: {str(e)}")
                
        except requests.exceptions.RequestException as e:
            print(f"Request error: {type(e).__name__}: {str(e)}")
            raise ValueError(f"Failed to make request to Firecrawl: {str(e)}")
        except Exception as e:
            print(f"Unexpected error: {type(e).__name__}: {str(e)}")
            raise

    async def scrape_liveblog_content(self, url: str) -> str:
        """
        Scrape content from a liveblog article using Playwright for dynamic content.
        Returns the extracted text content or raises ValueError if extraction fails.
        """
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_viewport_size({"width": 1920, "height": 1080})
                
                # Navigate to the URL and wait for content
                await page.goto(url)
                
                # Wait for the main content container
                await page.wait_for_selector('.wysiwyg-content', timeout=30000)
                
                # Click "Read more" button if it exists
                try:
                    read_more_button = await page.wait_for_selector('button:has-text("Read more")', timeout=5000)
                    if read_more_button:
                        await read_more_button.click()
                        await page.wait_for_timeout(1000)
                except:
                    pass
                
                text_content = []
                
                # Get the main headline/title
                main_title = await page.query_selector('h1')
                if main_title:
                    title_text = await main_title.text_content()
                    text_content.append(f"# {title_text.strip()}\n")
                
                # Get the summary content
                summary = await page.query_selector('.wysiwyg-content')
                if summary:
                    summary_text = await summary.text_content()
                    if summary_text.strip():
                        text_content.append("SUMMARY:")
                        text_content.append(summary_text.strip())
                
                # Get all liveblog entries
                entries = await page.query_selector_all('.timeline-item')
                
                for entry in entries:
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
                            if header_text.strip():
                                text_content.append(f"\n## {header_text.strip()}\n")
                        
                        # Get paragraphs
                        paragraphs = await content.query_selector_all('p')
                        for p in paragraphs:
                            p_text = await p.text_content()
                            if p_text.strip():
                                text_content.append(p_text.strip())
                        
                        # Get list items
                        list_items = await content.query_selector_all('li')
                        for item in list_items:
                            item_text = await item.text_content()
                            if item_text.strip():
                                text_content.append(f"• {item_text.strip()}")
                
                # If no timeline items found, try to get content from wysiwyg sections
                if not entries:
                    wysiwyg_content = await page.query_selector_all('.wysiwyg-content h2, .wysiwyg-content h3, .wysiwyg-content p, .wysiwyg-content li')
                    for content in wysiwyg_content:
                        tag_name = await content.evaluate('element => element.tagName.toLowerCase()')
                        content_text = await content.text_content()
                        
                        if content_text.strip():
                            if tag_name in ['h2', 'h3']:
                                text_content.append(f"\n## {content_text.strip()}\n")
                            elif tag_name == 'li':
                                text_content.append(f"• {content_text.strip()}")
                            else:
                                text_content.append(content_text.strip())
                
                # Remove duplicate paragraphs that are next to each other
                filtered_content = []
                prev_content = None
                for content in text_content:
                    if content != prev_content:
                        filtered_content.append(content)
                    prev_content = content
                
                return self._filter_content('\n\n'.join(filtered_content))
                
            finally:
                await browser.close()

    async def scrape_article_content(self, url: str) -> str:
        """
        Scrape the main content from a news article URL.
        Returns the extracted text content or raises ValueError if extraction fails.
        """
        try:
            # Check if it's a liveblog
            if 'liveblog' in url.lower():
                return await self.scrape_liveblog_content(url)

            # Regular article scraping logic continues...
            response = requests.get(url, headers=self.scraper_headers, timeout=30)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove unwanted elements
            for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'iframe']):
                element.decompose()
            
            text_content = []
            
            # Get the main headline/title
            main_title = soup.find('h1')
            if main_title:
                title_text = main_title.get_text()
                text_content.append(f"# {title_text.strip()}\n")
            
            # Special handling for Al Jazeera
            if 'aljazeera.com' in url:
                content = soup.select_one('[class*="wysiwyg"]')
                if content:
                    # Try to click "Read more" button if it exists (for liveblogs)
                    if 'liveblog' in url.lower():
                        text_content.append("SUMMARY:")
                        summary_text = content.get_text().strip()
                        if summary_text:
                            text_content.append(summary_text)
                        
                        # Get all liveblog entries
                        entries = soup.select('.timeline-item')
                        for entry in entries:
                            # Extract timestamp
                            timestamp = entry.select_one('.timeline-item__time')
                            if timestamp:
                                time_text = timestamp.get_text()
                                text_content.append(f"\n[{time_text.strip()}]\n")
                            
                            # Extract content
                            entry_content = entry.select_one('.timeline-item__content')
                            if entry_content:
                                # Get headers
                                headers = entry_content.find_all(['h2', 'h3', 'h4'])
                                for header in headers:
                                    header_text = header.get_text()
                                    text_content.append(f"\n## {header_text.strip()}\n")
                                
                                # Get paragraphs
                                paragraphs = entry_content.find_all('p')
                                for p in paragraphs:
                                    p_text = p.get_text()
                                    if p_text.strip():
                                        text_content.append(p_text.strip())
                                
                                # Get list items
                                list_items = entry_content.find_all('li')
                                for item in list_items:
                                    item_text = item.get_text()
                                    if item_text.strip():
                                        text_content.append(f"• {item_text.strip()}")
                    else:
                        # Regular article handling
                        elements = content.find_all(['h2', 'h3', 'p', 'li'])
                        for element in elements:
                            if element.name in ['h2', 'h3']:
                                text_content.append(f"\n## {element.get_text().strip()}\n")
                            elif element.name == 'li':
                                text_content.append(f"• {element.get_text().strip()}")
                            else:
                                text_content.append(element.get_text().strip())
                    
                    return self._filter_content('\n\n'.join(text for text in text_content if text.strip()))
            
            # Fallback to general selectors
            content_selectors = [
                '[class*="wysiwyg"]',
                'article',
                '[role="article"]',
                '.article-content',
                '.article-body',
                '.story-content',
                '#article-body',
                '.post-content',
                'main'
            ]
            
            content = None
            for selector in content_selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    content = content_element
                    break
            
            if not content:
                content = soup.find('body')
            
            if not content:
                raise ValueError("Could not find article content")
            
            elements = content.find_all(['h2', 'h3', 'p'])
            for element in elements:
                if element.name in ['h2', 'h3']:
                    text_content.append(f"\n## {element.get_text().strip()}\n")
                else:
                    text_content.append(element.get_text().strip())
            
            final_content = '\n\n'.join(text for text in text_content if text.strip())
            
            if not final_content:
                raise ValueError("No text content found in article")
            
            return self._filter_content(final_content)
            
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Failed to fetch article: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to extract article content: {str(e)}")

from pydantic import BaseModel
import requests
from typing import List
import json
from datetime import datetime

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
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.headers = {
            # "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

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

        response = requests.post(self.api_url, json=payload, headers=self.headers)
        
        # Save raw response to debug log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f'firecrawl_debug_{timestamp}.json', 'w') as f:
            try:
                formatted_json = json.dumps(response.json(), indent=2)
                f.write(formatted_json)
            except:
                f.write(response.text)

        # Parse the response into Pydantic model
        try:
            firecrawl_response = FirecrawlResponse.model_validate_json(response.text)
            return firecrawl_response.data.extract.articles
        except Exception as e:
            print(f"Error parsing response: {e}")
            print("Raw response:", response.text[:500])
            return []

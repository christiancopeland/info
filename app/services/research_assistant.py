from typing import List, Dict, Any, Optional
import httpx
import json
import asyncio
from pydantic import BaseModel

class Message(BaseModel):
    role: str
    content: str

class ResearchAssistant:
    """Basic Research Assistant implementation with chat and structured output support"""
    
    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url
        self.chat_endpoint = f"{api_url}/api/chat"
        self.model = "llama3.2-vision"  # Default model
        print(f"ResearchAssistant initialized with endpoint: {self.chat_endpoint}")
        
    async def chat(self, messages: List[Message], stream: bool = True) -> Any:
        """Basic chat functionality with streaming support"""
        print(f"Starting chat with messages: {messages}")  # Debug log
        
        payload = {
            "model": self.model,
            "messages": [msg.model_dump() for msg in messages],
            "stream": stream
        }
        print(f"Sending payload: {payload}")  # Debug log
        
        async with httpx.AsyncClient(timeout=30.0) as client:  # Increased timeout
            if stream:
                try:
                    async with client.stream('POST', self.chat_endpoint, json=payload) as response:
                        if response.status_code != 200:
                            error_msg = f"Ollama server error: {response.status_code}"
                            try:
                                error_data = await response.json()
                                error_msg += f" - {error_data.get('error', 'Unknown error')}"
                            except:
                                pass
                            raise Exception(error_msg)
                        
                        print(f"Got response with status: {response.status_code}")  # Debug log
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    chunk = json.loads(line)
                                    print(f"Processing chunk: {chunk}")  # Debug log
                                    if chunk.get("done", False):
                                        yield {
                                            "type": "done",
                                            "message": {"content": ""}
                                        }
                                    else:
                                        content = chunk.get("message", {}).get("content", "")
                                        print(f"Yielding content: {content}")  # Debug log
                                        yield {
                                            "type": "chunk",
                                            "message": {
                                                "role": "assistant",
                                                "content": content
                                            }
                                        }
                                except json.JSONDecodeError as e:
                                    print(f"JSON decode error: {e} for line: {line}")  # Debug log
                                    continue
                except httpx.TimeoutException as e:
                    error_msg = "Connection timeout while connecting to Ollama server. Please ensure the server is running and accessible."
                    print(f"Timeout error: {error_msg}")  # Debug log
                    raise Exception(error_msg) from e
                except Exception as e:
                    error_msg = f"Stream error: {str(e)}"
                    print(error_msg)  # Debug log
                    raise Exception(error_msg) from e
            else:
                # For non-streaming, yield a single response
                try:
                    response = await client.post(self.chat_endpoint, json=payload)
                    if response.status_code != 200:
                        error_msg = f"Ollama server error: {response.status_code}"
                        try:
                            error_data = response.json()
                            error_msg += f" - {error_data.get('error', 'Unknown error')}"
                        except:
                            pass
                        raise Exception(error_msg)
                    
                    response_data = response.json()
                    yield {
                        "type": "chunk",
                        "message": {
                            "role": "assistant",
                            "content": response_data.get("message", {}).get("content", "")
                        }
                    }
                    yield {
                        "type": "done",
                        "message": {"content": ""}
                    }
                except httpx.TimeoutException as e:
                    error_msg = "Connection timeout while connecting to Ollama server. Please ensure the server is running and accessible."
                    print(f"Timeout error: {error_msg}")  # Debug log
                    raise Exception(error_msg) from e
                except Exception as e:
                    error_msg = f"Request error: {str(e)}"
                    print(error_msg)  # Debug log
                    raise Exception(error_msg) from e

    async def structured_chat(self, 
                            messages: List[Message], 
                            output_schema: Dict[str, Any]) -> Any:
        """
        Chat with structured output based on provided JSON schema
        """
        payload = {
            "model": self.model,
            "messages": [msg.model_dump() for msg in messages],
            "stream": False,  # Structured output requires non-streaming
            "format": output_schema,
            "options": {
                "temperature": 0  # Lower temperature for more consistent structured output
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.chat_endpoint, json=payload)
            result = response.json()
            
            # Extract the JSON content from the assistant's message
            if result.get("message", {}).get("content"):
                try:
                    return json.loads(result["message"]["content"])
                except json.JSONDecodeError:
                    return result["message"]["content"]
            return result
        
    async def generate_analysis_from_news_article(self, messages: List[Message]) -> Dict[str, Any]:
        """Generate analysis for a news article"""

        output_schema = {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "A detailed analysis with Key Points and Analysis sections"
                }
            },
            "required": ["analysis"]
        }

        # Add system message to guide the model
        system_message = Message(
            role="system",
            content="""Generate a comprehensive analysis with investigative journalism in 
            mind. Include the following sections:
            1. Key Points: Bullet points of main findings
            2. Analysis: Detailed examination of implications
            Format with markdown and ensure all claims are supported by document content."""
        )
        
        messages = [system_message] + messages
        try:
            print("Generating analysis with messages:", messages)  # Debug log
            
            # Make sure we're using the right model and settings for analysis
            response = await self.structured_chat(messages, output_schema)
            
            print("Raw response from model:", response)  # Debug log
            
            # Make sure we get a proper response
            if not response or not isinstance(response, dict) or 'content' not in response:
                print("Invalid response format:", response)  # Debug log
                raise ValueError("Invalid response from language model")

            return {
                "analysis": response['content']
            }

        except Exception as e:
            print(f"Error generating analysis: {str(e)}")  # Debug log
            raise
        
    async def generate_knowledge_graph_from_news_article(self, messages: List[Message]) -> Any:
        """
        Generate a knowledge graph from a given news article
        """
        output_schema = {
            "type": "object",
            "properties": {
                "graph": {
                    "type": "string",
                    "description": "A knowledge graph with Entities, Relationships, and Context sections"
                }
            },
            "required": ["graph"]
        }
        
        # Add system message to guide the model
        system_message = Message(
            role="system",
            content="""Create a knowledge graph with the following sections:
            1. Entities: List and describe key entities
            2. Relationships: Describe connections between entities
            3. Context: Provide relevant background information
            Format the output as a markdown document with clear section headers."""
        )
        
        messages = [system_message] + messages
        return await self.structured_chat(messages, output_schema)

    async def generate_analysis_from_document(self, messages: List[Message]) -> Any:
        """
        Generate an analysis of a given document
        """
        output_schema = {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "A detailed analysis with Key Points and Analysis sections"
                }
            },
            "required": ["analysis"]
        }
        
        # Add system message to guide the model
        system_message = Message(
            role="system",
            content="""Generate a comprehensive analysis with investigative journalism in mind. Include the following sections:
            1. Key Points: Bullet points of main findings
            2. Analysis: Detailed examination of implications
            Format with markdown and ensure all claims are supported by document content."""
        )
        
        messages = [system_message] + messages
        return await self.structured_chat(messages, output_schema)

    async def generate_knowledge_graph_from_document(self, messages: List[Message]) -> Any:
        """
        Generate a knowledge graph from a given document
        """
        output_schema = {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"}
                        }
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "relationship": {"type": "string"}
                        }
                    }
                },
                "context": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": ["entities", "relationships"]
        }
        
        # Add system message to guide the model
        system_message = Message(
            role="system",
            content="""Create a structured knowledge graph with:
            1. Entities: Key actors, organizations, policies, and concepts
            2. Relationships: Specific connections between entities
            3. Context: Background information and implications
            Ensure all elements are directly supported by the document."""
        )
        
        messages = [system_message] + messages
        return await self.structured_chat(messages, output_schema)
    



# Example usage:
async def example_usage():
    assistant = ResearchAssistant()
    
    # Basic chat example
    messages = [
        Message(role="user", content="What is the capital of France?")
    ]
    
    # Streaming chat
    async for chunk in assistant.chat(messages):
        if chunk.get("message", {}).get("content"):
            print(chunk["message"]["content"], end="")
    print()
    
    # Structured output example
    schema = {
        "type": "object",
        "properties": {
            "capital": {
                "type": "string"
            },
            "country": {
                "type": "string"
            },
            "population": {
                "type": "integer"
            }
        },
        "required": ["capital", "country"]
    }
    
    result = await assistant.structured_chat(messages, schema)
    print(f"Structured result: {result}")

if __name__ == "__main__":
    asyncio.run(example_usage())

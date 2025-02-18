from typing import List, Dict, Any, Optional
import httpx
import json
import asyncio

class ResearchAssistant:
    """Basic Research Assistant implementation with chat and structured output support"""
    
    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url
        self.chat_endpoint = f"{api_url}/api/chat"
        self.model = "qwen2.5-coder:14b"  # Default model
        print(f"ResearchAssistant initialized with endpoint: {self.chat_endpoint}")
        
    async def chat(self, messages: List[Dict[str, str]], stream: bool = True) -> Any:
        """Basic chat functionality with streaming support"""
        print(f"Starting chat with messages: {messages}")  # Debug log
        
        payload = {
            "model": self.model,
            "messages": messages,
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
                            messages: List[Dict[str, str]], 
                            output_schema: Dict[str, Any]) -> Any:
        """Chat with structured output based on provided JSON schema"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": output_schema,
            "options": {
                "temperature": 0,  # Lower temperature for more consistent structured output
                "num_ctx": 8192
            }
        }
        
        print(f"Sending payload to LLM: {payload}")
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:  # Increase client timeout
            try:
                response = await client.post(self.chat_endpoint, json=payload)
                print(f"Raw response status: {response.status_code}")
                
                if response.status_code == 499:  # Client closed connection
                    raise ValueError("LLM server timeout - VRAM issue detected")
                elif response.status_code != 200:
                    raise ValueError(f"LLM server error: {response.status_code}")
                
                result = response.json()
                print(f"Raw response JSON: {result}")
                
                if result.get("message", {}).get("content"):
                    content = result["message"]["content"]
                    print(f"Extracted content: {content}")
                    
                    try:
                        parsed_content = json.loads(content)
                        print(f"Parsed JSON content: {parsed_content}")
                        return parsed_content
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}. Returning raw content")
                        return {"analysis": content}
                
                print(f"No message content found in response. Returning full result")
                return result
                
            except httpx.TimeoutException:
                raise ValueError("Request timed out. The LLM server might be experiencing high load or VRAM issues.")
            except Exception as e:
                raise ValueError(f"Error communicating with LLM server: {str(e)}")

    async def generate_analysis_from_news_article(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Generate analysis for a news article"""
        try:
            # Add system message at the beginning of the messages list
            system_message = {
                "role": "system",
                "content": """You are an expert journalist and analyst. Generate a comprehensive 
                analysis of the provided news article. Your analysis should be detailed and 
                thorough, covering:
                1. Key Points: Main findings and claims from the article
                2. Sources & Citations: Analysis of the sources used and their credibility
                3. Context: Relevant background information and historical context
                4. Critical Analysis: Examination of potential biases and missing information
                5. Further Research: Related topics and angles for additional investigation

                
                IMPORTANT: Your response must be detailed and at least 500 words long. Format your response in markdown with clear section headers. Ensure all 
                analysis is based on the article content provided."""
            }
            
            # Ensure messages is a list of dictionaries
            if isinstance(messages, str):
                try:
                    messages = json.loads(messages)
                except json.JSONDecodeError:
                    messages = [{"role": "user", "content": messages}]
            elif not isinstance(messages, list):
                messages = [{"role": "user", "content": str(messages)}]
            
            all_messages = [system_message] + messages
            
            max_retries = 3
            retry_delay = 5  # seconds
            
            for attempt in range(max_retries):
                try:
                    response = await self.structured_chat(
                        messages=all_messages,
                        output_schema={
                            "type": "object",
                            "properties": {
                                "analysis": {
                                    "type": "string",
                                    "description": "A detailed markdown-formatted analysis of the article (minimum 500 words). Structure your response with the following sections: ## Key Points, ## Sources & Citations, ## Context, ## Critical Analysis, ## Further Research."
                                }
                            },
                            "required": ["analysis"]
                        }
                    )
                    
                    print(f"Response from structured_chat (attempt {attempt + 1}): {response}")
                    
                    if isinstance(response, dict) and "analysis" in response:
                        analysis_content = response["analysis"]
                        print(f"Analysis content length: {len(analysis_content)}")
                        print(f"Analysis content preview: {analysis_content[:200]}")
                        
                        if len(analysis_content) < 100:
                            raise ValueError(f"Analysis response too short. Response: {analysis_content}")
                        return response
                    
                    raise ValueError(f"Unexpected response format: {response}")
                    
                except ValueError as e:
                    if "VRAM issue" in str(e) and attempt < max_retries - 1:
                        print(f"VRAM issue detected, retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                    raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"Error on attempt {attempt + 1}: {str(e)}, retrying...")
                        await asyncio.sleep(retry_delay)
                        continue
                    raise

        except Exception as e:
            print(f"Error generating analysis: {str(e)}")
            raise
        
    async def generate_knowledge_graph_from_news_article(self, messages: List[Dict[str, str]]) -> Any:
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
        system_message = {
            "role": "system",
            "content": """Create a knowledge graph with the following sections:
            1. Entities: List and describe key entities
            2. Relationships: Describe connections between entities
            3. Context: Provide relevant background information
            Format the output as a markdown document with clear section headers."""
        }
        
        messages = [system_message] + messages
        return await self.structured_chat(messages, output_schema)

    async def generate_analysis_from_document(self, messages: List[Dict[str, str]]) -> Any:
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
        system_message = {
            "role": "system",
            "content": """Generate a comprehensive analysis with investigative journalism in mind. Include the following sections:
            1. Key Points: Bullet points of main findings
            2. Analysis: Detailed examination of implications
            Format with markdown and ensure all claims are supported by document content."""
        }
        
        messages = [system_message] + messages
        return await self.structured_chat(messages, output_schema)

    async def generate_knowledge_graph_from_document(self, messages: List[Dict[str, str]]) -> Any:
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
        system_message = {
            "role": "system",
            "content": """Create a structured knowledge graph with:
            1. Entities: Key actors, organizations, policies, and concepts
            2. Relationships: Specific connections between entities
            3. Context: Background information and implications
            Ensure all elements are directly supported by the document."""
        }
        
        messages = [system_message] + messages
        return await self.structured_chat(messages, output_schema)
    



# Example usage:
async def example_usage():
    assistant = ResearchAssistant()
    
    # Basic chat example
    messages = [
        {"role": "user", "content": "What is the capital of France?"}
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

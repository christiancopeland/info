from typing import Dict, List, Optional, Tuple, Union
import PyPDF2
from io import BytesIO
import logging
import backoff  # Add this to requirements.txt
from tenacity import retry, stop_after_attempt, wait_exponential  # Add this to requirements.txt
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
import asyncio
import uuid
import redis
import textwrap
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import time
from datetime import datetime
from uuid import UUID
import gc
from sqlalchemy import text


logger = logging.getLogger(__name__)

class DocumentProcessingError(Exception):
    """Base exception for document processing errors"""
    pass

class EmbeddingGenerationError(DocumentProcessingError):
    """Exception raised for errors during embedding generation"""
    pass

@dataclass
class ProcessingStats:
    """Track document processing statistics"""
    total_pages: int = 0
    processed_pages: int = 0
    failed_pages: int = 0
    total_chunks: int = 0
    processed_chunks: int = 0
    failed_chunks: int = 0

class ConcurrentProcessingError(DocumentProcessingError):
    """Exception for concurrent processing failures"""
    def __init__(self, message: str, failed_items: List[Tuple[int, Exception]]):
        self.failed_items = failed_items
        super().__init__(f"{message} ({len(failed_items)} failures)")

class DocumentProcessor:
    """Handles document processing and metadata extraction"""
    
    def __init__(self):
        # Initialize Qdrant client
        self.qdrant = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )
        
        # Initialize Redis client
        self.redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=0
        )
        
        # Constants for text processing
        self.CHUNK_SIZE = 250  # Set fixed chunk size
        self.CHUNK_OVERLAP = 50  # Set fixed overlap
        MAX_CHUNKS = 1000
        
        # Ensure collection exists
        self._init_collection()
        
        # Retry configuration
        self.max_retries = 3
        self.max_backoff = 60  # Maximum backoff time in seconds
        
        # Add thread pool for concurrent processing
        self.max_workers = os.getenv("MAX_PROCESSING_THREADS", 1)
        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Chunk processing configuration
        self.batch_size = 2
        
        self.processing_stats = ProcessingStats()
        
        # Add timeout configurations
        self.page_timeout = int(os.getenv("PAGE_PROCESSING_TIMEOUT", 30))  # seconds
        self.chunk_timeout = int(os.getenv("CHUNK_PROCESSING_TIMEOUT", 60))  # seconds
        
        # Add memory-related constraints
        self.max_document_size = 5 * 1024 * 1024  # 5MB limit
        self.max_concurrent_chunks = 5  # Limit concurrent chunk processing
    
    def _init_collection(self):
        """Initialize Qdrant collection by recreating it each time"""
        try:
            # Drop collection if it exists
            try:
                self.qdrant.delete_collection("documents")
                logger.info("Deleted existing 'documents' collection")
            except Exception as e:
                logger.debug(f"Collection might not exist, continuing: {str(e)}")
            
            # Create new collection
            self.qdrant.create_collection(
                collection_name="documents",
                vectors_config=VectorParams(
                    size=3072,  # text-embedding-3-large dimension size
                    distance=Distance.COSINE
                )
            )
            logger.info("Created new Qdrant collection: documents")
            
        except Exception as e:
            logger.error(f"Error initializing collection: {str(e)}")
            raise

    def _sanitize_text(self, text: str) -> str:
        """Remove null bytes and other problematic characters"""
        if not text:
            return ""
            
        try:
            # Remove null bytes
            cleaned = text.replace('\x00', '')
            
            # Replace other potentially problematic characters
            cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')
            
            # Ensure the text is valid UTF-8
            cleaned = cleaned.encode('utf-8', errors='ignore').decode('utf-8')
            
            return cleaned
        except Exception as e:
            logger.error(f"Error sanitizing text: {str(e)}")
            return ""

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks with memory optimization"""
        # Sanitize input text first
        text = self._sanitize_text(text)
        logger.info(f"Starting text chunking for {len(text)} characters")
        chunks = []
        start = 0
        text_length = len(text)
        last_position = -1  # Track last position to detect loops
        
        # Constants
        self.CHUNK_SIZE = 250  # Set fixed chunk size
        self.CHUNK_OVERLAP = 50  # Set fixed overlap
        MAX_CHUNKS = 1000
        
        try:
            while start < text_length:
                if len(chunks) >= MAX_CHUNKS:
                    logger.error(f"Exceeded maximum chunk limit of {MAX_CHUNKS}. Text length: {text_length}")
                    raise ValueError(f"Document produced too many chunks (>{MAX_CHUNKS})")
                
                # Calculate end position
                end = min(start + self.CHUNK_SIZE, text_length)
                current_chunk = text[start:end]
                
                # Find break point only if we're not at the end of text
                if end < text_length:
                    break_chars = ["\n\n", ".", "!", "?"]
                    last_break = -1
                    for char in break_chars:
                        last_break = current_chunk.rfind(char)
                        if last_break != -1:
                            break
                    
                    if last_break != -1:
                        end = start + last_break + 1
                        current_chunk = text[start:end]
                
                # Sanity check chunk size
                if len(current_chunk) < 10:  # Minimum reasonable chunk size
                    logger.warning(f"Skipping very small chunk of size {len(current_chunk)} at position {start}")
                    start = end  # Move to next chunk without overlap
                    continue
                
                # Log chunk creation with more details
                logger.info(f"Creating chunk {len(chunks) + 1}: {len(current_chunk)} chars, Position: {start}-{end}")
                
                chunks.append(current_chunk)
                
                # Calculate next start position
                new_start = end - self.CHUNK_OVERLAP
                
                # Ensure we're moving forward by at least CHUNK_SIZE/2
                if new_start <= start or (new_start - start) < (self.CHUNK_SIZE / 2):
                    new_start = start + max(self.CHUNK_SIZE // 2, end - start)
                    logger.info(f"Forcing forward movement from {start} to {new_start}")
                
                start = min(new_start, text_length)  # Ensure we don't go past the end
                
                # Log progress periodically
                if len(chunks) % 10 == 0:
                    logger.info(f"Created {len(chunks)} chunks so far...")
                    logger.debug(f"Last chunk details: Size={len(current_chunk)}, Start={start}, End={end}, Next start: {new_start}")
                
                # Clear current_chunk from memory
                del current_chunk
            
            logger.info(f"Chunking completed. Created {len(chunks)} chunks. Average chunk size: {sum(len(c) for c in chunks)/len(chunks):.1f} chars")
            return chunks
            
        except Exception as e:
            logger.error(f"Error during text chunking: {str(e)}")
            raise
    
    @staticmethod
    def should_retry_exception(exception):
        """Predicate function to determine if we should retry on this exception"""
        return isinstance(exception, (APIError, RateLimitError, APIConnectionError))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=should_retry_exception.__func__,
        before_sleep=lambda retry_state: logger.info(f"Retrying after {retry_state.outcome.exception()}")
    )
    async def _generate_embedding(self, text: str, openai_client: OpenAI) -> List[float]:
        """Generate embeddings using OpenAI's API with detailed logging"""
        start_time = time.time()
        logger.info(f"Starting embedding generation for text of length {len(text)}")
        
        try:
            response = openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=text
            )
            duration = time.time() - start_time
            logger.info(f"Embedding generated successfully in {duration:.2f}s")
            return response.data[0].embedding
            
        except RateLimitError as e:
            logger.warning(f"Rate limit hit after {time.time() - start_time:.2f}s: {str(e)}")
            raise EmbeddingGenerationError(f"Rate limit exceeded: {str(e)}")
            
        except APIConnectionError as e:
            logger.warning(f"API connection error after {time.time() - start_time:.2f}s: {str(e)}")
            raise EmbeddingGenerationError(f"Connection error: {str(e)}")
            
        except APIError as e:
            logger.error(f"OpenAI API error after {time.time() - start_time:.2f}s: {str(e)}")
            raise EmbeddingGenerationError(f"API error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error generating embedding after {time.time() - start_time:.2f}s: {str(e)}")
            raise EmbeddingGenerationError(f"Unexpected error: {str(e)}")

    @contextmanager
    def _track_processing_time(self, operation: str):
        """Context manager to track processing time and log warnings for slow operations"""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            if duration > self.page_timeout and operation == "page":
                logger.warning(f"Page processing exceeded timeout: {duration:.2f}s")
            elif duration > self.chunk_timeout and operation == "chunk":
                logger.warning(f"Chunk processing exceeded timeout: {duration:.2f}s")

    async def process_pdf(self, file: BytesIO, client_id: str) -> Dict:
        """Main PDF processing function with comprehensive logging"""
        start_time = time.time()
        logger.info("=== Starting PDF Processing ===")
        
        try:
            # API key validation
            logger.info(f"Validating API key for client_id: {client_id}")
            api_key = self.redis.get(f"api_key:{client_id}")
            
            if not api_key:
                logger.error("No API key found in Redis")
                raise DocumentProcessingError("No OpenAI API key found for this session")
            
            try:
                api_key_str = api_key.decode()
                logger.info("API key retrieved and decoded successfully")
            except (AttributeError, UnicodeDecodeError) as e:
                logger.error(f"API key decode error: {str(e)}")
                raise DocumentProcessingError("Invalid API key format in session")
            
            # Initialize OpenAI client
            openai_client = OpenAI(api_key=api_key_str)
            logger.info("OpenAI client initialized")
            
            # Initialize PDF reader
            pdf_reader = PyPDF2.PdfReader(file)
            doc_id = str(uuid.uuid4())
            logger.info(f"PDF reader initialized. Document ID: {doc_id}")
            
            # Extract metadata and content
            logger.info("Starting metadata and content extraction")
            metadata = await self._extract_metadata_async(pdf_reader)
            logger.info("Starting text extraction")
            content = await self._extract_text_async(pdf_reader)
            
            # Process chunks
            logger.info("Starting chunk processing")
            chunks = self._chunk_text(content)
            logger.info(f"Created {len(chunks)} chunks for processing")
            
            # Process chunks sequentially
            chunk_results = []
            chunk_logs = []
            
            for index, chunk in enumerate(chunks):
                chunk_start_time = time.time()
                logger.info(f"Processing chunk {index + 1}/{len(chunks)}")
                
                try:
                    # Sanitize chunk before processing
                    sanitized_chunk = self._sanitize_text(chunk)
                    embedding = await self._generate_embedding(sanitized_chunk, openai_client)
                    chunk_id = await self._store_chunk(
                        doc_id=doc_id,
                        chunk_id=index,
                        content=sanitized_chunk,
                        embedding=embedding,
                        metadata=metadata
                    )
                    chunk_results.append(chunk_id)
                    
                    # Log successful chunk processing
                    chunk_time = time.time() - chunk_start_time
                    chunk_log = {
                        "chunk_number": index,
                        "processing_time": f"{chunk_time:.2f}s",
                        "status": "success",
                        "chunk_size": len(chunk),
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.info(f"Chunk processing log: {chunk_log}")
                    chunk_logs.append(chunk_log)
                    
                except Exception as e:
                    chunk_time = time.time() - chunk_start_time
                    chunk_log = {
                        "chunk_number": index,
                        "processing_time": f"{chunk_time:.2f}s",
                        "status": "failed",
                        "error": str(e),
                        "chunk_size": len(chunk),
                        "timestamp": datetime.now().isoformat()
                    }
                    logger.error(f"Chunk processing log: {chunk_log}")
                    chunk_logs.append(chunk_log)

            # Calculate total processing time
            total_time = time.time() - start_time
            logger.info(f"=== PDF Processing Completed in {total_time:.2f}s ===")

            return {
                "doc_id": doc_id,
                "chunk_ids": chunk_results,
                "metadata": metadata,
                "processing_stats": asdict(self.processing_stats),
                "processing_metrics": {
                    "total_processing_time": total_time,
                    "chunk_processing_logs": chunk_logs
                },
                "failures": {
                    "chunks": [log for log in chunk_logs if log["status"] == "failed"]
                },
                "status": "processed"
            }

        except Exception as e:
            total_time = time.time() - start_time
            logger.error(f"=== PDF Processing Failed after {total_time:.2f}s: {str(e)} ===")
            raise DocumentProcessingError(
                f"Processing failed: {str(e)}",
                {
                    "processing_stats": asdict(self.processing_stats),
                    "processing_time": total_time
                }
            )

    async def _extract_text_async(self, pdf_reader) -> str:
        """Extract text from PDF pages with detailed progress logging"""
        text_parts = []
        total_pages = len(pdf_reader.pages)
        logger.info(f"Starting text extraction for {total_pages} pages")
        
        # Process pages in smaller batches
        batch_size = 3
        
        for i in range(0, total_pages, batch_size):
            batch_start = time.time()
            current_batch = i // batch_size + 1
            total_batches = (total_pages + batch_size - 1) // batch_size
            
            logger.info(f"Processing batch {current_batch}/{total_batches} (pages {i+1}-{min(i+batch_size, total_pages)})")
            
            batch_pages = list(pdf_reader.pages[i:i + batch_size])
            batch_tasks = [
                asyncio.to_thread(self._extract_page_text, page)
                for page in batch_pages
            ]
            
            try:
                batch_results = await asyncio.gather(*batch_tasks)
                text_parts.extend(batch_results)
                
                batch_time = time.time() - batch_start
                logger.info(f"Batch {current_batch} completed in {batch_time:.2f}s")
                
            except Exception as e:
                logger.error(f"Error in batch {current_batch}: {str(e)}")
                continue
            
            # Small delay between batches
            await asyncio.sleep(0.05)
    
        final_text = "\n".join(filter(None, text_parts))
        logger.info(f"Text extraction completed. Extracted {len(final_text)} characters")
        return final_text

    def _extract_page_text(self, page) -> str:
        """Extract text from a single page with timing and sanitization"""
        start_time = time.time()
        try:
            page_text = page.extract_text()
            duration = time.time() - start_time
            
            # Sanitize the extracted text
            sanitized_text = self._sanitize_text(page_text)
            
            if sanitized_text:
                logger.info(f"Page extracted and sanitized {len(sanitized_text)} chars in {duration:.2f}s")
            else:
                logger.warning(f"Page extracted no valid text in {duration:.2f}s")
                
            return sanitized_text
            
        except Exception as e:
            logger.error(f"Page extraction failed after {time.time() - start_time:.2f}s: {str(e)}")
            return ""

    async def _chunk_text_streaming(self, text: str):
        """Generator that yields chunks with controlled memory usage"""
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + self.CHUNK_SIZE
            chunk = text[start:end]
            
            # Find break point
            if end < text_length:
                break_chars = ["\n\n", ".", "!", "?"]
                for char in break_chars:
                    last_break = chunk.rfind(char)
                    if last_break != -1:
                        end = start + last_break + 1
                        chunk = text[start:end]
                        break
            
            yield chunk
            start = end - self.CHUNK_OVERLAP
            
            # Cleanup after yielding
            del chunk
            if start % (self.CHUNK_SIZE * 10) == 0:
                gc.collect()

    def _extract_page_text_with_timeout(self, page) -> str:
        """Extract text from a page with timeout"""
        with self._track_processing_time("page"):
            return self._extract_page_text(page)

    async def _process_chunk_batch(
        self, 
        batch: List[str], 
        start_idx: int,
        doc_id: str,
        metadata: Dict,
        openai_client: OpenAI
    ) -> List[Tuple[int, Union[str, Exception]]]:
        """Process a batch of chunks with enhanced error handling"""
        tasks = []
        for chunk_idx, chunk in enumerate(batch, start=start_idx):
            task = self._process_chunk_with_timeout(
                chunk, chunk_idx, doc_id, metadata, openai_client
            )
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_chunk_with_timeout(self, *args, **kwargs) -> Tuple[int, Union[str, Exception]]:
        """Process a single chunk with timeout and error handling"""
        chunk_idx = args[1]  # Index is the second argument
        try:
            with self._track_processing_time("chunk"):
                result = await self._process_chunk(*args, **kwargs)
                return chunk_idx, result
        except Exception as e:
            logger.error(f"Chunk {chunk_idx} processing failed: {str(e)}")
            return chunk_idx, e

    def _extract_page_text(self, page) -> str:
        """Extract text from a single page with validation and timeout"""
        try:
            # Add timeout to page extraction
            start_time = time.time()
            page_text = page.extract_text()
            
            # Log slow page extractions
            processing_time = time.time() - start_time
            if processing_time > 1.0:  # Log if page takes more than 1 second
                logger.warning(f"Slow page extraction: {processing_time:.2f} seconds")
            
            if not page_text:
                logger.warning("Empty text extracted from page")
                return ""
                
            return page_text
            
        except Exception as e:
            logger.error(f"Error extracting text: {str(e)}")
            return ""

    async def _process_chunk(self, chunk: str, index: int, doc_id: str, 
                           metadata: Dict, openai_client: OpenAI) -> Optional[str]:
        """Process a single chunk with retries"""
        try:
            # Generate embedding concurrently
            embedding = await self._generate_embedding(chunk, openai_client)
            
            # Store in Qdrant
            chunk_id = await self._store_chunk(
                doc_id=doc_id,
                chunk_id=index,
                content=chunk,
                embedding=embedding,
                metadata=metadata
            )
            
            return chunk_id
            
        except Exception as e:
            logger.error(f"Error processing chunk {index}: {str(e)}")
            return None

    def _extract_metadata(self, pdf_reader: PyPDF2.PdfReader) -> Dict:
        """Extract metadata with validation"""
        try:
            metadata = {
                "num_pages": len(pdf_reader.pages),
                "title": pdf_reader.metadata.get('/Title', 'Untitled'),
                "author": pdf_reader.metadata.get('/Author', 'Unknown'),
                "creation_date": pdf_reader.metadata.get('/CreationDate', 'Unknown'),
            }
            
            # Validate metadata
            for key, value in metadata.items():
                if value is None:
                    metadata[key] = 'Unknown'
                    logger.warning(f"Missing metadata: {key}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return {
                "num_pages": len(pdf_reader.pages),
                "title": "Untitled",
                "author": "Unknown",
                "creation_date": "Unknown",
                "error": str(e)
            }
    
    async def _store_chunk(self, doc_id: str, chunk_id: int, content: str, 
                          embedding: List[float], metadata: Dict) -> str:
        """Store document chunk in Qdrant with timing"""
        start_time = time.time()
        logger.info(f"Starting chunk storage for chunk {chunk_id} of document {doc_id}")
        
        try:
            point_id = str(uuid.uuid4())
            
            self.qdrant.upsert(
                collection_name="documents",
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            'doc_id': doc_id,
                            'chunk_id': chunk_id,
                            'content': content,
                            'metadata': metadata,
                            'composite_id': f"{doc_id}_{chunk_id}"
                        }
                    )
                ]
            )
            
            duration = time.time() - start_time
            logger.info(f"Chunk {chunk_id} stored successfully in {duration:.2f}s")
            return point_id
            
        except Exception as e:
            logger.error(f"Error storing chunk {chunk_id} after {time.time() - start_time:.2f}s: {str(e)}")
            raise
    
    async def search_similar_chunks(self, query: str, limit: int = 5) -> List[Dict]:
        """Search for similar chunks using the query text"""
        try:
            logger.debug(f"Starting search for query: {query[:50]}...")  # Log truncated query
            
            # Get API key from Redis
            api_key = self.redis.get("api_key:default")
            logger.debug(f"Retrieved API key from Redis: {'Present' if api_key else 'Missing'}")
            
            if not api_key:
                raise DocumentProcessingError("No OpenAI API key found")
            
            # Create OpenAI client
            openai_client = OpenAI(api_key=api_key.decode())
            logger.debug("Created OpenAI client")
            
            # Generate embedding for the query
            try:
                logger.debug("Generating embedding for query...")
                query_embedding = await self._generate_embedding(query, openai_client)
                logger.debug(f"Generated embedding of length: {len(query_embedding)}")
            except Exception as e:
                logger.error(f"Error generating embedding: {str(e)}", exc_info=True)
                raise
            
            # Search Qdrant
            try:
                logger.debug("Searching Qdrant...")
                search_results = self.qdrant.search(
                    collection_name="documents",
                    query_vector=query_embedding,
                    limit=limit
                )
                logger.debug(f"Found {len(search_results)} results from Qdrant")
                
                # Log the type and structure of search_results
                logger.debug(f"Search results type: {type(search_results)}")
                logger.debug(f"First result type (if any): {type(search_results[0]) if search_results else 'No results'}")
                
            except Exception as e:
                logger.error(f"Error searching Qdrant: {str(e)}", exc_info=True)
                raise
            
            # Format results
            try:
                logger.debug("Formatting search results...")
                results = []
                for result in search_results:
                    logger.debug(f"Processing result: {type(result)}")
                    logger.debug(f"Result attributes: {dir(result)}")
                    
                    results.append({
                        'content': result.payload['content'],
                        'metadata': result.payload['metadata'],
                        'score': result.score
                    })
                logger.debug(f"Formatted {len(results)} results")
                
                return results
                
            except Exception as e:
                logger.error(f"Error formatting results: {str(e)}", exc_info=True)
                raise
            
        except Exception as e:
            logger.error(f"Error in search_similar_chunks: {str(e)}", exc_info=True)
            raise
    
    def format_context_for_prompt(self, relevant_chunks: List[Dict]) -> str:
        """Format relevant chunks into context for the LLM prompt"""
        context_parts = []
        
        for i, chunk in enumerate(relevant_chunks, 1):
            metadata = chunk['metadata']
            context_parts.append(
                f"Document {i}:\n"
                f"Title: {metadata['title']}\n"
                f"Content: {chunk['content']}\n"
                f"Relevance Score: {chunk['score']:.2f}\n"
            )
        
        return "\n---\n".join(context_parts)

    async def _emit_progress_update(self, doc_id: str, update_data: dict):
        """Emit progress updates for document processing"""
        try:
            # For now, just log the update
            logger.info(f"Progress update for {doc_id}: {update_data}")
            
            # In a real implementation, you would emit this to connected WebSocket clients
            # This will be implemented when we set up the WebSocket manager
            pass
            
        except Exception as e:
            logger.error(f"Error emitting progress update: {str(e)}")

    async def _extract_metadata_async(self, pdf_reader: PyPDF2.PdfReader) -> Dict:
        """Extract metadata with timing"""
        start_time = time.time()
        logger.info("Starting metadata extraction")
        
        try:
            metadata = {
                "num_pages": len(pdf_reader.pages),
                "title": pdf_reader.metadata.get('/Title', 'Untitled'),
                "author": pdf_reader.metadata.get('/Author', 'Unknown'),
                "creation_date": pdf_reader.metadata.get('/CreationDate', 'Unknown'),
            }
            
            duration = time.time() - start_time
            logger.info(f"Metadata extracted successfully in {duration:.2f}s: {metadata}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting metadata after {time.time() - start_time:.2f}s: {str(e)}")
            return {
                "num_pages": len(pdf_reader.pages),
                "title": "Untitled",
                "author": "Unknown",
                "creation_date": "Unknown",
                "error": str(e)
            }

    async def process_document(
        self,
        session,
        project_id: Optional[UUID],
        folder_id: Optional[UUID],
        file_content: bytes,
        filename: str,
        client_id: str
    ):
        """Main entry point for document processing"""
        try:
            logger.info(f"Starting document processing for {filename}")
            
            # Create BytesIO object from file content
            file_obj = BytesIO(file_content)
            
            # Extract and sanitize text content
            try:
                pdf_reader = PyPDF2.PdfReader(file_obj)
                raw_text = ""
                for page in pdf_reader.pages:
                    raw_text += page.extract_text()
                
                # Sanitize the complete document text
                sanitized_raw_text = self._sanitize_text(raw_text)
                
                # Log truncated content for debugging
                content_preview = sanitized_raw_text[:500] + "..." if len(sanitized_raw_text) > 500 else sanitized_raw_text
                logger.debug(f"Extracted and sanitized text preview from {filename}:\n{content_preview}")
                
                # Reset file pointer for further processing
                file_obj.seek(0)
            except Exception as e:
                logger.error(f"Error extracting text content: {str(e)}")
                sanitized_raw_text = None
            
            # Process the PDF and get results
            processing_result = await self.process_pdf(file_obj, client_id)
            
            # Create document record in database with sanitized text
            from ..models.project import Document
            
            document = Document(
                document_id=UUID(processing_result['doc_id']),
                folder_id=folder_id,
                filename=filename,
                file_type='pdf',
                processing_status=processing_result['status'],
                doc_metadata=processing_result['metadata'],
                file_size=len(file_content),
                qdrant_chunks=processing_result['chunk_ids'],
                raw_content=sanitized_raw_text  # Store the sanitized raw text
            )
            
            session.add(document)
            await session.commit()
            await session.refresh(document)
            
            # Debug: Verify document was saved
            verification_query = text("""
            SELECT document_id, filename, file_size, processing_status 
            FROM documents 
            WHERE document_id = :doc_id
            """)
            result = await session.execute(
                verification_query, 
                {'doc_id': document.document_id}
            )
            db_doc = result.first()
            logger.debug(f"Verified document in database: {db_doc}")
            
            # Log successful processing
            logger.info(f"""
            Document {filename} processed and saved successfully:
            - ID: {document.document_id}
            - Size: {document.file_size} bytes
            - Status: {document.processing_status}
            - Chunks: {len(document.qdrant_chunks)} created
            - Raw content length: {len(sanitized_raw_text) if sanitized_raw_text else 0} chars
            """)
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing document {filename}: {str(e)}", exc_info=True)
            await session.rollback()
            raise DocumentProcessingError(f"Error processing document: {str(e)}")
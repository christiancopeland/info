from typing import List, Dict, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.conversation import Conversation, Message
from app.services.research_assistant import ResearchAssistant
from uuid import UUID
import tiktoken  # For token counting
import logging

logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self, db: Session, research_assistant: ResearchAssistant):
        self.db = db
        self.research_assistant = research_assistant
        # Initialize the tokenizer for GPT models
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # This is used by GPT-4 and GPT-3.5
        self.max_tokens = 7000  # Maximum token window
        logger.info(f"ConversationService initialized with max_tokens={self.max_tokens}")

    async def create_conversation(self, project_id: UUID, name: str) -> Conversation:
        """Create a new conversation in a project"""
        now = datetime.now(timezone.utc)
        conversation = Conversation(
            project_id=project_id,
            name=name,
            created_at=now,
            updated_at=now,
            meta_data={
                "document_references": [],
                "key_findings": [],
                "tags": []
            }
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def add_message(self, 
                         conversation_id: int, 
                         role: str, 
                         content: str,
                         meta_data: Dict = None) -> Message:
        """Add a new message to the conversation"""
        now = datetime.now(timezone.utc)
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=now,
            meta_data=meta_data or {}
        )
        self.db.add(message)
        
        # Update conversation's updated_at timestamp
        conversation = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = conversation.scalar_one()
        conversation.updated_at = now
        
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_conversation_history(self, conversation_id: int) -> List[Dict]:
        """Get all messages in a conversation"""
        query = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(Message.timestamp)
        
        result = await self.db.execute(query)
        messages = result.scalars().all()
            
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "meta_data": msg.meta_data
            }
            for msg in messages
        ]

    def count_tokens(self, messages: List[Dict]) -> int:
        """Count the number of tokens in a list of messages"""
        token_count = 0
        for message in messages:
            content_tokens = len(self.tokenizer.encode(message.get("content", "")))
            role_tokens = len(self.tokenizer.encode(message.get("role", "")))
            message_overhead = 4  # Approximate overhead per message
            
            message_total = content_tokens + role_tokens + message_overhead
            token_count += message_total
            
            logger.debug(f"Message tokens: role='{message.get('role')}', content={content_tokens}, role={role_tokens}, overhead={message_overhead}, total={message_total}")
            
        logger.debug(f"Total token count for {len(messages)} messages: {token_count}")
        return token_count

    def trim_messages_to_token_limit(self, messages: List[Dict]) -> List[Dict]:
        """Trim messages to fit within token limit, keeping most recent messages"""
        logger.info(f"Trimming {len(messages)} messages to fit within {self.max_tokens} token limit")
        
        # Always keep the system message if it exists
        system_message = None
        other_messages = []
        
        for msg in messages:
            if msg.get("role") == "system" and system_message is None:
                system_message = msg
            else:
                other_messages.append(msg)
        
        # Start with system message if it exists
        result = [system_message] if system_message else []
        current_tokens = self.count_tokens(result)
        logger.debug(f"Starting with system message: {current_tokens} tokens")
        
        # Add messages from newest to oldest until we hit the token limit
        messages_added = 0
        messages_skipped = 0
        
        for msg in reversed(other_messages):
            msg_tokens = self.count_tokens([msg])
            if current_tokens + msg_tokens <= self.max_tokens:
                result.insert(1 if system_message else 0, msg)  # Insert after system message
                current_tokens += msg_tokens
                messages_added += 1
                logger.debug(f"Added message ({msg.get('role')}): {msg_tokens} tokens, running total: {current_tokens}")
            else:
                messages_skipped += 1
                logger.debug(f"Skipped message ({msg.get('role')}): {msg_tokens} tokens would exceed limit")
        
        logger.info(f"Trimming complete: {messages_added} messages kept, {messages_skipped} messages skipped, total tokens: {current_tokens}")
        return result

    async def process_message(self, 
                            conversation_id: int, 
                            user_message: str) -> Dict:
        """Process a user message and get AI response"""
        try:
            logger.info(f"Processing message for conversation {conversation_id}")
            
            # Get conversation from database
            conversation = await self.db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = conversation.scalar_one()
            logger.debug(f"Retrieved conversation: {conversation.id}, name: {conversation.name}")
            
            # Initialize or get existing conversation_memory
            conversation_memory = conversation.meta_data.get('conversation_memory', [])
            logger.debug(f"Retrieved conversation memory with {len(conversation_memory)} messages")
            
            # System prompt
            system_prompt = """You are an AI Research Assistant managing a comprehensive research and intelligence platform designed to help investigators, journalists, and researchers conduct deep research and monitor current events. This service is called The Pulse. Your core purpose is to help users discover, analyze, and synthesize information across multiple documents and sources.
            "PRIMARY CAPABILITIES:
            "1. Document Processing & Analysis
            "- Process multiple document types (PDF, TXT, URL, DOCX)
            "- Extract metadata and entities
            "- Classify content and assess source credibility
            "- Maximum file size: 100MB per document
            "- Processing time target: <30 seconds
            "2. Research Assistance
            "- Engage in context-aware conversations about documents
            "- Support multiple research modes:
            "  * Exploration (open-ended research)
            "  * Analysis (deep document examination)
            "  * Synthesis (cross-document insights)
            "  * Fact-checking (claim verification)
            "- Maintain conversation context including active documents and key findings
            "- Generate citations and explanations
            "3. Search & Discovery
            "- Execute keyword, semantic, and hybrid searches
            "- Detect cross-document references
            "- Response time target: <2 seconds
            "- Support time-period and source-specific filtering
            "4. Project Organization
            "- Help manage hierarchical project structures (max depth: 10 folders)
            "- Track document versions and processing status
            "- Support up to 1000 documents per folder
            "- Maintain project metadata and settings
            "5. Entity Tracking & Alerts
            "- Monitor entities across all sources
            "- Filter false positives
            "- Manage alert thresholds
            "- Deliver notifications through multiple channels
            "INTERACTION GUIDELINES:
            "1. Always maintain context of:
            "- Current research project scope
            "- Active documents under discussion
            "- Recent conversation history
            "- Verified facts and hypotheses
            "- Pending questions
            "2. For each user interaction:
            "- Consider project context
            "- Reference specific documents when appropriate
            "- Provide evidence-based responses
            "- Suggest relevant next steps
            "- Update research state
            "3. Research Assistance Priorities:
            "- Help formulate research questions
            "- Identify patterns and connections
            "- Highlight contradictions or gaps
            "- Generate actionable insights
            "- Support fact verification
            "Remember: Your primary goal is to augment human research capabilities by providing intelligent, context-aware assistance while maintaining high standards of accuracy and evidence-based analysis."""
            
            # Add user message to memory
            conversation_memory.append({
                "role": "user",
                "content": user_message
            })
            logger.debug(f"Added user message to memory: {len(user_message)} chars")
            
            # Save user message to database
            user_msg = await self.add_message(
                conversation_id=conversation_id,
                role="user",
                content=user_message
            )
            logger.info(f"Saved user message to database, ID: {user_msg.id}")
            
            # Prepare messages for LLM with token window
            # Always include system message at the beginning
            llm_messages = [{"role": "system", "content": system_prompt}]
            logger.debug(f"System prompt token count: {self.count_tokens(llm_messages)}")
            
            # Add conversation history within token limit
            history_messages = self.trim_messages_to_token_limit(conversation_memory)
            logger.info(f"Trimmed conversation history to {len(history_messages)} messages")
            
            # Combine system message with trimmed history
            if history_messages and history_messages[0].get("role") == "system":
                # If history already has a system message, use the combined messages
                llm_messages = history_messages
                logger.debug("Using system message from history")
            else:
                # Otherwise append history to our system message
                llm_messages.extend(history_messages)
                logger.debug("Appending history to system message")
            
            logger.info(f"Sending {len(llm_messages)} messages to LLM with total tokens: {self.count_tokens(llm_messages)}")
            
            # Get AI response as a stream
            response_stream = self.research_assistant.chat(messages=llm_messages)
            
            # Initialize response content
            full_response = ""
            
            # Return a streaming response
            async def response_generator():
                nonlocal full_response
                
                try:
                    chunk_count = 0
                    async for chunk in response_stream:
                        chunk_count += 1
                        if isinstance(chunk, dict) and "message" in chunk:
                            content = chunk["message"]["content"]
                        else:
                            content = str(chunk)
                        
                        full_response += content
                        if chunk_count % 10 == 0:  # Log every 10 chunks to avoid excessive logging
                            logger.debug(f"Received chunk {chunk_count}, current response length: {len(full_response)} chars")
                        
                        yield {
                            "type": "chunk",
                            "content": content
                        }
                    
                    logger.info(f"Response streaming complete, received {chunk_count} chunks, total length: {len(full_response)} chars")
                    
                    # After stream completes, update conversation memory
                    conversation_memory.append({
                        "role": "assistant",
                        "content": full_response
                    })
                    logger.debug("Added assistant response to conversation memory")
                    
                    # Save assistant message to database
                    assistant_msg = await self.add_message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=full_response
                    )
                    logger.info(f"Saved assistant message to database, ID: {assistant_msg.id}")
                    
                    # Update conversation metadata
                    conversation.meta_data['conversation_memory'] = conversation_memory
                    conversation.updated_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    logger.info("Updated conversation metadata and committed to database")
                    
                    # Send completion message
                    yield {
                        "type": "done",
                        "content": full_response
                    }
                    
                except Exception as e:
                    logger.error(f"Error in response generator: {str(e)}", exc_info=True)
                    yield {
                        "type": "error",
                        "content": str(e)
                    }
            
            return response_generator()
            
        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}", exc_info=True)
            raise

    async def get_project_conversations(self, project_id: UUID) -> List[Dict]:
        """Get all conversations in a project"""
        conversations = self.db.query(Conversation).filter(
            Conversation.project_id == project_id
        ).order_by(Conversation.updated_at.desc()).all()
        
        return [{
            "id": str(conv.id),
            "name": conv.name,
            "updated_at": conv.updated_at,
            "meta_data": conv.meta_data
        } for conv in conversations]

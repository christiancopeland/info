import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost/research_platform"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True
)

# Create async session maker
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def create_entity_tracking_tables():
    """Create the tracked_entities and entity_mentions tables"""
    async with engine.begin() as conn:
        try:
            # Drop existing tables if they exist
            logger.info("Dropping existing entity tracking tables if they exist...")
            drop_tables = text("""
                DROP TABLE IF EXISTS entity_mentions CASCADE;
                DROP TABLE IF EXISTS tracked_entities CASCADE;
            """)
            await conn.execute(drop_tables)
            
            # Create tracked_entities table
            logger.info("Creating tracked_entities table...")
            create_tracked_entities = text("""
                CREATE TABLE tracked_entities (
                    entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(user_id),
                    name VARCHAR NOT NULL,
                    entity_type VARCHAR NOT NULL,
                    created_at VARCHAR NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB,
                    UNIQUE(user_id, name)
                );
                
                -- Add index for faster lookups by user_id
                CREATE INDEX idx_tracked_entities_user_id ON tracked_entities(user_id);
                
                -- Add index for name searches
                CREATE INDEX idx_tracked_entities_name ON tracked_entities(name);
            """)
            await conn.execute(create_tracked_entities)
            
            # Create entity_mentions table
            logger.info("Creating entity_mentions table...")
            create_entity_mentions = text("""
                CREATE TABLE entity_mentions (
                    mention_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_id UUID NOT NULL REFERENCES tracked_entities(entity_id) ON DELETE CASCADE,
                    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(user_id),
                    chunk_id VARCHAR NOT NULL,
                    context TEXT NOT NULL,
                    timestamp VARCHAR NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Ensure user can only see their own mentions
                    CONSTRAINT fk_user_mentions
                        FOREIGN KEY (user_id, entity_id)
                        REFERENCES tracked_entities(user_id, entity_id)
                );
                
                -- Add indexes for common queries
                CREATE INDEX idx_entity_mentions_entity_id ON entity_mentions(entity_id);
                CREATE INDEX idx_entity_mentions_user_id ON entity_mentions(user_id);
                CREATE INDEX idx_entity_mentions_document_id ON entity_mentions(document_id);
                CREATE INDEX idx_entity_mentions_timestamp ON entity_mentions(timestamp);
            """)
            await conn.execute(create_entity_mentions)
            
            logger.info("Successfully created entity tracking tables")
            
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise

async def main():
    try:
        await create_entity_tracking_tables()
        logger.info("Table creation completed")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
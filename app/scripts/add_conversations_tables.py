import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost/research_platform"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    future=True
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def update_schema():
    """Update database schema while preserving existing data"""
    async with engine.begin() as conn:
        try:
            # Start a transaction
            await conn.execute(text("BEGIN;"))
            
            # 1. Create conversations table if it doesn't exist
            logger.info("Checking conversations table...")
            create_conversations = text("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    project_id UUID REFERENCES research_projects(project_id) ON DELETE CASCADE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    meta_data JSONB DEFAULT '{}'::jsonb
                );
            """)
            await conn.execute(create_conversations)
            
            # Create index if it doesn't exist
            create_conv_index = text("""
                CREATE INDEX IF NOT EXISTS idx_conversations_project_id 
                ON conversations(project_id);
            """)
            await conn.execute(create_conv_index)
            
            # 2. Create messages table if it doesn't exist
            logger.info("Checking messages table...")
            create_messages = text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
                    role VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    meta_data JSONB DEFAULT '{}'::jsonb
                );
            """)
            await conn.execute(create_messages)
            
            # Create index if it doesn't exist
            create_msg_index = text("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                ON messages(conversation_id);
            """)
            await conn.execute(create_msg_index)
            
            # 3. Add any new columns to existing tables (if needed)
            # Check if columns exist before adding them
            check_columns = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='conversations' AND column_name='meta_data';
            """)
            result = await conn.execute(check_columns)
            if not result.scalar():
                logger.info("Adding meta_data column to conversations...")
                add_meta_data = text("""
                    ALTER TABLE conversations 
                    ADD COLUMN IF NOT EXISTS meta_data JSONB DEFAULT '{}'::jsonb;
                """)
                await conn.execute(add_meta_data)
            
            # 4. Update any existing data if needed
            # For example, initialize meta_data for any NULL values
            update_null_meta = text("""
                UPDATE conversations 
                SET meta_data = '{}'::jsonb 
                WHERE meta_data IS NULL;
            """)
            await conn.execute(update_null_meta)
            
            # Commit transaction
            await conn.execute(text("COMMIT;"))
            logger.info("Schema update completed successfully")
            
        except Exception as e:
            # Rollback in case of error
            await conn.execute(text("ROLLBACK;"))
            logger.error(f"Error updating schema: {str(e)}")
            raise

async def verify_schema():
    """Verify the schema changes were applied correctly"""
    async with engine.begin() as conn:
        try:
            # Check tables exist
            tables = ['conversations', 'messages']
            for table in tables:
                check_table = text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{table}'
                    );
                """)
                result = await conn.execute(check_table)
                exists = result.scalar()
                logger.info(f"Table {table} exists: {exists}")
            
            # Check indexes exist
            indexes = ['idx_conversations_project_id', 'idx_messages_conversation_id']
            for index in indexes:
                check_index = text(f"""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE indexname = '{index}'
                    );
                """)
                result = await conn.execute(check_index)
                exists = result.scalar()
                logger.info(f"Index {index} exists: {exists}")
                
        except Exception as e:
            logger.error(f"Error verifying schema: {str(e)}")
            raise

async def main():
    try:
        logger.info("Starting schema update...")
        await update_schema()
        logger.info("Verifying schema changes...")
        await verify_schema()
        logger.info("Schema update and verification completed successfully")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
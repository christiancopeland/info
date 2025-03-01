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
    """Update conversations and messages tables schema while preserving existing data"""
    async with engine.begin() as conn:
        try:
            # Start a transaction
            await conn.execute(text("BEGIN;"))
            
            # 1. Create conversations table if it doesn't exist
            logger.info("Checking conversations table...")
            create_conversations = text("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    project_id UUID REFERENCES research_projects(project_id),
                    created_at TIMESTAMP WITH TIME ZONE,
                    updated_at TIMESTAMP WITH TIME ZONE,
                    meta_data JSON DEFAULT '{}'::json
                );
            """)
            await conn.execute(create_conversations)
            
            # Create index as separate statement
            create_index = text("""
                CREATE INDEX IF NOT EXISTS idx_conversations_name ON conversations(name);
            """)
            await conn.execute(create_index)
            
            # 2. Create messages table if it doesn't exist
            logger.info("Checking messages table...")
            create_messages = text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id INTEGER REFERENCES conversations(id),
                    role VARCHAR(50) NOT NULL,
                    content VARCHAR NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE,
                    meta_data JSON DEFAULT '{}'::json
                );
            """)
            await conn.execute(create_messages)
            
            # Update message timestamp column to use timezone
            logger.info("Updating message timestamp column to use timezone...")
            alter_message_timestamp = text("""
                ALTER TABLE messages 
                ALTER COLUMN timestamp TYPE TIMESTAMP WITH TIME ZONE 
                USING timestamp AT TIME ZONE 'UTC';
            """)
            await conn.execute(alter_message_timestamp)
            
            # 3. Add or modify columns as needed for conversations
            logger.info("Checking and updating conversations columns...")
            columns_to_check = [
                ("name", "VARCHAR(255)", True),
                ("project_id", "UUID", True),
                ("created_at", "TIMESTAMP WITH TIME ZONE", False),
                ("updated_at", "TIMESTAMP WITH TIME ZONE", False),
                ("meta_data", "JSON", False)
            ]
            
            for col_name, col_type, not_null in columns_to_check:
                # Check if column exists and its type
                check_column = text(f"""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = 'conversations' 
                    AND column_name = '{col_name}';
                """)
                result = await conn.execute(check_column)
                column_info = result.fetchone()
                
                if not column_info:
                    # Add column if it doesn't exist
                    logger.info(f"Adding column {col_name}...")
                    add_column = text(f"""
                        ALTER TABLE conversations 
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type} 
                        {' NOT NULL' if not_null else ''} 
                        {" DEFAULT '{}'" if col_type == 'JSON' else ''};
                    """)
                    await conn.execute(add_column)
            
            # 4. Add or modify columns as needed for messages
            logger.info("Checking and updating messages columns...")
            message_columns = [
                ("role", "VARCHAR(50)", True),
                ("content", "VARCHAR", True),
                ("timestamp", "TIMESTAMP WITH TIME ZONE", False),
                ("meta_data", "JSON", False)
            ]
            
            for col_name, col_type, not_null in message_columns:
                check_column = text(f"""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = 'messages' 
                    AND column_name = '{col_name}';
                """)
                result = await conn.execute(check_column)
                column_info = result.fetchone()
                
                if not column_info:
                    logger.info(f"Adding column {col_name}...")
                    add_column = text(f"""
                        ALTER TABLE messages 
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type} 
                        {' NOT NULL' if not_null else ''} 
                        {" DEFAULT '{}'" if col_type == 'JSON' else ''};
                    """)
                    await conn.execute(add_column)
            
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
            # Check all required columns exist with correct types for conversations
            conversations_columns = [
                ("id", "integer"),
                ("name", "character varying"),
                ("project_id", "uuid"),
                ("created_at", "timestamp with time zone"),
                ("updated_at", "timestamp with time zone"),
                ("meta_data", "json")
            ]
            
            for col_name, expected_type in conversations_columns:
                check_column = text(f"""
                    SELECT data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'conversations' 
                    AND column_name = '{col_name}';
                """)
                result = await conn.execute(check_column)
                actual_type = result.scalar()
                logger.info(f"Conversations column {col_name} exists with type: {actual_type}")
                assert actual_type is not None, f"Column {col_name} is missing"
                assert actual_type == expected_type, f"Column {col_name} has wrong type: {actual_type} != {expected_type}"
            
            # Check all required columns exist with correct types for messages
            messages_columns = [
                ("id", "integer"),
                ("conversation_id", "integer"),
                ("role", "character varying"),
                ("content", "character varying"),
                ("timestamp", "timestamp with time zone"),
                ("meta_data", "json")
            ]
            
            for col_name, expected_type in messages_columns:
                check_column = text(f"""
                    SELECT data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'messages' 
                    AND column_name = '{col_name}';
                """)
                result = await conn.execute(check_column)
                actual_type = result.scalar()
                logger.info(f"Messages column {col_name} exists with type: {actual_type}")
                assert actual_type is not None, f"Column {col_name} is missing"
                assert actual_type == expected_type, f"Column {col_name} has wrong type: {actual_type} != {expected_type}"
                
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
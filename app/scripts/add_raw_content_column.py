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

async def add_raw_content_column():
    """Add raw_content column to documents table"""
    async with engine.begin() as conn:
        try:
            # Check if column exists first
            check_column = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='documents' AND column_name='raw_content';
            """)
            result = await conn.execute(check_column)
            if result.scalar():
                logger.info("raw_content column already exists")
                return

            # Add the column
            logger.info("Adding raw_content column to documents table...")
            add_column = text("""
                ALTER TABLE documents 
                ADD COLUMN raw_content TEXT;
            """)
            await conn.execute(add_column)
            
            logger.info("Successfully added raw_content column")
            
        except Exception as e:
            logger.error(f"Error adding column: {str(e)}")
            raise

async def main():
    try:
        await add_raw_content_column()
        logger.info("Column addition completed")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())

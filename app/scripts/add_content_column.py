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

async def add_content_column():
    """Add content column to news_articles table"""
    async with engine.begin() as conn:
        try:
            # Check if column exists first
            check_column = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='news_articles' AND column_name='content';
            """)
            result = await conn.execute(check_column)
            if result.scalar():
                logger.info("content column already exists")
                return

            # Add the content column
            logger.info("Adding content column to news_articles table...")
            add_column = text("""
                ALTER TABLE news_articles 
                ADD COLUMN content TEXT;
            """)
            await conn.execute(add_column)
            
            logger.info("Successfully added content column")
            
        except Exception as e:
            logger.error(f"Error adding column: {str(e)}")
            raise

async def main():
    try:
        await add_content_column()
        logger.info("Column addition completed")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
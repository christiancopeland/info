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

async def add_news_article_columns():
    """Add new columns to news_articles table"""
    async with engine.begin() as conn:
        try:
            # Check if content column exists
            check_content = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='news_articles' AND column_name='content';
            """)
            result = await conn.execute(check_content)
            if not result.scalar():
                logger.info("Adding content column...")
                await conn.execute(text("""
                    ALTER TABLE news_articles 
                    ADD COLUMN content TEXT;
                """))
                logger.info("Added content column")

            # Check if is_liveblog column exists
            check_liveblog = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='news_articles' AND column_name='is_liveblog';
            """)
            result = await conn.execute(check_liveblog)
            if not result.scalar():
                logger.info("Adding is_liveblog column...")
                await conn.execute(text("""
                    ALTER TABLE news_articles 
                    ADD COLUMN is_liveblog BOOLEAN DEFAULT FALSE;
                """))
                logger.info("Added is_liveblog column")

            # Check if last_updated column exists
            check_last_updated = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='news_articles' AND column_name='last_updated';
            """)
            result = await conn.execute(check_last_updated)
            if not result.scalar():
                logger.info("Adding last_updated column...")
                await conn.execute(text("""
                    ALTER TABLE news_articles 
                    ADD COLUMN last_updated TIMESTAMP WITH TIME ZONE;
                """))
                logger.info("Added last_updated column")

            logger.info("Successfully added all required columns")
            
        except Exception as e:
            logger.error(f"Error adding columns: {str(e)}")
            raise

async def main():
    try:
        await add_news_article_columns()
        logger.info("Column additions completed")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
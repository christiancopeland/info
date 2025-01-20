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

async def create_news_articles_table():
    """Create the news_articles table if it doesn't exist"""
    async with engine.begin() as conn:
        try:
            # Drop the table if it exists
            logger.info("Dropping existing news_articles table if it exists...")
            drop_table = text("""
                DROP TABLE IF EXISTS news_articles CASCADE;
            """)
            await conn.execute(drop_table)
            
            # Create the table
            logger.info("Creating news_articles table...")
            create_table = text("""
                CREATE TABLE news_articles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    title VARCHAR NOT NULL,
                    heading VARCHAR NOT NULL,
                    url VARCHAR NOT NULL UNIQUE,
                    source_site VARCHAR NOT NULL,
                    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute(create_table)
            
            logger.info("Successfully created news_articles table")
            
        except Exception as e:
            logger.error(f"Error creating table: {str(e)}")
            raise

async def main():
    try:
        await create_news_articles_table()
        logger.info("Table creation completed")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
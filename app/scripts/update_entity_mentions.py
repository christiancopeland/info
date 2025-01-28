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

async def update_entity_mentions_table():
    """Update entity_mentions table to support news articles"""
    async with engine.begin() as conn:
        try:
            # Check if news_article_id column exists
            check_column = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='entity_mentions' AND column_name='news_article_id';
            """)
            result = await conn.execute(check_column)
            if result.scalar():
                logger.info("news_article_id column already exists")
                return

            # Make document_id nullable
            logger.info("Making document_id nullable...")
            make_nullable = text("""
                ALTER TABLE entity_mentions 
                ALTER COLUMN document_id DROP NOT NULL;
            """)
            await conn.execute(make_nullable)
            
            # Add news_article_id column
            logger.info("Adding news_article_id column...")
            add_column = text("""
                ALTER TABLE entity_mentions 
                ADD COLUMN news_article_id UUID REFERENCES news_articles(id) ON DELETE CASCADE;
            """)
            await conn.execute(add_column)
            
            # Add check constraint
            logger.info("Adding check constraint...")
            add_constraint = text("""
                ALTER TABLE entity_mentions
                ADD CONSTRAINT check_one_source_id
                CHECK (
                    (document_id IS NOT NULL AND news_article_id IS NULL) OR
                    (document_id IS NULL AND news_article_id IS NOT NULL)
                );
            """)
            await conn.execute(add_constraint)
            
            logger.info("Successfully updated entity_mentions table")
            
        except Exception as e:
            logger.error(f"Error updating table: {str(e)}")
            raise

async def main():
    try:
        await update_entity_mentions_table()
        logger.info("Table update completed successfully")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 
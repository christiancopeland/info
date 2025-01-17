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

async def add_updated_at_column():
    """Add updated_at column to project_folders table"""
    async with engine.begin() as conn:
        try:
            # Check if column exists first
            check_column = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='project_folders' AND column_name='updated_at';
            """)
            result = await conn.execute(check_column)
            if result.scalar():
                logger.info("updated_at column already exists")
                return

            # Add the column with default value
            logger.info("Adding updated_at column to project_folders table...")
            add_column = text("""
                ALTER TABLE project_folders 
                ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
            """)
            await conn.execute(add_column)
            
            # Update existing rows to match created_at
            logger.info("Updating existing rows...")
            update_existing = text("""
                UPDATE project_folders 
                SET updated_at = created_at 
                WHERE updated_at IS NULL;
            """)
            await conn.execute(update_existing)
            
            logger.info("Successfully added and populated updated_at column")
            
        except Exception as e:
            logger.error(f"Error adding column: {str(e)}")
            raise

async def main():
    try:
        await add_updated_at_column()
        logger.info("Column addition completed")
    except Exception as e:
        logger.error(f"Script failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())

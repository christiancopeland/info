from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
import logging
from fastapi import HTTPException



logger = logging.getLogger(__name__)

# Create declarative base
Base = declarative_base()

# Get database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost/research_platform"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Set to False in production
    future=True,
    pool_size=20,
    max_overflow=0
)

# Create async session maker
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """Initialize the database tables"""
    try:
        async with engine.begin() as conn:
            # First create tables that don't exist
            await conn.run_sync(Base.metadata.create_all)
            
            # Then add the openai_api_key column if it doesn't exist
            await conn.execute(
                text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 
                            FROM information_schema.columns 
                            WHERE table_name='users' AND column_name='openai_api_key'
                        ) THEN
                            ALTER TABLE users ADD COLUMN openai_api_key VARCHAR;
                        END IF;
                    END $$;
                """)
            )
            
            logger.info("Database tables and columns created successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

async def get_db():
    """Dependency for getting database sessions"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except HTTPException as e:
            # Don't log HTTP exceptions as database errors
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()

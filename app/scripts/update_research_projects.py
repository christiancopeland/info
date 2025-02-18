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
    """Update research_projects table schema while preserving existing data"""
    async with engine.begin() as conn:
        try:
            # Start a transaction
            await conn.execute(text("BEGIN;"))
            
            # 1. Create research_projects table if it doesn't exist
            logger.info("Checking research_projects table...")
            create_projects = text("""
                CREATE TABLE IF NOT EXISTS research_projects (
                    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    owner_id VARCHAR NOT NULL,
                    status VARCHAR(50) DEFAULT 'active',
                    settings JSONB DEFAULT '{}'::jsonb
                );
            """)
            await conn.execute(create_projects)
            
            # 2. Add or modify columns as needed
            logger.info("Checking and updating columns...")
            
            # Check and update column types
            columns_to_check = [
                ("name", "VARCHAR(255)"),
                ("description", "TEXT"),
                ("owner_id", "VARCHAR"),
                ("status", "VARCHAR(50)"),
                ("settings", "JSONB")
            ]
            
            for col_name, col_type in columns_to_check:
                # Check if column exists and its type
                check_column = text(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'research_projects' 
                    AND column_name = '{col_name}';
                """)
                result = await conn.execute(check_column)
                column_info = result.fetchone()
                
                if not column_info:
                    # Add column if it doesn't exist
                    logger.info(f"Adding column {col_name}...")
                    add_column = text(f"""
                        ALTER TABLE research_projects 
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type} 
                        {' NOT NULL' if col_name in ['name', 'owner_id'] else ''} 
                        {f" DEFAULT '{{'}}'" if col_type == 'JSONB' else ''};
                    """)
                    await conn.execute(add_column)
                else:
                    # Check if we need to modify the column type
                    current_type = column_info[1]  # data_type is the second column
                    expected_type = col_type.lower().replace('varchar(255)', 'character varying')
                    
                    if current_type != expected_type:
                        logger.info(f"Modifying column {col_name} type from {current_type} to {expected_type}...")
                        modify_column = text(f"""
                            ALTER TABLE research_projects 
                            ALTER COLUMN {col_name} TYPE {col_type} 
                            USING {col_name}::{col_type};
                        """)
                        await conn.execute(modify_column)
            
            # 3. Add timestamps if they don't exist
            for timestamp_col in ['created_at', 'updated_at']:
                check_timestamp = text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'research_projects' 
                    AND column_name = '{timestamp_col}';
                """)
                result = await conn.execute(check_timestamp)
                if not result.scalar():
                    logger.info(f"Adding {timestamp_col} column...")
                    add_timestamp = text(f"""
                        ALTER TABLE research_projects 
                        ADD COLUMN IF NOT EXISTS {timestamp_col} 
                        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
                    """)
                    await conn.execute(add_timestamp)
            
            # 4. Set default values for any NULL fields
            logger.info("Updating NULL values with defaults...")
            update_nulls = text("""
                UPDATE research_projects SET
                    status = COALESCE(status, 'active'),
                    settings = COALESCE(settings, '{}'::jsonb),
                    updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP),
                    created_at = COALESCE(created_at, CURRENT_TIMESTAMP);
            """)
            await conn.execute(update_nulls)
            
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
            # Check all required columns exist with correct types
            columns_to_verify = [
                ("project_id", "uuid"),
                ("name", "character varying"),
                ("description", "text"),
                ("created_at", "timestamp with time zone"),
                ("updated_at", "timestamp with time zone"),
                ("owner_id", "character varying"),
                ("status", "character varying"),
                ("settings", "jsonb")
            ]
            
            for col_name, expected_type in columns_to_verify:
                check_column = text(f"""
                    SELECT data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'research_projects' 
                    AND column_name = '{col_name}';
                """)
                result = await conn.execute(check_column)
                actual_type = result.scalar()
                logger.info(f"Column {col_name} exists with type: {actual_type}")
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
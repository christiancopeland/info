import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os
from typing import Dict, List, Tuple

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

class TableCreationError(Exception):
    """Custom exception for table creation errors"""
    pass

async def verify_table_structure(conn) -> Dict[str, List[str]]:
    """Verify the structure of created tables"""
    verification_results = {
        "tables": [],
        "constraints": [],
        "indexes": [],
        "issues": []
    }
    
    try:
        # Check tables existence
        tables_query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('tracked_entities', 'entity_mentions');
        """
        result = await conn.execute(text(tables_query))
        existing_tables = [row[0] for row in result]
        verification_results["tables"] = existing_tables
        
        # Check constraints
        constraints_query = """
            SELECT tc.table_name, tc.constraint_name, tc.constraint_type
            FROM information_schema.table_constraints tc
            WHERE tc.table_schema = 'public'
            AND tc.table_name IN ('tracked_entities', 'entity_mentions');
        """
        result = await conn.execute(text(constraints_query))
        constraints = [(row[0], row[1], row[2]) for row in result]
        verification_results["constraints"] = constraints
        
        # Check indexes
        indexes_query = """
            SELECT 
                tablename, 
                indexname, 
                indexdef
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename IN ('tracked_entities', 'entity_mentions');
        """
        result = await conn.execute(text(indexes_query))
        indexes = [(row[0], row[1], row[2]) for row in result]
        verification_results["indexes"] = indexes
        
        # Verify specific requirements
        required_tables = {'tracked_entities', 'entity_mentions'}
        missing_tables = required_tables - set(existing_tables)
        if missing_tables:
            verification_results["issues"].append(f"Missing tables: {missing_tables}")
        
        # Verify unique constraint on tracked_entities
        unique_constraint_found = any(
            c[0] == 'tracked_entities' and c[2] == 'UNIQUE'
            for c in constraints
        )
        if not unique_constraint_found:
            verification_results["issues"].append(
                "Missing unique constraint on tracked_entities(user_id, entity_id)"
            )
        
        return verification_results
        
    except Exception as e:
        raise TableCreationError(f"Error during verification: {str(e)}")

async def create_entity_tracking_tables(dry_run: bool = False):
    """Create the tracked_entities and entity_mentions tables"""
    async with engine.begin() as conn:
        try:
            # Store SQL commands for dry run
            sql_commands = []
            
            # Drop existing tables one at a time
            logger.info("Dropping existing entity tracking tables if they exist...")
            sql_commands.extend([
                "DROP TABLE IF EXISTS entity_mentions CASCADE;",
                "DROP TABLE IF EXISTS tracked_entities CASCADE;"
            ])
            
            # Create tracked_entities table
            logger.info("Creating tracked_entities table...")
            create_tracked_entities = """
                CREATE TABLE tracked_entities (
                    entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(user_id),
                    name VARCHAR NOT NULL,
                    entity_type VARCHAR NOT NULL,
                    created_at VARCHAR NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    entity_metadata JSONB,
                    CONSTRAINT unique_user_entity UNIQUE (user_id, entity_id)
                );
            """
            sql_commands.append(create_tracked_entities)
            
            # Add indexes for tracked_entities
            tracked_entities_indexes = [
                "CREATE INDEX idx_tracked_entities_user_id ON tracked_entities(user_id);",
                "CREATE INDEX idx_tracked_entities_name ON tracked_entities(name);",
                "CREATE UNIQUE INDEX idx_user_entity_name ON tracked_entities(user_id, name);"
            ]
            sql_commands.extend(tracked_entities_indexes)
            
            # Create entity_mentions table
            logger.info("Creating entity_mentions table...")
            create_entity_mentions = """
                CREATE TABLE entity_mentions (
                    mention_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    entity_id UUID NOT NULL,
                    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(user_id),
                    chunk_id VARCHAR NOT NULL,
                    context TEXT NOT NULL,
                    timestamp VARCHAR NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT fk_user_mentions 
                        FOREIGN KEY (user_id, entity_id) 
                        REFERENCES tracked_entities(user_id, entity_id) 
                        ON DELETE CASCADE
                );
            """
            sql_commands.append(create_entity_mentions)
            
            # Add indexes for entity_mentions
            entity_mentions_indexes = [
                "CREATE INDEX idx_entity_mentions_entity_id ON entity_mentions(entity_id);",
                "CREATE INDEX idx_entity_mentions_user_id ON entity_mentions(user_id);",
                "CREATE INDEX idx_entity_mentions_document_id ON entity_mentions(document_id);",
                "CREATE INDEX idx_entity_mentions_timestamp ON entity_mentions(timestamp);"
            ]
            sql_commands.extend(entity_mentions_indexes)
            
            if dry_run:
                logger.info("DRY RUN - SQL commands to be executed:")
                for cmd in sql_commands:
                    logger.info(f"\n{cmd}")
                return
            
            # Execute all commands
            for cmd in sql_commands:
                await conn.execute(text(cmd))
            
            # Verify the table structure
            logger.info("Verifying table structure...")
            verification_results = await verify_table_structure(conn)
            
            if verification_results["issues"]:
                raise TableCreationError(
                    f"Table verification failed: {verification_results['issues']}"
                )
            
            # Log successful creation with details
            logger.info("Successfully created entity tracking tables")
            logger.info(f"Created tables: {verification_results['tables']}")
            logger.info(f"Created constraints: {len(verification_results['constraints'])}")
            logger.info(f"Created indexes: {len(verification_results['indexes'])}")
            
        except Exception as e:
            logger.error(f"Error creating tables: {str(e)}")
            raise

async def main():
    try:
        # First do a dry run
        logger.info("Performing dry run...")
        await create_entity_tracking_tables(dry_run=True)
        
        # Ask for confirmation
        response = input("\nProceed with table creation? (y/n): ")
        if response.lower() != 'y':
            logger.info("Table creation cancelled")
            return
        
        # Create tables
        logger.info("Creating tables...")
        await create_entity_tracking_tables()
        logger.info("Table creation completed successfully")
        
    except TableCreationError as e:
        logger.error(f"Table creation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 
import asyncio
import sys
import os
import uuid
import redis
from sqlalchemy import select, Column, String, DateTime, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Configuration variables
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")  # Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost/research_platform"
    )
    
    # Redis settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    
    # API Settings
    API_TITLE: str = "Research Platform API"
    API_DESCRIPTION: str = "A comprehensive research and news monitoring platform"
    API_VERSION: str = "0.1.0"
    
    # CORS Settings
    CORS_ORIGINS: list[str] = ["http://127.0.0.1:8000"]
    
    # Template Settings
    TEMPLATE_DIR: str = "templates"
    STATIC_DIR: str = "static"

    class Config:
        case_sensitive = True

settings = Settings()


# Add the parent directory to Python path so we can import our app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create declarative base
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    openai_api_key = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

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


# Test user constants
API_KEY = "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"
TEST_EMAIL = "test@test.com"
TEST_USER_ID = "aa5c38ff-7fb4-41d0-9fb3-ed2d67d3b4c3" 

# Initialize Redis client
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB
)

async def insert_api_key():
    async with async_session() as session:
        # Try to find existing user first
        result = await session.execute(
            select(User).where(User.email == TEST_EMAIL)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Create new user with specific user_id
            user = User(
                user_id=uuid.UUID(TEST_USER_ID),
                email=TEST_EMAIL,
                password_hash="test_hash",  # You should use a proper hash in production
                openai_api_key=API_KEY
            )
            session.add(user)
        else:
            # Update existing user
            user.user_id = uuid.UUID(TEST_USER_ID)  # Update user_id
            user.openai_api_key = API_KEY
        
        try:
            await session.commit()
            print(f"User created/updated with ID: {TEST_USER_ID}")
            print(f"API key stored in database for user {TEST_EMAIL}")
            
            # Store in Redis
            redis_client.setex(
                f"openai_key:{TEST_USER_ID}",  # Use user_id as Redis key
                2592000,  # 30 days
                API_KEY.encode()  # Make sure to encode the API key
            )
            print(f"API key stored in Redis with user_id: {TEST_USER_ID}")
            
            # Verify the data
            result = await session.execute(
                select(User).where(User.user_id == uuid.UUID(TEST_USER_ID))
            )
            verified_user = result.scalar_one_or_none()
            if verified_user:
                print("\nVerification successful:")
                print(f"User ID: {verified_user.user_id}")
                print(f"Email: {verified_user.email}")
                print(f"Has API Key: {bool(verified_user.openai_api_key)}")
            else:
                print("Warning: Could not verify user after insert/update")
                
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            await session.rollback()
            raise

if __name__ == "__main__":
    asyncio.run(insert_api_key())

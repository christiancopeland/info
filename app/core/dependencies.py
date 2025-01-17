from fastapi import Depends, HTTPException, FastAPI, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, ExpiredSignatureError
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import redis
from contextlib import asynccontextmanager
import logging

from ..database import get_db, init_db, engine
from ..services.document_processor import DocumentProcessor
from ..services.auth.security_service import SecurityService
from ..services.project_service import ProjectService
from ..models.user import User
from .config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Add logging setup
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user"""
    logger.debug("Starting get_current_user")
    logger.debug(f"Received token: {token[:10]}..." if token else "No token")
    
    credentials_exception = HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        logger.debug("No token provided")
        raise credentials_exception
    
    try:
        logger.debug(f"Attempting to decode token: {token[:10]}...")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logger.debug(f"Token decoded successfully. Payload: {payload}")
        
        user_id: str = payload.get("sub")
        if not user_id:
            logger.debug("No user_id in token payload")
            raise credentials_exception
            
        logger.debug(f"Looking up user with ID: {user_id}")
        
        result = await db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.debug(f"No user found for user_id: {user_id}")
            raise credentials_exception
            
        logger.debug(f"User found: {user.email}")
        return user
        
    except Exception as e:
        logger.error(f"Error in get_current_user: {str(e)}")
        raise credentials_exception

# Helper functions
async def test_api_connection(client: OpenAI) -> bool:
    """Test if the OpenAI API key is valid"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{
                "role": "user",
                "content": "Hello"
            }],
            max_tokens=5
        )
        return True
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid API key: {str(e)}")

def create_access_token(data: dict):
    """Create JWT token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

# Add the test user creation function
async def create_test_user(db: AsyncSession):
    """Create a test user if it doesn't exist"""
    try:
        result = await db.execute(
            select(User).where(User.email == "test@test.com")
        )
        if not result.scalar_one_or_none():
            hashed_password = pwd_context.hash("password")
            test_user = User(
                email="test@test.com",
                password_hash=hashed_password
            )
            db.add(test_user)
            await db.commit()
            logger.info("Test user created successfully")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating test user: {str(e)}")

# Add the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for FastAPI"""
    # Startup
    await init_db()
    
    # Create test user
    async with AsyncSession(engine) as session:
        await create_test_user(session)
    
    yield
    # Shutdown
    # Add any cleanup code here

# Add service initialization functions
def init_services():
    """Initialize all services"""
    document_processor = DocumentProcessor()
    redis_client = redis.Redis(
        host=settings.REDIS_HOST, 
        port=settings.REDIS_PORT, 
        db=settings.REDIS_DB
    )
    security_service = SecurityService(settings.SECRET_KEY, settings.ALGORITHM)
    project_service = ProjectService(document_processor)
    
    return document_processor, redis_client, security_service, project_service

def init_templates():
    """Initialize templates and static files"""
    templates = Jinja2Templates(directory="templates")
    return templates

def setup_cors(app: FastAPI):
    """Setup CORS middleware"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*", "Set-Cookie"],
    )

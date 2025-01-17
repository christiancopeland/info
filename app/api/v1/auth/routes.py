from fastapi import APIRouter, Depends, HTTPException, Body, Cookie, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import redis
from openai import OpenAI
import logging 
import uuid


from ....database import get_db
from ....models.user import User
from ....services.auth.security_service import SecurityService
from ....core.config import settings
from ....core.dependencies import test_api_connection, create_access_token, pwd_context, get_current_user


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
security_service = SecurityService(settings.SECRET_KEY, settings.ALGORITHM)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB
)

class CookieResponse(JSONResponse):
    def __init__(
        self,
        content: dict,
        token: str,
        status_code: int = 200,
        headers: Optional[dict] = None
    ):
        super().__init__(content=content, status_code=status_code, headers=headers)
        self.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,
            secure=False,  # Set to True in production
            samesite='lax',
            max_age=2592000,
            path="/",
            # Don't set domain at all for localhost/127.0.0.1
            # domain="localhost"  # Remove this line
        )
        # Add debug header
        self.headers["X-Debug-Cookie"] = token[:10]

@router.post("/register")
async def register_user(
    email: str = Body(...),
    password: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    try:
        # Check if user exists
        result = await db.execute(
            select(User).where(User.email == email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = pwd_context.hash(password)
        new_user = User(
            email=email,
            password_hash=hashed_password
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        return {"message": "User registered successfully"}
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login user and return access token"""
    try:
        # Debug: Log the email we're looking for
        logger.debug(f"Attempting login for email: {form_data.username}")
        
        # Debug: List all users in the database
        all_users_query = select(User)
        all_users_result = await db.execute(all_users_query)
        all_users = all_users_result.scalars().all()
        logger.debug("All users in database:")
        for u in all_users:
            logger.debug(f"User ID: {u.user_id}, Email: {u.email}")
        
        # Find user
        result = await db.execute(
            select(User).where(User.email == form_data.username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"No user found for email: {form_data.username}")
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password"
            )
        
        logger.debug(f"Found user: ID={user.user_id}, Email={user.email}")
        
        if not pwd_context.verify(form_data.password, user.password_hash):
            logger.error("Password verification failed")
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password"
            )
        
        # Create access token with actual user ID
        token = security_service.create_token({
            'sub': str(user.user_id),
            'client_id': str(user.user_id),
            'user_id': str(user.user_id)
        })
        
        logger.debug(f"Created token for user {user.email} with ID {user.user_id}")
        
        # Create a response with cookie
        response = CookieResponse(
            content={
                "access_token": token,
                "token_type": "bearer",
                "has_api_key": bool(user.openai_api_key)
            },
            token=token
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))
    

@router.post("/key")
async def store_api_key(
    request: Request,
    api_key: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Store API key in both Redis (for quick access) and Postgres (for persistence)"""
    logger.debug("Request received at /api/auth/key")
    logger.debug(f"Request headers: {dict(request.headers)}")
    logger.debug(f"Request cookies: {request.cookies}")
    logger.debug(f"Current user: {current_user.email if current_user else 'None'}")
    
    try:
        # Test the API key first
        client = OpenAI(api_key=api_key)
        await test_api_connection(client)
        
        # Generate a client_id
        client_id = str(uuid.uuid4())
        
        # Store in Redis
        redis_client.setex(
            f"api_key:{client_id}",
            2592000,  # 30 days
            api_key
        )
        
        # Store in Postgres
        current_user.openai_api_key = api_key
        db.add(current_user)
        await db.commit()
        
        # Create token that includes client_id
        token = security_service.create_token({
            'client_id': client_id,
            'user_id': str(current_user.user_id)
        })
        
        response = JSONResponse(content={"status": "success"})
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,
            secure=False,  # Set to True in production
            samesite='lax',
            max_age=2592000,
            path="/"
        )
        
        return response
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error storing API key: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid API key: {str(e)}")


@router.post("/test-key")
async def test_api_key(authorization: Optional[str] = Header(None)):
    """Test if an OpenAI API key is valid"""
    logger.debug(f"Received authorization header: {authorization}")
    
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="No API key provided")
    
    api_key = authorization.replace('Bearer ', '')
    logger.debug("Testing API key...")
    
    try:
        client = OpenAI(api_key=api_key)
        await test_api_connection(client)
        return {"status": "valid"}
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid API key: {str(e)}")
    

@router.get("/verify")
async def verify_auth(auth_token: Optional[str] = Cookie(None)):
    """Verify stored authentication"""
    if not auth_token:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated"
        )
    
    try:
        # Just verify the token is valid
        token_data = security_service.decode_token(auth_token)
        if not token_data:
            raise HTTPException(
                status_code=401, 
                detail="Invalid authentication token"
            )
        
        return {
            "status": "valid",
            "user_id": token_data.get('user_id'),
            "client_id": token_data.get('client_id')
        }
    except Exception as e:
        raise HTTPException(
            status_code=401, 
            detail="Invalid authentication token"
        )

@router.post("/logout")
async def logout():
    """Clear authentication cookie"""
    response = JSONResponse(content={"status": "success"})
    response.delete_cookie(key="auth_token", path="/")
    return response

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return {
        "user_id": current_user.user_id,
        "email": current_user.email
    }

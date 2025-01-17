import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Configuration variables
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")  # Change in production
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    postgresUser: str = os.getenv("POSTGRES_USER", "postgres")
    postgresPassword: str = os.getenv("POSTGRES_PASSWORD", "postgres")

    if postgresUser and postgresPassword:
        DATABASE_URL: str = f"postgresql+asyncpg://{postgresUser}:{postgresPassword}@localhost/research_platform"
        
    else:
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

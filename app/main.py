from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.dependencies import (
    lifespan, 
    init_services, 
    init_templates, 
    setup_cors,
    logger
)
from .api.v1.projects.routes import router as project_router
from .api.v1.auth.routes import router as auth_router
from .api.v1.websocket.routes import router as websocket_router
from .api.v1.news.routes import router as news_routes
from .api.v1.entities.routes import router as entities_router
from .api.v1.research_assistant.routes import router as research_assistant_router
# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    lifespan=lifespan
)

# Setup CORS
setup_cors(app)

# Set up templates and static files
templates = init_templates()
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(websocket_router, prefix="/api/v1/websocket", tags=["websocket"])
app.include_router(project_router, prefix="/api/v1", tags=["projects"])
app.include_router(news_routes, prefix="/api/v1/news", tags=["news"])
app.include_router(entities_router, prefix="/api/v1", tags=["entities"])
app.include_router(research_assistant_router, prefix="/api/v1/research_assistant", tags=["research_assistant"])

# Initialize services
document_processor, redis_client, security_service, project_service = init_services()

@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})




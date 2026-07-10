import warnings
# Suppress generative AI deprecation and metadata warnings during server startup
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database.connection import db_manager, get_db
from app.statement.upload.routes import router as statement_router
from app.database.connection import init_db, close_db, get_db
from app.auth.firebase import initialize_firebase
from app.auth.routes import router as auth_router
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: Initialize database engine & create tables
    db_manager.connect()
    await db_manager.create_tables()
    # Startup: Initialize Firebase Admin SDK
    initialize_firebase()
    # Startup: Create database tables (if not exist)
    await init_db()
    yield
    # Shutdown logic: Dispose database engine
    await db_manager.disconnect()

from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
    get_redoc_html,
)

from fastapi.openapi.utils import get_openapi
    # Shutdown: Dispose database engine
    await close_db()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Patch schema properties to ensure file uploads render correctly in Swagger UI
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        properties = schema.get("properties", {})
        for prop in properties.values():
            if prop.get("contentMediaType") == "application/octet-stream":
                prop["format"] = "binary"
            elif prop.get("type") == "array":
                items = prop.get("items", {})
                if items.get("contentMediaType") == "application/octet-stream":
                    items["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui-bundle.js",
        swagger_css_url="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.9.0/swagger-ui.css",
    )

@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://cdnjs.cloudflare.com/ajax/libs/redoc/2.1.3/redoc.standalone.js",
    )

# Enable CORS for frontend UI interaction (Rohan's dashboard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(statement_router)
    lifespan=lifespan
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api")

# ---------------------------------------------------------------------------
# Health / Root
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}"}


from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Perform a health check by pinging the PostgreSQL database to verify connectivity.
    Perform a health check by running a simple query against PostgreSQL.
    """
    try:
        # Send a ping query to the database
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "detail": str(e)}

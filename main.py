import warnings
# Suppress generative AI deprecation and metadata warnings during server startup
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import logging
# Configure logging format and level to display info/debug logs in the console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database.connection import init_db, close_db, get_db
from app.auth.firebase import initialize_firebase
from app.auth.routes import router as auth_router

from app.business.routes import router as business_router
from app.business.invite_routes import router as invite_router
from app.company.routes import router as company_router
from app.company.document_routes import router as document_router, package_router
from app.industry.routes import router as industry_router

# HR / CFO Module Routers
from app.api.employee.routes import router as employee_router
from app.api.vendor.routes import router as vendor_router
<<<<<<< HEAD
from app.api.dashboard.routes import router as dashboard_router
from app.api.chatbot.routes import router as chatbot_router
from app.api.spotlite.routes import router as spotlite_router
=======
from app.api.cfo.clients.routes import router as cfo_client_router
from app.api.dashboard.routes import router as dashboard_router, cfo_dashboard_router
from app.api.chatbot.routes import router as chatbot_router, cfo_chatbot_router
>>>>>>> 32dd859 (Implement CFO client and vendor agreement management)

from app.transaction.routes import router as transaction_router
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database engine, run migrations, and initialize Firebase SDK
    await init_db()
    initialize_firebase()
    yield
    # Shutdown: Dispose database engine
    await close_db()

from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
    get_redoc_html,
)
from fastapi.openapi.utils import get_openapi

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

# ---------------------------------------------------------------------------
# Request Logging Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    logger.info("----> [Request] %s %s | Host: %s | Origin: %s", request.method, request.url.path, host, origin)
    try:
        response = await call_next(request)
        logger.info("<---- [Response] %s %s | Status: %s", request.method, request.url.path, response.status_code)
        return response
    except Exception as e:
        logger.error("!!!!! [Exception] %s %s | Error: %s", request.method, request.url.path, e)
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal Server Error: {str(e)}"}
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

app.include_router(business_router, prefix="/api")
app.include_router(invite_router, prefix="/api")
app.include_router(company_router, prefix="/api")
app.include_router(document_router, prefix="/api/company")
app.include_router(package_router, prefix="/api/company")
app.include_router(industry_router, prefix="/api")

# HR Module Routers registered under prefix /api/v1/hr
app.include_router(employee_router, prefix="/api/v1/hr/employees", tags=["HR-Employee"])
app.include_router(dashboard_router, prefix="/api/v1/hr/dashboard", tags=["HR-Dashboard"])
app.include_router(chatbot_router, prefix="/api/v1/hr/chatbot", tags=["HR-Chatbot"])

# CFO Module Routers registered under prefix /api/v1/cfo
app.include_router(vendor_router, prefix="/api/v1/cfo/vendors", tags=["CFO-Vendor"])
app.include_router(cfo_client_router, prefix="/api/v1/cfo/clients", tags=["CFO-Client"])
app.include_router(cfo_dashboard_router, prefix="/api/v1/cfo/dashboard", tags=["CFO-Dashboard"])
app.include_router(cfo_chatbot_router, prefix="/api/v1/cfo/chatbot", tags=["CFO-Chatbot"])
app.include_router(transaction_router, prefix="/api")
app.include_router(spotlite_router, prefix="/api/v1/spotlite")

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

# Trigger reload

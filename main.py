from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database.connection import init_db, close_db, get_db
from app.auth.firebase import initialize_firebase
from app.auth.routes import router as auth_router
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Firebase Admin SDK
    initialize_firebase()
    # Startup: Create database tables (if not exist)
    await init_db()
    yield
    # Shutdown: Dispose database engine
    await close_db()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
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

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Perform a health check by running a simple query against PostgreSQL.
    """
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "detail": str(e)}

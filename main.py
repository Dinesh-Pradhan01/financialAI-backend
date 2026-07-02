from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from app.config import settings
from app.database.connection import db_manager, get_db
from motor.motor_asyncio import AsyncIOMotorDatabase

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: Connect to MongoDB
    db_manager.connect()
    yield
    # Shutdown logic: Disconnect from MongoDB
    db_manager.disconnect()

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}"}

@app.get("/health")
async def health_check(db: AsyncIOMotorDatabase = Depends(get_db)):
    """
    Perform a health check by pinging the MongoDB database to verify connectivity.
    """
    try:
        # Send a ping command to the database
        await db.command("ping")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "detail": str(e)}

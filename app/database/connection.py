import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

logger = logging.getLogger(__name__)

class MongoDBConnectionManager:
    def __init__(self):
        self.client: AsyncIOMotorClient = None
        self.db = None

    def connect(self):
        try:
            logger.info("Connecting to MongoDB...")
            self.client = AsyncIOMotorClient(settings.MONGODB_URL)
            self.db = self.client[settings.DATABASE_NAME]
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
            raise e

    def disconnect(self):
        if self.client is not None:
            logger.info("Closing MongoDB connection...")
            self.client.close()
            logger.info("MongoDB connection closed.")
            self.client = None
            self.db = None

db_manager = MongoDBConnectionManager()

async def get_db():
    """FastAPI Dependency for accessing the MongoDB database instance."""
    if db_manager.db is None:
        raise RuntimeError("Database not initialized. Please call connect() first.")
    return db_manager.db

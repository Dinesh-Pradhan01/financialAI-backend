from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List
import os
from dotenv import load_dotenv
load_dotenv()
class Settings(BaseSettings):
    APP_NAME: str = "Spotlite Backend API"
    DEBUG: bool = False
    
    # Database settings
    DATABASE_URL: str = "postgresql://localhost/postgres"

    # AI settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # PostgreSQL (NeonDB) settings
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    @field_validator("DATABASE_URL")
    @classmethod
    def convert_postgres_scheme(cls, v: str) -> str:
        """Ensure we use asyncpg driver even if the user pastes a standard postgresql:// URL."""
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg does not support channel_binding query param
        if "channel_binding=require" in v:
            v = v.replace("&channel_binding=require", "").replace("?channel_binding=require", "")
        # asyncpg expects ssl=require instead of sslmode=require
        if "sslmode=" in v:
            v = v.replace("sslmode=", "ssl=")
        return v

    # Firebase settings
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID")
    FIREBASE_CREDENTIALS_PATH: str = os.getenv("FIREBASE_CREDENTIALS_PATH")

    # CORS settings
    CORS_ORIGINS: str = "http://localhost:8000,http://localhost:8080"
    FRONTEND_URL: str = "http://localhost:8080"

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS string into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        url = self.DATABASE_URL.strip("\"'")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Strip query parameters that cause TypeErrors in asyncpg connect()
        if "?" in url:
            url = url.split("?")[0]
        return url

settings = Settings()


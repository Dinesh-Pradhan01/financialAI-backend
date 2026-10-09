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
    
    # AI settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # PostgreSQL (NeonDB) settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost/postgres")

    @field_validator("DATABASE_URL")
    @classmethod
    def convert_postgres_scheme(cls, v: str) -> str:
        """Ensure we use asyncpg driver even if the user pastes a standard postgresql:// URL."""
        v = v.strip("\"'")
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
    FIREBASE_PROJECT_ID: Optional[str] = os.getenv("FIREBASE_PROJECT_ID")
    FIREBASE_CREDENTIALS_PATH: Optional[str] = os.getenv("FIREBASE_CREDENTIALS_PATH")
    FIREBASE_CREDENTIALS_BASE64: Optional[str] = os.getenv("FIREBASE_CREDENTIALS_BASE64")

    # CORS settings — must be set in .env / Railway Variables.
    # CORS_ORIGINS: comma-separated list of allowed frontend origins.
    # Example: http://localhost:8080,https://app.yourdomain.com
    CORS_ORIGINS: str = "http://localhost:8080"   # safe fallback for local dev only
    FRONTEND_URL: str = "http://localhost:8080"   # safe fallback for local dev only

    # Groq LLM & Document Extraction Settings
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    LLM_TEMPERATURE: float = 0.0
    LLM_TIMEOUT: int = 60
    MAX_DOCUMENT_SIZE_MB: int = 15
    MIN_TEXT_LENGTH: int = 100
    OCR_ENABLED: bool = True
    OCR_LANGUAGE: str = "eng"
    EXTRACTION_MAX_RETRIES: int = 2

    #SendGrid Mail-Service
    SENDER_EMAIL: str = os.getenv('SENDER_EMAIL')
    SENDGRID_API_KEY: str = os.getenv('SENDGRID_API_KEY')

    # Storage settings
    UPLOAD_DIR: str = os.getenv(
        "UPLOAD_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    )
    S3_BUCKET_NAME: Optional[str] = os.getenv("S3_BUCKET_NAME", os.getenv("AWS_STORAGE_BUCKET_NAME"))
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_ASSUME_ROLE_ARN: Optional[str] = os.getenv("AWS_ASSUME_ROLE_ARN")
    AWS_ROLE_SESSION_NAME: str = os.getenv("AWS_ROLE_SESSION_NAME", "spotlite-session")
    AWS_REGION: str = os.getenv("AWS_REGION", os.getenv("AWS_S3_REGION_NAME", "us-east-1"))
    AWS_ENDPOINT_URL: Optional[str] = os.getenv("AWS_ENDPOINT_URL", os.getenv("AWS_S3_ENDPOINT_URL"))

    #absolute path
    #APP_DIR = os.path.dirname(os.path.abspath(__file__))

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


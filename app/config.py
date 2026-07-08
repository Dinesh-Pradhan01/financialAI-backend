from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Spotlite Backend API"
    DEBUG: bool = False
    
    # Database settings
    DATABASE_URL: str = "postgresql://localhost/postgres"

    # AI settings
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

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


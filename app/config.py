from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "Spotlite Backend API"
    DEBUG: bool = False
    
    # MongoDB settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "spotlite_db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

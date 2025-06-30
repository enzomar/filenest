import os
from pydantic_settings import BaseSettings

ENV = os.environ.get("ENV", "prod").lower()  # Define this at module level

class Settings(BaseSettings):
    API_KEY: str = "supersecretapikey"
    API_KEY_NAME: str = "x-api-key"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    STORAGE_DIR: str = "storage"
    DB_PATH: str = "./data/records_metadata.sqlite"
    CORS_ORIGINS: list[str] = ["http://localhost:8000"]
    ENV: str = ENV  # Include ENV if you want to access it from settings later
    class Config:
        env_file = "../.env" if ENV == "dev" else ".env"

settings = Settings()

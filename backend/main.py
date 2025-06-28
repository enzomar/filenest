import os
import uuid
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException, Security, status, Request

from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import conint, validator
from pydantic_settings import BaseSettings

from sqlalchemy import create_engine, Column, String, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import text


# -------------------------
# Config & Settings
# -------------------------

class Settings(BaseSettings):
    API_KEY: str = "supersecretapikey"
    API_KEY_NAME: str = "x-api-key"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    STORAGE_DIR: str = "storage"
    DATABASE_URL: str = "sqlite:///./data/file_metadata.db"
    CLEANUP_INTERVAL_SEC: int = 60
    MAX_TTL_SECONDS: int = 60 * 60 * 24 * 30  # max 30 days TTL

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()

# -------------------------
# Logging Setup
# -------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# -------------------------
# DB Setup
# -------------------------
# Fix DB folder existence and absolute path for SQLite
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///"):
    db_path = db_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(os.path.abspath(db_path)) or "."
    os.makedirs(db_dir, exist_ok=True)
    settings.DATABASE_URL = f"sqlite:///{os.path.abspath(db_path)}"

engine = create_engine(
    settings.DATABASE_URL, connect_args={"check_same_thread": False}
)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class FileMeta(Base):
    __tablename__ = "filemeta"
    id = Column(String, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    upload_time = Column(DateTime, default=datetime.utcnow)
    ttl_seconds = Column(Integer, nullable=True)

Base.metadata.create_all(bind=engine)

# -------------------------
# FastAPI app & Security
# -------------------------

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if api_key == settings.API_KEY:
        return api_key
    logger.warning("Unauthorized access attempt with API key: %s", api_key)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")

app = FastAPI(title="FileNest - Secure TTL File Storage")

# CORS - configure origins as needed for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourfrontend.domain"],  # change or add your domains
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

os.makedirs(settings.STORAGE_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.STORAGE_DIR), name="files")

# -------------------------
# DB session helper
# -------------------------

def get_db_session() -> Session:
    return SessionLocal()

# -------------------------
# Validators
# -------------------------

def validate_ttl(ttl: Optional[int]) -> Optional[int]:
    if ttl is not None:
        if ttl <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ttl_seconds must be positive"
            )
        if ttl > settings.MAX_TTL_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ttl_seconds cannot exceed {settings.MAX_TTL_SECONDS} seconds"
            )
    return ttl

# -------------------------
# Routes
# -------------------------

@app.post("/upload/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[conint(gt=0)] = None,
    api_key: str = Security(get_api_key)
) -> JSONResponse:
    ttl_seconds = validate_ttl(ttl_seconds)
    safe_filename = os.path.basename(file.filename)  # Prevent path traversal
    file_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    logger.info(f"Start uploading file {safe_filename}")

    # Check if file already exists
    if os.path.exists(file_path):
        logger.warning(f"Upload failed: file {safe_filename} already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{safe_filename}' already exists."
        )

    size = 0
    try:
        async with aiofiles.open(file_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_FILE_SIZE:
                    await out_file.close()
                    await aiofiles.os.remove(file_path)
                    logger.warning(f"File {safe_filename} rejected: size > {settings.MAX_FILE_SIZE}")
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Max size is {settings.MAX_FILE_SIZE // (1024 * 1024)} MB."
                    )
                await out_file.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {safe_filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Save metadata
    with get_db_session() as db:
        meta = FileMeta(id=safe_filename, filename=safe_filename, ttl_seconds=ttl_seconds)
        db.add(meta)
        db.commit()

    full_url = f"{request.base_url}files/{safe_filename}"
    logger.info(f"File {safe_filename} uploaded successfully")

    return JSONResponse({"file_url": full_url})



@app.get("/health", tags=["Health"])
def health_check():
    try:
        with get_db_session() as db:
            db.execute(text("SELECT 1"))  # wrap raw SQL in text()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")


# -------------------------
# Background cleanup task
# -------------------------

async def cleanup_files_task():
    while True:
        await asyncio.sleep(settings.CLEANUP_INTERVAL_SEC)
        now = datetime.utcnow()
        with get_db_session() as db:
            expired_files = db.query(FileMeta).filter(
                FileMeta.ttl_seconds.isnot(None),
                (FileMeta.upload_time + timedelta(seconds=FileMeta.ttl_seconds)) < now
            ).all()

            if not expired_files:
                continue

            for f in expired_files:
                file_path = os.path.join(settings.STORAGE_DIR, f.filename)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Deleted expired file {f.filename}")
                    except Exception as e:
                        logger.error(f"Error deleting file {f.filename}: {e}")

                db.delete(f)
            db.commit()

@app.on_event("startup")
async def on_startup():
    logger.info("Starting cleanup task")
    asyncio.create_task(cleanup_files_task())

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down")


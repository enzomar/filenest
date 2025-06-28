import os
import asyncio
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, conint

import aiofiles
from fastapi import (
    FastAPI, UploadFile, File, HTTPException,
    Security, status, Request
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from sqlalchemy import create_engine, Column, String, DateTime, Integer, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

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
# Helpers
# -------------------------

def get_db_session() -> Session:
    return SessionLocal()

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

async def save_file_bytes(file_path: str, file_bytes: bytes) -> None:
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size is {settings.MAX_FILE_SIZE // (1024 * 1024)} MB."
        )
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(file_bytes)

def save_file_metadata(filename: str, ttl_seconds: Optional[int]) -> None:
    with get_db_session() as db:
        meta = FileMeta(id=filename, filename=filename, ttl_seconds=ttl_seconds)
        db.add(meta)
        db.commit()

async def write_uploadfile_to_disk(file: UploadFile, file_path: str) -> None:
    size = 0
    async with aiofiles.open(file_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                await out_file.close()
                await aiofiles.os.remove(file_path)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Max size is {settings.MAX_FILE_SIZE // (1024 * 1024)} MB."
                )
            await out_file.write(chunk)

# -------------------------
# Request Models
# -------------------------

class Base64UploadRequest(BaseModel):
    filename: str
    content_base64: str
    ttl_seconds: Optional[conint(gt=0)] = None

# -------------------------
# Routes
# -------------------------

@app.post("/upload_base64/", status_code=status.HTTP_201_CREATED)
async def upload_file_base64(
    request: Request,
    body: Base64UploadRequest,
    api_key: str = Security(get_api_key),
) -> JSONResponse:
    ttl_seconds = validate_ttl(body.ttl_seconds)
    safe_filename = os.path.basename(body.filename)
    file_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    logger.info(f"Start uploading base64 file {safe_filename}")

    if os.path.exists(file_path):
        logger.warning(f"Upload failed: file {safe_filename} already exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"File '{safe_filename}' already exists.")

    try:
        file_bytes = base64.b64decode(body.content_base64)
    except Exception as e:
        logger.warning(f"Invalid base64 content for file {safe_filename}: {e}")
        raise HTTPException(status_code=400, detail="Invalid base64 content")

    await save_file_bytes(file_path, file_bytes)
    save_file_metadata(safe_filename, ttl_seconds)

    full_url = f"{request.base_url}files/{safe_filename}"
    logger.info(f"Base64 file {safe_filename} uploaded successfully")
    return JSONResponse({"file_url": full_url})


@app.post("/upload/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[conint(gt=0)] = None,
    api_key: str = Security(get_api_key)
) -> JSONResponse:
    ttl_seconds = validate_ttl(ttl_seconds)
    safe_filename = os.path.basename(file.filename)
    file_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    logger.info(f"Start uploading file {safe_filename}")

    if os.path.exists(file_path):
        logger.warning(f"Upload failed: file {safe_filename} already exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"File '{safe_filename}' already exists.")

    try:
        await write_uploadfile_to_disk(file, file_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {safe_filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    save_file_metadata(safe_filename, ttl_seconds)

    full_url = f"{request.base_url}files/{safe_filename}"
    logger.info(f"File {safe_filename} uploaded successfully")

    return JSONResponse({"file_url": full_url})

@app.get("/health", tags=["Health"])
def health_check():
    try:
        with get_db_session() as db:
            db.execute(text("SELECT 1"))
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

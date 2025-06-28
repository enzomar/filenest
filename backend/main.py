import os
import uuid
import json
import base64
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Generator

import aiofiles
from fastapi import (
    FastAPI, UploadFile, File, Form, HTTPException,
    Security, status, Request, Depends
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, conint, BaseSettings
from sqlalchemy import (
    create_engine, Column, String, DateTime, Integer, JSON, text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# --------------
# Settings
# --------------

class Settings(BaseSettings):
    API_KEY: str = "supersecretapikey"
    API_KEY_NAME: str = "x-api-key"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    STORAGE_DIR: str = "storage"
    DATABASE_URL: str = "sqlite:///./data/file_metadata.db"
    CLEANUP_INTERVAL_SEC: int = 60
    MAX_TTL_SECONDS: int = 60 * 60 * 24 * 30  # 30 days TTL
    DEFAULT_TTL_SECONDS: int = 60 * 60  # 1 hour default TTL
    CORS_ORIGINS: list[str] = ["https://yourfrontend.domain"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

# --------------
# Logging
# --------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("filenest")

# --------------
# Database Setup
# --------------

db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///"):
    db_path = db_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(os.path.abspath(db_path)) or "."
    os.makedirs(db_dir, exist_ok=True)
    settings.DATABASE_URL = f"sqlite:///{os.path.abspath(db_path)}"

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

class FileMeta(Base):
    __tablename__ = "filemeta"

    id = Column(String, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    ttl_seconds = Column(Integer, nullable=True)
    metadata = Column(JSON, nullable=True)

Base.metadata.create_all(bind=engine)

# --------------
# Security
# --------------

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if api_key == settings.API_KEY:
        return api_key
    logger.warning(f"Unauthorized access attempt with API key: {api_key}")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")

# --------------
# FastAPI App Initialization
# --------------

app = FastAPI(title="FileNest - Secure TTL File Storage")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

os.makedirs(settings.STORAGE_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.STORAGE_DIR), name="files")

# --------------
# Helpers
# --------------

def get_db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def validate_ttl(ttl: Optional[int]) -> int:
    if ttl is None:
        return settings.DEFAULT_TTL_SECONDS
    if ttl <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ttl_seconds must be positive",
        )
    if ttl > settings.MAX_TTL_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ttl_seconds cannot exceed {settings.MAX_TTL_SECONDS} seconds",
        )
    return ttl

async def save_file_bytes(file_path: str, file_bytes: bytes) -> None:
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size is {settings.MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(file_bytes)

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
                    detail=f"File too large. Max size is {settings.MAX_FILE_SIZE // (1024 * 1024)} MB.",
                )
            await out_file.write(chunk)

def save_file_metadata(
    db: Session, filename: str, ttl_seconds: int, metadata: Optional[Dict[str, Any]]
) -> str:
    record_id = str(uuid.uuid4())
    meta = FileMeta(
        id=record_id,
        filename=filename,
        ttl_seconds=ttl_seconds,
        metadata=metadata,
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta.id

# --------------
# Request Models
# --------------

class Base64UploadRequest(BaseModel):
    filename: str
    content_base64: str
    ttl_seconds: Optional[conint(gt=0)] = None

# --------------
# Routes
# --------------

@app.post("/upload_base64/", status_code=status.HTTP_201_CREATED)
async def upload_file_base64(
    request: Request,
    body: Base64UploadRequest,
    api_key: str = Security(get_api_key),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    ttl_seconds = validate_ttl(body.ttl_seconds)
    safe_filename = os.path.basename(body.filename)
    file_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    logger.info(f"Start uploading base64 file {safe_filename}")

    if os.path.exists(file_path):
        logger.warning(f"Upload failed: file {safe_filename} already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{safe_filename}' already exists.",
        )

    try:
        file_bytes = base64.b64decode(body.content_base64)
    except Exception as e:
        logger.warning(f"Invalid base64 content for file {safe_filename}: {e}")
        raise HTTPException(status_code=400, detail="Invalid base64 content")

    await save_file_bytes(file_path, file_bytes)
    record_id = save_file_metadata(db, safe_filename, ttl_seconds, None)

    full_url = f"{request.base_url}files/{safe_filename}"
    logger.info(f"Base64 file {safe_filename} uploaded successfully")
    return JSONResponse({"id": record_id, "file_url": full_url})

@app.post("/upload/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[conint(gt=0)] = None,
    api_key: str = Security(get_api_key),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    ttl_seconds = validate_ttl(ttl_seconds)
    safe_filename = os.path.basename(file.filename)
    file_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    logger.info(f"Start uploading file {safe_filename}")

    if os.path.exists(file_path):
        logger.warning(f"Upload failed: file {safe_filename} already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{safe_filename}' already exists.",
        )

    try:
        await write_uploadfile_to_disk(file, file_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {safe_filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    record_id = save_file_metadata(db, safe_filename, ttl_seconds, None)

    full_url = f"{request.base_url}files/{safe_filename}"
    logger.info(f"File {safe_filename} uploaded successfully")

    return JSONResponse({"id": record_id, "file_url": full_url})

@app.post("/upload_with_metadata/", status_code=status.HTTP_201_CREATED)
async def upload_with_metadata(
    request: Request,
    file: UploadFile = File(...),
    metadata_json: str = Form(...),
    ttl_seconds: Optional[conint(gt=0)] = Form(None),
    api_key: str = Security(get_api_key),
    db: Session = Depends(get_db_session),
) -> JSONResponse:
    ttl_seconds = validate_ttl(ttl_seconds)
    safe_filename = os.path.basename(file.filename)
    file_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    logger.info(f"Start uploading file with metadata: {safe_filename}")

    if os.path.exists(file_path):
        logger.warning(f"Upload failed: file {safe_filename} already exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{safe_filename}' already exists.",
        )

    try:
        await write_uploadfile_to_disk(file, file_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {safe_filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    try:
        metadata = json.loads(metadata_json)
    except Exception as e:
        os.remove(file_path)
        logger.warning(f"Invalid JSON metadata for file {safe_filename}: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON metadata")

    record_id = save_file_metadata(db, safe_filename, ttl_seconds, metadata)

    full_url = f"{request.base_url}files/{safe_filename}"
    logger.info(f"File {safe_filename} with metadata uploaded successfully")

    return JSONResponse({"id": record_id, "file_url": full_url})

@app.get("/metadata/{record_id}")
def get_metadata(
    record_id: str,
    request: Request,
    api_key: str = Security(get_api_key),
    db: Session = Depends(get_db_session),
) -> Dict[str, Any]:
    record = db.query(FileMeta).filter(FileMeta.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    full_url = f"{request.base_url}files/{record.filename}"
    return {
        "id": record.id,
        "file_url": full_url,
        "metadata": record.metadata,
        "ttl_seconds": record.ttl_seconds,
        "upload_time": record.upload_time.isoformat(),
    }

@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db_session)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}")
        raise HTTPException(status_code=500, detail="Database connection failed")

# --------------
# Background Cleanup Task
# --------------

async def cleanup_files_task():
    while True:
        await asyncio.sleep(settings.CLEANUP_INTERVAL_SEC)
        now = datetime.utcnow()
        with SessionLocal() as db:
            expired_files = db.query(FileMeta).filter(
                FileMeta.ttl_seconds.isnot(None),
                (FileMeta.upload_time + timedelta(seconds=FileMeta.ttl_seconds)) < now
            ).all()

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

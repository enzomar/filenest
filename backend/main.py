# This is a simplified version of your FastAPI app using TinyDB instead of SQLAlchemy

import os
import uuid
import json
import base64
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import aiofiles
from fastapi import (
    FastAPI, UploadFile, File, Form, HTTPException, Path,
    Security, status, Request, Depends, Query as FastAPIQuery
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, conint 
from pydantic_settings import BaseSettings
from tinydb import TinyDB, Query


# --------------
# Settings
# --------------

class Settings(BaseSettings):
    API_KEY: str = "supersecretapikey"
    API_KEY_NAME: str = "x-api-key"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    STORAGE_DIR: str = "storage"
    DB_PATH: str = "./data/file_metadata.json"
    CLEANUP_INTERVAL_SEC: int = 60
    MAX_TTL_SECONDS: int = 60 * 60 * 24 * 30  # 30 days TTL
    DEFAULT_TTL_SECONDS: int = 60 * 60  # 1 hour default TTL
    CORS_ORIGINS: list[str] = ["https://yourfrontend.domain"]

    class Config:
        env_file = ".env"

settings = Settings()

# --------------
# Logging
# --------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("filenest")

# --------------
# Database Setup (TinyDB)
# --------------

os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
db = TinyDB(settings.DB_PATH)
FileTable = db.table("files")

# --------------
# FastAPI Setup
# --------------

app = FastAPI(title="FileNest - TinyDB Edition")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.STORAGE_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.STORAGE_DIR), name="files")

# --------------
# Security
# --------------

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if api_key == settings.API_KEY:
        return api_key
    raise HTTPException(status_code=403, detail="Invalid API Key")

# --------------
# Helpers
# --------------

def validate_ttl(ttl: Optional[int]) -> int:
    if ttl is None:
        return settings.DEFAULT_TTL_SECONDS
    if ttl <= 0 or ttl > settings.MAX_TTL_SECONDS:
        raise HTTPException(400, "Invalid TTL")
    return ttl

async def save_file_bytes(file_path: str, file_bytes: bytes):
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise HTTPException(413, "File too large")
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(file_bytes)

async def write_uploadfile_to_disk(file: UploadFile, file_path: str):
    size = 0
    async with aiofiles.open(file_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                raise HTTPException(413, "File too large")
            await out_file.write(chunk)

# --------------
# Models
# --------------

class Base64UploadRequest(BaseModel):
    filename: str
    content_base64: str
    ttl_seconds: Optional[conint(gt=0)] = None

class UpdateMetadataRequest(BaseModel):
    metadata: Optional[Dict[str, Any]] = None

# --------------
# Routes
# --------------

@app.post("/records/")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[conint(gt=0)] = Form(None),
    metadata_json: Optional[str] = Form(None),
    api_key: str = Security(get_api_key)
):
    ttl = validate_ttl(ttl_seconds)
    file_id = str(uuid.uuid4())
    filename = os.path.basename(file.filename)
    file_path = os.path.join(settings.STORAGE_DIR, filename)

    if os.path.exists(file_path):
        raise HTTPException(409, "File already exists")

    await write_uploadfile_to_disk(file, file_path)

    metadata = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception:
            raise HTTPException(400, "Invalid JSON metadata")

    now = datetime.utcnow().isoformat()

    FileTable.insert({
        "id": file_id,
        "filename": filename,
        "upload_time": now,
        "ttl_seconds": ttl,
        "metadata": metadata,
        "created_at": now,
        "updated_at": now
    })

    return {"id": file_id, "file_url": f"{request.base_url}files/{filename}"}

@app.get("/records/{record_id}")
def get_metadata(record_id: str, request: Request, api_key: str = Security(get_api_key)):
    File = Query()
    result = FileTable.get(File.id == record_id)
    if not result:
        raise HTTPException(404, "Record not found")

    return {
        "id": result["id"],
        "file_url": f"{request.base_url}files/{result['filename']}",
        "metadata": result["metadata"],
        "ttl_seconds": result["ttl_seconds"],
        "upload_time": result["upload_time"],
        "created_at": result["created_at"],
        "updated_at": result["updated_at"]
    }

@app.get("/records")
def search_metadata(
    key: str = FastAPIQuery(..., description="Metadata key to search for"),
    value: str = FastAPIQuery(..., description="Value to match"),
    value_type: str = FastAPIQuery("string", regex="^(string|boolean|number|datetime)$", description="Type of the value"),
    limit: int = FastAPIQuery(50, ge=1, le=1000, description="Maximum number of records to return"),
    api_key: str = Security(get_api_key)
):
    def cast_value(v, vtype):
        try:
            if vtype == "string":
                return str(v)
            elif vtype == "boolean":
                return v.lower() == "true"
            elif vtype == "number":
                return float(v) if '.' in v else int(v)
            elif vtype == "datetime":
                return datetime.fromisoformat(v)
        except Exception:
            return v  # fallback

    results = []
    for record in FileTable.all():
        meta = record.get("metadata", {})
        val = meta.get(key)
        if val is None:
            continue

        try:
            val_casted = cast_value(str(val), value_type)
            value_casted = cast_value(value, value_type)
        except Exception:
            continue

        if val_casted == value_casted:
            results.append(record)
            if len(results) >= limit:
                break

    return results


@app.delete("/records/{record_id}", status_code=200)
def delete_file(
    record_id: str = Path(..., description="ID of the file to delete"),
    api_key: str = Security(get_api_key),
):
    File = Query()
    result = FileTable.get(File.id == record_id)
    if not result:
        raise HTTPException(404, "File not found")

    file_path = os.path.join(settings.STORAGE_DIR, result["filename"])
    if os.path.exists(file_path):
        os.remove(file_path)

    FileTable.remove(File.id == record_id)
    return {"status": "success", "message": f"File '{result['filename']}' deleted."}

@app.put("/records/{record_id}/metadata", status_code=200)
def update_metadata(
    record_id: str = Path(..., description="ID of the file metadata to update"),
    body: UpdateMetadataRequest = ...,
    api_key: str = Security(get_api_key),
):
    File = Query()
    now = datetime.utcnow().isoformat()
    updated = FileTable.update({"metadata": body.metadata, "updated_at": now}, File.id == record_id)
    if not updated:
        raise HTTPException(404, "File not found")
    return {"status": "success", "message": "Metadata updated."}


@app.get("/health", tags=["Health"])
def health_check():
    try:
        _ = FileTable.all()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}")
        raise HTTPException(status_code=500, detail="TinyDB connection failed")

# --------------
# Background Task
# --------------

async def cleanup_task():
    while True:
        await asyncio.sleep(settings.CLEANUP_INTERVAL_SEC)
        now = datetime.utcnow()
        File = Query()
        records = FileTable.all()
        for record in records:
            if record["ttl_seconds"] is None:
                continue
            expiry = datetime.fromisoformat(record["upload_time"]) + timedelta(seconds=record["ttl_seconds"])
            if expiry < now:
                file_path = os.path.join(settings.STORAGE_DIR, record["filename"])
                if os.path.exists(file_path):
                    os.remove(file_path)
                FileTable.remove(File.id == record["id"])

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(cleanup_task())

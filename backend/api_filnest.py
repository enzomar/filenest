from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException, Request,
    Security, Query as FastAPIQuery, status
)
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
from tempfile import NamedTemporaryFile
import uuid
import json
import os
import shutil

from security import get_api_key
from storage import (
    save_uploadfile,
    insert_file_metadata,
    get_file_metadata_by_id,
    remove_file_metadata,
    update_metadata,
    settings,
    create_bucket,
    delete_bucket as delete_bucket_helper,
    list_buckets as list_buckets_helper,
    search_metadata,
    db
)

router = APIRouter(prefix="/api/v1", tags=["filenest"])

# -------------------------------
# Models
# -------------------------------

class StatusResponse(BaseModel):
    status: str = Field(..., example="success")
    message: str

class FileUploadResponse(BaseModel):
    id: str
    file_url: str

class FileRecord(BaseModel):
    id: str
    file_url: str
    metadata: Optional[Dict[str, Any]] = None
    ttl_seconds: Optional[int] = None
    upload_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FileRecordSummary(BaseModel):
    id: str
    file_url: str

class BucketListResponse(BaseModel):
    buckets: List[str]

# -------------------------------
# Utility Functions
# -------------------------------

def validate_filename(filename: str) -> str:
    return filename.replace("..", "")  # Basic sanitization

# -------------------------------
# Bucket Routes
# -------------------------------

@router.post("/buckets/{bucket}", response_model=StatusResponse)
def create_bucket_route(bucket: str, api_key: str = Security(get_api_key)):
    if bucket in db.tables():
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Bucket '{bucket}' already exists.")
    create_bucket(bucket)
    return {"status": "success", "message": f"Bucket '{bucket}' created."}

@router.get("/buckets", response_model=BucketListResponse)
def list_buckets(api_key: str = Security(get_api_key)):
    return {"buckets": list_buckets_helper()}

@router.delete("/buckets/{bucket}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bucket(bucket: str, api_key: str = Security(get_api_key)):
    try:
        delete_bucket_helper(bucket)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return None

# -------------------------------
# File Routes
# -------------------------------

@router.post("/buckets/{bucket}/records/", response_model=FileUploadResponse)
async def upload_file(
    bucket: str,
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[int] = Form(None),
    metadata_json: Optional[str] = Form(None),
    api_key: str = Security(get_api_key)
):
    create_bucket(bucket, True)
    ttl = ttl_seconds if ttl_seconds and 0 < ttl_seconds <= settings.MAX_FILE_SIZE else 3600

    file_id = str(uuid.uuid4())
    safe_filename = validate_filename(file.filename)
    temp_file = NamedTemporaryFile(delete=False)
    await save_uploadfile(file, temp_file.name)

    metadata = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            os.remove(temp_file.name)
            raise HTTPException(400, detail="Invalid JSON metadata")

    try:
        insert_file_metadata(file_id, safe_filename, bucket, ttl, metadata)
    except Exception as e:
        os.remove(temp_file.name)
        raise HTTPException(500, detail=f"Failed to save metadata: {str(e)}")

    final_path = os.path.join(settings.STORAGE_DIR, bucket, safe_filename)
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    shutil.move(temp_file.name, final_path)

    return {"id": file_id, "file_url": f"{request.base_url}files/{bucket}/{safe_filename}"}

@router.get("/buckets/{bucket}/records/{record_id}", response_model=FileRecord)
def get_record(bucket: str, record_id: str, request: Request, api_key: str = Security(get_api_key)):
    record = get_file_metadata_by_id(record_id, bucket)
    if not record:
        raise HTTPException(404, detail="Record not found")
    return {
        "id": record["id"],
        "file_url": f"{request.base_url}files/{bucket}/{record['filename']}",
        "metadata": record.get("metadata"),
        "ttl_seconds": record.get("ttl_seconds"),
        "upload_time": record.get("upload_time"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at")
    }

@router.delete("/buckets/{bucket}/records/{record_id}", response_model=StatusResponse)
def delete_record(bucket: str, record_id: str, api_key: str = Security(get_api_key)):
    record = get_file_metadata_by_id(record_id, bucket)
    if not record:
        raise HTTPException(404, detail="File not found")

    remove_file_metadata(record_id, bucket)
    file_path = os.path.join(settings.STORAGE_DIR, bucket, record['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    return {"status": "success", "message": f"File '{record['filename']}' deleted."}

@router.put("/buckets/{bucket}/records/{record_id}/metadata", response_model=StatusResponse)
def update_record_metadata(bucket: str, record_id: str, metadata: Dict[str, Any], api_key: str = Security(get_api_key)):
    if not update_metadata(record_id, bucket, metadata):
        raise HTTPException(404, detail="File not found")
    return {"status": "success", "message": "Metadata updated."}

@router.get("/buckets/{bucket}/records", response_model=List[FileRecordSummary])
def list_or_search_records(
    bucket: str,
    request: Request,
    key: Optional[str] = FastAPIQuery(None),
    value: Optional[str] = FastAPIQuery(None),
    value_type: str = FastAPIQuery("string", regex="^(string|boolean|number|datetime)$"),
    limit: int = FastAPIQuery(50, ge=1, le=1000),
    api_key: str = Security(get_api_key)
):
    records = search_metadata(bucket, key, value, value_type, limit)
    return [
        FileRecordSummary(
            id=record["id"],
            file_url=f"{request.base_url}files/{bucket}/{record['filename']}"
        ) for record in records
    ]

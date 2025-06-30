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
    update_metadata as update_metadata_helper,
    settings,
    create_bucket as create_bucket_helper,
    delete_bucket as delete_bucket_helper,
    list_buckets as list_buckets_helper,
    search_metadata
)

router = APIRouter(prefix="/api/v1")

# -------------------------------
# Models
# -------------------------------

class StatusResponse(BaseModel):
    """Standard response indicating success or failure status."""
    status: str = Field(..., example="success")
    message: str

class FileUploadResponse(BaseModel):
    """Response returned after a successful file upload."""
    id: str
    file_url: str

class FileRecord(BaseModel):
    """Detailed information about a file record."""
    id: str
    file_url: str
    metadata: Optional[Dict[str, Any]] = None
    ttl_seconds: Optional[int] = None
    upload_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FileRecordSummary(BaseModel):
    """Summary information of a file record for listings."""
    id: str
    file_url: str

class BucketListResponse(BaseModel):
    """List of bucket names."""
    buckets: List[str]

class MetadataFieldUpdate(BaseModel):
    """Request body for updating a single metadata field."""
    key: str
    value: Any

# -------------------------------
# Utility Functions
# -------------------------------

def validate_filename(filename: str) -> str:
    """
    Sanitize the filename by removing potentially dangerous parts.

    Currently replaces '..' with ''.
    """
    return filename.replace("..", "")

# -------------------------------
# Bucket Routes
# -------------------------------

@router.post("/buckets/{bucket}", response_model=StatusResponse, tags=["Buckets"])
def create_bucket(bucket: str, api_key: str = Security(get_api_key)):
    """
    Create a new bucket with the specified name.

    - Returns 409 Conflict if the bucket already exists.
    - Bucket names should be unique.
    """
    create_bucket_helper(bucket)
    return {"status": "success", "message": f"Bucket '{bucket}' created."}

@router.get("/buckets", response_model=BucketListResponse, tags=["Buckets"])
def list_buckets(api_key: str = Security(get_api_key)):
    """
    List all existing buckets.

    Returns a list of bucket names.
    """
    return {"buckets": list_buckets_helper()}

@router.delete("/buckets/{bucket}", status_code=status.HTTP_204_NO_CONTENT, tags=["Buckets"])
def delete_bucket(bucket: str, api_key: str = Security(get_api_key)):
    """
    Delete the specified bucket and all its contents.

    - Returns 404 if the bucket does not exist.
    """
    try:
        delete_bucket_helper(bucket)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))
    return None

# -------------------------------
# Records Routes
# -------------------------------

@router.post("/buckets/{bucket}/records/", response_model=FileUploadResponse, tags=["Records"])
async def create_record(
    bucket: str,
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[int] = Form(None),
    metadata_json: Optional[str] = Form(None),
    api_key: str = Security(get_api_key)
):
    """
    Upload a new file record to the specified bucket.

    - **bucket**: Name of the bucket. If the bucket does not exist, it will be created automatically.
    - **file**: The file to upload.
    - **ttl_seconds**: Optional TTL (time to live) in seconds for the file. Defaults to 3600 seconds if omitted or invalid. Set to 0 to disable it.
    - **metadata_json**: Optional JSON string with additional metadata for the file.
    - **api_key**: API key for authorization.

    Returns the ID and accessible URL of the uploaded file.
    """
    create_bucket_helper(bucket, exist_ok=True)
    ttl = ttl_seconds if ttl_seconds and 0 <= ttl_seconds  else 3600

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

@router.get("/buckets/{bucket}/records/{record_id}", response_model=FileRecord, tags=["Records"])
def get_record(bucket: str, record_id: str, request: Request, api_key: str = Security(get_api_key)):
    """
    Retrieve detailed metadata and info for a single record by its ID in a bucket.

    - Returns 404 if the record is not found.
    """
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

@router.delete("/buckets/{bucket}/records/{record_id}", response_model=StatusResponse, tags=["Records"])
def delete_record(bucket: str, record_id: str, api_key: str = Security(get_api_key)):
    """
    Delete a record by ID from the specified bucket along with its file from storage.

    - Returns 404 if the record does not exist.
    """
    record = get_file_metadata_by_id(record_id, bucket)
    if not record:
        raise HTTPException(404, detail="Record not found")

    remove_file_metadata(record_id, bucket)
    file_path = os.path.join(settings.STORAGE_DIR, bucket, record['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    return {"status": "success", "message": f"File '{record['filename']}' deleted."}

@router.get("/buckets/{bucket}/records", response_model=List[FileRecordSummary], tags=["Records"])
def list_or_search_records(
    bucket: str,
    request: Request,
    key: Optional[str] = FastAPIQuery(None, description="Metadata key to filter by"),
    value: Optional[str] = FastAPIQuery(None, description="Metadata value to filter by"),
    value_type: str = FastAPIQuery("string", regex="^(string|boolean|number|datetime)$", description="Type of metadata value"),
    limit: int = FastAPIQuery(50, ge=1, le=1000, description="Maximum number of records to return"),
    api_key: str = Security(get_api_key)
):
    """
    List or search records in a bucket, optionally filtered by metadata key/value.

    - **bucket**: Name of the bucket to search.
    - **key**: Metadata key to filter on.
    - **value**: Metadata value to match.
    - **value_type**: Type of the metadata value (string, boolean, number, datetime).
    - **limit**: Max number of records to return (default 50, max 1000).
    - Returns a list of file record summaries with ID and URL.
    """
    records = search_metadata(bucket, key, value, value_type, limit)
    return [
        FileRecordSummary(
            id=record["id"],
            file_url=f"{request.base_url}files/{bucket}/{record['filename']}"
        ) for record in records
    ]

# -------------------------------
# Metadata Routes
# -------------------------------

@router.put("/buckets/{bucket}/records/{record_id}/metadata", response_model=StatusResponse, tags=["Metadata"])
def update_metadata(bucket: str, record_id: str, metadata: Dict[str, Any], api_key: str = Security(get_api_key)):
    """
    Replace the entire metadata object for a given record.

    - Returns 404 if the file does not exist.
    """
    if not update_metadata_helper(record_id, bucket, metadata):
        raise HTTPException(404, detail="File not found")
    return {"status": "success", "message": "Metadata updated."}

@router.patch("/buckets/{bucket}/records/{record_id}/metadata", tags=["Metadata"])
async def update_metadata_field(
    bucket: str,
    record_id: str,
    update: MetadataFieldUpdate = ...,
    api_key: str = Security(get_api_key),
):
    """
    Update a single field in the metadata of a specific record.

    - **key**: Metadata field name to update.
    - **value**: New value for the field.
    - Returns 404 if the file is not found.
    - Returns 403 if API key is invalid.
    """
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

    record = get_file_metadata_by_id(record_id, bucket)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")

    metadata = record.get("metadata", {})
    metadata[update.key] = update.value

    updated = update_metadata_helper(record_id, bucket, metadata)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update metadata")

    return {"message": "Metadata field updated", "metadata": metadata}

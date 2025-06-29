from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException, Request,
    Security, Query as FastAPIQuery, status
)
from typing import Optional, Dict, Any
import uuid
import json
import os
import shutil
from datetime import datetime

from security import get_api_key
from storage import (
    save_uploadfile,
    insert_file_metadata,
    get_file_metadata_by_id,
    remove_file_metadata,
    update_metadata,
    settings,
    create_bucket,
    db  # TinyDB instance
)

router = APIRouter(prefix="/api/v1", tags=["filenest"])


def get_table_for_bucket(bucket: str):
    # Return TinyDB table object for the bucket (create if not exist)
    return db.table(bucket)


@router.post("/buckets/{bucket}")
def create_named_bucket(
    bucket: str,
    api_key: str = Security(get_api_key)
):
    # Check if bucket already exists
    if bucket in db.tables():
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Bucket '{bucket}' already exists.")

    # Create TinyDB table (creates on demand)
    db.table(bucket)

    # Create bucket directory
    bucket_path = os.path.join(settings.STORAGE_DIR, bucket)
    os.makedirs(bucket_path, exist_ok=True)

    return {"status": "success", "message": f"Bucket '{bucket}' created."}


@router.delete("/buckets/{bucket}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bucket(
    bucket: str,
    api_key: str = Security(get_api_key)
):
    if bucket not in db.tables():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Bucket '{bucket}' not found.")

    # Remove all files in bucket folder
    bucket_path = os.path.join(settings.STORAGE_DIR, bucket)
    if os.path.exists(bucket_path):
        shutil.rmtree(bucket_path)

    # Remove TinyDB table for bucket
    db.drop_table(bucket)

    return None  # 204 No Content


@router.post("/buckets/{bucket}/records/")
async def upload_file(
    bucket: str,
    request: Request,
    file: UploadFile = File(...),
    ttl_seconds: Optional[int] = Form(None),
    metadata_json: Optional[str] = Form(None),
    api_key: str = Security(get_api_key)
):
    create_bucket(bucket, True)  # Create folder if missing
    
    ttl = ttl_seconds if ttl_seconds and 0 < ttl_seconds <= settings.MAX_FILE_SIZE else 3600

    file_id = str(uuid.uuid4())
    filename = file.filename
    file_path = os.path.join(settings.STORAGE_DIR, bucket, filename)

    try:
        await save_uploadfile(file, file_path)
    except Exception as e:
        raise HTTPException(413, detail=str(e))

    metadata = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception:
            raise HTTPException(400, "Invalid JSON metadata")

    insert_file_metadata(file_id, filename, bucket, ttl, metadata)

    return {"id": file_id, "file_url": f"{request.base_url}files/{bucket}/{filename}"}



@router.get("/buckets/{bucket}/records/{record_id}")
def get_metadata(
    bucket: str,
    record_id: str,
    request: Request,
    api_key: str = Security(get_api_key)
):
    table = get_table_for_bucket(bucket)
    record = get_file_metadata_by_id(record_id, bucket)
    if not record:
        raise HTTPException(404, "Record not found")
    return {
        "id": record["id"],
        "file_url": f"{request.base_url}files/{bucket}/{record['filename']}",
        "metadata": record.get("metadata"),
        "ttl_seconds": record.get("ttl_seconds"),
        "upload_time": record.get("upload_time"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at")
    }


@router.delete("/buckets/{bucket}/records/{record_id}")
def delete_file(
    bucket: str,
    record_id: str,
    api_key: str = Security(get_api_key)
):
    table = get_table_for_bucket(bucket)
    record = get_file_metadata_by_id(record_id, bucket)
    if not record:
        raise HTTPException(404, "File not found")

    file_path = os.path.join(settings.STORAGE_DIR, bucket, record['filename'])
    if os.path.exists(file_path):
        os.remove(file_path)

    remove_file_metadata(record_id, bucket)
    return {"status": "success", "message": f"File '{record['filename']}' deleted."}


@router.put("/buckets/{bucket}/records/{record_id}/metadata")
def update_file_metadata(
    bucket: str,
    record_id: str,
    metadata: Dict[str, Any],
    api_key: str = Security(get_api_key)
):
    updated = update_metadata(record_id, bucket, metadata)
    if not updated:
        raise HTTPException(404, "File not found")
    return {"status": "success", "message": "Metadata updated."}


@router.get("/buckets/{bucket}/records")
def search_metadata(
    bucket: str,
    request: Request,
    key: Optional[str] = FastAPIQuery(None, description="Metadata key to search for"),
    value: Optional[str] = FastAPIQuery(None, description="Value to match"),
    value_type: str = FastAPIQuery("string", regex="^(string|boolean|number|datetime)$"),
    limit: int = FastAPIQuery(50, ge=1, le=1000),
    api_key: str = Security(get_api_key)
):
    table = get_table_for_bucket(bucket)

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
            return v

    results = []
    for record in table.all():
        if key and value is not None:
            meta = record.get("metadata", {})
            val = meta.get(key)
            if val is None:
                continue

            try:
                val_casted = cast_value(str(val), value_type)
                value_casted = cast_value(value, value_type)
            except Exception:
                continue

            if val_casted != value_casted:
                continue

        results.append({
            "id": record["id"],
            "file_url": f"{request.base_url}files/{bucket}/{record['filename']}",
            "metadata": record.get("metadata"),
            "ttl_seconds": record.get("ttl_seconds"),
            "upload_time": record.get("upload_time"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        })

        if len(results) >= limit:
            break

    return results


@router.get("/buckets")
def list_buckets(api_key: str = Security(get_api_key)):
    # List all bucket names (tables in TinyDB)
    buckets = [b for b in db.tables() if b != "_default"]
    return {"buckets": buckets}

import os
import shutil
import aiofiles
from datetime import datetime
from tinydb import TinyDB, Query
from settings import settings
import asyncio

# Ensure storage and DB directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)

# Initialize TinyDB
db = TinyDB(settings.DB_PATH)

# -----------------------------
# Path Utilities
# -----------------------------

def get_bucket_path(bucket_name: str) -> str:
    return os.path.join(settings.STORAGE_DIR, bucket_name)

def get_object_path(bucket_name: str, object_key: str) -> str:
    return os.path.join(get_bucket_path(bucket_name), object_key)

# -----------------------------
# Bucket Utilities
# -----------------------------

def get_bucket_table(bucket_name: str):
    return db.table(bucket_name)

def create_bucket(bucket_name: str, exist_ok: bool = False):
    if bucket_name in db.tables():
        if exist_ok:
            return
        raise ValueError(f"Bucket '{bucket_name}' already exists.")

    db.table(bucket_name)  # Ensures table is created
    os.makedirs(get_bucket_path(bucket_name), exist_ok=True)

def delete_bucket(bucket_name: str):
    if bucket_name not in db.tables():
        raise ValueError(f"Bucket '{bucket_name}' does not exist.")

    bucket_path = get_bucket_path(bucket_name)
    if os.path.exists(bucket_path):
        shutil.rmtree(bucket_path)
    db.drop_table(bucket_name)

def list_buckets() -> list[str]:
    return [name for name in db.tables() if name != '_default']

# -----------------------------
# File Utilities
# -----------------------------

async def save_file_bytes(file_path: str, file_bytes: bytes):
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise ValueError("File too large")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    async with aiofiles.open(file_path, "wb") as out:
        await out.write(file_bytes)

    os.chmod(file_path, 0o644)  # Set rwxr-xr-x


async def save_uploadfile(file, file_path: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    size = 0
    await file.seek(0)
    async with aiofiles.open(file_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                raise ValueError("File too large")
            await out.write(chunk)

    os.chmod(file_path, 0o644)  # Set rwxr-xr-x


# -----------------------------
# Metadata Operations
# -----------------------------

def insert_file_metadata(file_id: str, filename: str, bucket: str, ttl_seconds: int, metadata: dict | None):
    table = get_bucket_table(bucket)
    now = datetime.utcnow().isoformat()
    table.insert({
        "id": file_id,
        "filename": filename,
        "upload_time": now,
        "ttl_seconds": ttl_seconds,
        "metadata": metadata or {},
        "created_at": now,
        "updated_at": now
    })

def get_file_metadata_by_id(file_id: str, bucket: str):
    table = get_bucket_table(bucket)
    return table.get(Query().id == file_id)

def get_file_metadata_by_bucket_key(bucket: str, key: str):
    table = get_bucket_table(bucket)
    return table.get(Query().filename == key)

def remove_file_metadata(file_id: str, bucket: str):
    table = get_bucket_table(bucket)
    table.remove(Query().id == file_id)

def update_metadata(file_id: str, bucket: str, metadata: dict):
    table = get_bucket_table(bucket)
    now = datetime.utcnow().isoformat()
    return table.update({"metadata": metadata, "updated_at": now}, Query().id == file_id)

from datetime import datetime, timedelta

def is_expired(record: dict) -> bool:
    """Check if record is expired based on upload_time + ttl_seconds."""
    upload_time = record.get("upload_time")
    ttl_seconds = record.get("ttl_seconds")
    if not upload_time or not ttl_seconds:
        return False
    try:
        upload_dt = datetime.fromisoformat(upload_time)
    except Exception:
        return False
    expiry_dt = upload_dt + timedelta(seconds=ttl_seconds)
    return datetime.utcnow() > expiry_dt

def search_metadata(bucket: str, key: str | None = None, value: str | None = None, value_type: str = "string", limit: int = 50):
    table = get_bucket_table(bucket)
    results = []

    def cast_value(v, vtype):
        try:
            if vtype == "string":
                return str(v)
            elif vtype == "boolean":
                return str(v).lower() == "true"
            elif vtype == "number":
                return float(v) if '.' in str(v) else int(v)
            elif vtype == "datetime":
                return datetime.fromisoformat(str(v))
        except Exception:
            return v

    for record in table.all():
        if is_expired(record):
            continue

        if key and value is not None:
            meta = record.get("metadata", {})
            val = meta.get(key)
            if val is None:
                continue
            try:
                val_casted = cast_value(val, value_type)
                value_casted = cast_value(value, value_type)
            except Exception:
                continue
            if val_casted != value_casted:
                continue

        results.append(record)
        if len(results) >= limit:
            break
    return results



async def cleanup_all_buckets():
    print("[CLEANUP] Starting cleanup for all buckets...")
    buckets = list_buckets()
    
    for bucket in buckets:
        print(f"[CLEANUP] Checking bucket: {bucket}")
        table = get_bucket_table(bucket)
        expired_records = [r for r in table.all() if is_expired(r)]

        for record in expired_records:
            file_path = get_object_path(bucket, record.get("filename"))
            file_id = record.get("id")
            filename = record.get("filename")

            if file_path and os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    print(f"[CLEANUP] Deleted file: {file_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete {file_path}: {e}")
            else:
                print(f"[SKIP] File not found: {file_path}")

            # Remove from metadata
            if file_id:
                table.remove(Query().id == file_id)
                print(f"[CLEANUP] Removed metadata for ID: {file_id}")

    print("[CLEANUP] Completed cleanup.")




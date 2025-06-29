import os
import shutil
import aiofiles
from datetime import datetime
from tinydb import TinyDB, Query
from settings import settings

# Ensure root storage and DB directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)

db = TinyDB(settings.DB_PATH)

def get_bucket_path(bucket_name: str) -> str:
    """Return filesystem path for a given bucket."""
    return os.path.join(settings.STORAGE_DIR, bucket_name)

def get_object_path(bucket_name: str, object_key: str) -> str:
    """Return full filesystem path for an object inside a bucket."""
    return os.path.join(get_bucket_path(bucket_name), object_key)

def get_bucket_table(bucket_name: str):
    """Return TinyDB table instance for the bucket."""
    # Using bucket name as table name isolates metadata per bucket
    return db.table(bucket_name)

async def save_file_bytes(file_path: str, file_bytes: bytes):
    """Save bytes to file asynchronously, enforcing max file size."""
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise ValueError("File too large")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(file_bytes)

async def save_uploadfile(file, file_path: str):
    """Save an UploadFile asynchronously in chunks, enforcing max size."""
    size = 0
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await file.seek(0)
    async with aiofiles.open(file_path, "wb") as out_file:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                raise ValueError("File too large")
            await out_file.write(chunk)

def insert_file_metadata(file_id: str, filename: str, bucket: str, ttl_seconds: int, metadata: dict | None):
    """Insert file metadata into the TinyDB table corresponding to bucket."""
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
    """Get file metadata by ID scoped to bucket."""
    table = get_bucket_table(bucket)
    File = Query()
    return table.get(File.id == file_id)

def get_file_metadata_by_bucket_key(bucket: str, key: str):
    """Get file metadata by bucket and filename key."""
    table = get_bucket_table(bucket)
    File = Query()
    return table.get(File.filename == key)

def remove_file_metadata(file_id: str, bucket: str):
    """Remove file metadata by ID scoped to bucket."""
    table = get_bucket_table(bucket)
    File = Query()
    table.remove(File.id == file_id)

def update_metadata(file_id: str, bucket: str, metadata: dict):
    """Update metadata for file by ID scoped to bucket."""
    table = get_bucket_table(bucket)
    File = Query()
    now = datetime.utcnow().isoformat()
    updated = table.update({"metadata": metadata, "updated_at": now}, File.id == file_id)
    return updated

def search_metadata(bucket: str, key: str | None = None, value: str | None = None, value_type: str = "string", limit: int = 50):
    """Search metadata in a bucket table filtering by key and value with casting."""
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
            return v  # fallback no cast

    for record in table.all():
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

def list_buckets() -> list[str]:
    """Return a list of bucket names (all table names except default)."""
    tables = db.tables()
    return [t for t in tables if t != '_default']

def create_bucket(bucket_name: str, exist_ok: bool=False):
    """Create a new bucket directory and TinyDB table."""
    if bucket_name in db.tables():
        if exist_ok:
            return
        else:
            raise ValueError(f"Bucket '{bucket_name}' already exists.")
        
    # Create TinyDB table (creates on demand)
    db.table(bucket_name)
    # Create bucket folder on filesystem
    os.makedirs(get_bucket_path(bucket_name), exist_ok=True)


def delete_bucket(bucket_name: str):
    """Delete bucket directory and drop TinyDB table."""
    if bucket_name not in db.tables():
        raise ValueError(f"Bucket '{bucket_name}' does not exist.")
    # Remove bucket folder and all contents
    bucket_path = get_bucket_path(bucket_name)
    if os.path.exists(bucket_path):
        shutil.rmtree(bucket_path)
    # Drop TinyDB table
    db.drop_table(bucket_name)

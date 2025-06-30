import os
import shutil
import aiofiles
import sqlite3
from datetime import datetime, timedelta
from settings import settings
import asyncio
import json
from contextlib import contextmanager

# ---------------------------------
# DB Initialization & Connection
# ---------------------------------

os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)

def initialize_database():
    with sqlite3.connect(settings.DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")

        conn.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                bucket TEXT,
                filename TEXT,
                upload_time TEXT,
                ttl_seconds INTEGER,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_id ON files (id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_bucket ON files (bucket)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_bucket_id ON files (bucket, id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ttl ON files (ttl_seconds)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ttl_upload_time ON files (ttl_seconds, upload_time);')
        conn.commit()

@contextmanager
def get_db():
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

initialize_database()

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

def create_bucket(bucket_name: str, exist_ok: bool = False):
    os.makedirs(get_bucket_path(bucket_name), exist_ok=exist_ok)

def delete_bucket(bucket_name: str):
    bucket_path = get_bucket_path(bucket_name)
    if os.path.exists(bucket_path):
        shutil.rmtree(bucket_path)
    with get_db() as conn:
        conn.execute("DELETE FROM files WHERE bucket = ?", (bucket_name,))

def list_buckets() -> list[str]:
    with get_db() as conn:
        cursor = conn.execute("SELECT DISTINCT bucket FROM files")
        return [row[0] for row in cursor.fetchall()]

# -----------------------------
# File Utilities
# -----------------------------

async def save_file_bytes(file_path: str, file_bytes: bytes):
    if len(file_bytes) > settings.MAX_FILE_SIZE:
        raise ValueError("File too large")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    async with aiofiles.open(file_path, "wb") as out:
        await out.write(file_bytes)
    os.chmod(file_path, 0o644)

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
    os.chmod(file_path, 0o644)

# -----------------------------
# Metadata Operations
# -----------------------------

def insert_file_metadata(file_id, filename, bucket, ttl_seconds, metadata):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute('''
            INSERT INTO files (id, bucket, filename, upload_time, ttl_seconds, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (file_id, bucket, filename, now, ttl_seconds, json.dumps(metadata or {}), now, now))

def get_file_metadata_by_id(file_id, bucket):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ? AND bucket = ?", (file_id, bucket)).fetchone()
        return _row_to_dict(row) if row else None

def remove_file_metadata(file_id, bucket):
    with get_db() as conn:
        conn.execute("DELETE FROM files WHERE id = ? AND bucket = ?", (file_id, bucket))

def update_metadata(file_id, bucket, metadata):
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        cur = conn.execute('''
            UPDATE files SET metadata = ?, updated_at = ? WHERE id = ? AND bucket = ?
        ''', (json.dumps(metadata), now, file_id, bucket))
        return cur.rowcount > 0

def _row_to_dict(row):
    return {
        "id": row[0],
        "bucket": row[1],
        "filename": row[2],
        "upload_time": row[3],
        "ttl_seconds": row[4],
        "metadata": json.loads(row[5]) if row[5] else {},
        "created_at": row[6],
        "updated_at": row[7],
    }

def is_expired(record):
    try:
        ttl = record.get("ttl_seconds")
        if ttl == 0 or not ttl:
            return False
        upload_dt = datetime.fromisoformat(record.get("upload_time"))
        return datetime.utcnow() > (upload_dt + timedelta(seconds=ttl))
    except:
        return False

def search_metadata(bucket, key=None, value=None, value_type="string", limit=50):
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM files WHERE bucket = ?", (bucket,))
        results = []

        def cast(v, t):
            try:
                if t == "string": return str(v)
                if t == "boolean": return str(v).lower() == "true"
                if t == "number": return float(v) if '.' in str(v) else int(v)
                if t == "datetime": return datetime.fromisoformat(str(v))
            except: return v

        for row in cursor.fetchall():
            record = _row_to_dict(row)
            if is_expired(record): continue
            if key and value is not None:
                meta = record.get("metadata", {})
                if meta.get(key) is None: continue
                if cast(meta[key], value_type) != cast(value, value_type): continue
            results.append(record)
            if len(results) >= limit:
                break
        return results

# -----------------------------
# Cleanup
# -----------------------------

async def cleanup_all_buckets():
    print("[CLEANUP] Starting cleanup for expired files...")

    now_iso = datetime.utcnow().isoformat()

    # SQL to find expired records where ttl is not 0 and expiration < now
    cursor.execute('''
        SELECT id, bucket, filename FROM files
        WHERE ttl_seconds > 0
        AND DATETIME(upload_time, '+' || ttl_seconds || ' seconds') <= ?
    ''', (now_iso,))

    expired_records = cursor.fetchall()

    for file_id, bucket, filename in expired_records:
        file_path = get_object_path(bucket, filename)

        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
                print(f"[CLEANUP] Deleted file: {file_path}")
            except Exception as e:
                print(f"[ERROR] Failed to delete {file_path}: {e}")
        else:
            print(f"[SKIP] File not found: {file_path}")

        # Delete metadata
        try:
            with conn:
                conn.execute("DELETE FROM files WHERE id = ? AND bucket = ?", (file_id, bucket))
            print(f"[CLEANUP] Removed metadata for ID: {file_id}")
        except Exception as e:
            print(f"[ERROR] Failed to remove metadata for ID {file_id}: {e}")

    print("[CLEANUP] Cleanup completed.")


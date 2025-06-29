import os
import pytest
import asyncio
from datetime import datetime, timedelta
from tinydb import TinyDB
from unittest.mock import AsyncMock

# Import your module here; adjust according to your project structure
from backend.storage_helpers import (
    get_bucket_path, get_object_path,
    save_file_bytes, save_uploadfile,
    insert_file_metadata, get_file_metadata_by_id,
    get_file_metadata_by_bucket_key,
    remove_file_metadata, update_metadata,
    FileTable
)
from backend.settings import settings

@pytest.fixture(autouse=True)
def isolate_db_and_storage(tmp_path, monkeypatch):
    # Redirect STORAGE_ROOT and DB_PATH to tmp directory for testing
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "db.json"))

    # Re-create dirs and TinyDB instance for tests isolation
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)

    # Reinitialize TinyDB with tmp DB_PATH
    global FileTable
    db = TinyDB(settings.DB_PATH)
    FileTable = db.table("files")

    yield
    # cleanup after test if needed


@pytest.mark.asyncio
async def test_save_file_bytes_and_uploadfile(tmp_path):
    # Prepare bytes data
    data = b"Hello, World!"
    file_path = tmp_path / "dummyfile.txt"

    # Test save_file_bytes
    await save_file_bytes(str(file_path), data)
    assert file_path.exists()
    assert file_path.read_bytes() == data

    # Mock an UploadFile-like async object with read method
    class DummyUploadFile:
        def __init__(self, content):
            self._content = content
            self._pos = 0
        async def seek(self, pos):
            self._pos = pos
        async def read(self, n=-1):
            if self._pos >= len(self._content):
                return b""
            if n < 0:
                chunk = self._content[self._pos :]
                self._pos = len(self._content)
                return chunk
            chunk = self._content[self._pos : self._pos + n]
            self._pos += n
            return chunk

    dummy_file = DummyUploadFile(data)
    upload_path = tmp_path / "uploadfile.txt"
    await save_uploadfile(dummy_file, str(upload_path))
    assert upload_path.exists()
    assert upload_path.read_bytes() == data


def test_get_paths():
    bucket = "mybucket"
    key = "myfile.txt"
    bucket_path = get_bucket_path(bucket)
    assert bucket in bucket_path

    object_path = get_object_path(bucket, key)
    assert bucket in object_path
    assert key in object_path


def test_insert_get_remove_update_metadata():
    file_id = "testid"
    filename = "file.txt"
    bucket = "bucket1"
    ttl_seconds = 3600
    metadata = {"foo": "bar"}

    insert_file_metadata(file_id, filename, bucket, ttl_seconds, metadata)
    meta = get_file_metadata_by_id(file_id)
    assert meta is not None
    assert meta["id"] == file_id
    assert meta["bucket"] == bucket
    assert meta["filename"] == filename
    assert meta["metadata"] == metadata

    # Test get by bucket/key
    meta2 = get_file_metadata_by_bucket_key(bucket, filename)
    assert meta2 == meta

    # Update metadata
    new_metadata = {"foo": "baz"}
    update_count = update_metadata(file_id, new_metadata)
    assert update_count == 1

    updated_meta = get_file_metadata_by_id(file_id)
    assert updated_meta["metadata"] == new_metadata

    # Remove metadata
    remove_file_metadata(file_id)
    deleted_meta = get_file_metadata_by_id(file_id)
    assert deleted_meta is None

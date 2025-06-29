#!/usr/bin/env python3
import os
import sys
import time
import base64
import secrets
import random
import json
import requests
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

API_KEY = "supersecretapikey"
BASE_URL = "http://0.0.0.0:8000/api/v1/buckets"

NUM_BUCKETS = 5
FILES_PER_BUCKET = 10

HEADERS = {"x-api-key": API_KEY}

def log(msg):
    print(f"\033[1;33m[INFO]\033[0m {msg}")

def ok(msg):
    print(f"\033[0;32m[OK]\033[0m {msg}")

def fail(msg):
    print(f"\033[0;31m[ERROR]\033[0m {msg}")
    sys.exit(1)

def create_bucket(bucket_name):
    url = f"{BASE_URL}/{bucket_name}"
    resp = requests.post(url, headers=HEADERS)
    if resp.status_code == 409 or resp.status_code == 400:
        log(f"Bucket '{bucket_name}' already exists or handled: {resp.text}")
    elif resp.ok:
        ok(f"Bucket created: {bucket_name}")
    else:
        fail(f"Failed to create bucket '{bucket_name}': {resp.status_code} {resp.text}")

def generate_text_file_content(size_kb=2):
    raw = secrets.token_bytes(size_kb * 1024)
    b64data = base64.b64encode(raw)
    return b64data[: size_kb * 1024]

def generate_dummy_image_bytes():
    if Image is None:
        return None
    img = Image.new("RGB", (100, 100), color="skyblue")
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio.read()

def upload_files(bucket_name, filename, file_bytes, metadata):
    url = f"{BASE_URL}/{bucket_name}/records/"

    # Prepare metadata JSON file content
    metadata_filename = f"{filename}.metadata.json"
    metadata_json_bytes = json.dumps(metadata, indent=2).encode('utf-8')

    files = {
        "file": (filename, file_bytes),
        "metadata_file": (metadata_filename, metadata_json_bytes, "application/json"),
    }

    data = {
        "ttl_seconds": 3600,
        # Still sending metadata_json field for API, if it uses it (optional here)
        "metadata_json": json.dumps(metadata),
    }

    resp = requests.post(url, headers=HEADERS, files=files, data=data)
    if resp.ok:
        return resp.json()
    else:
        fail(f"Upload failed for {filename}: {resp.status_code} {resp.text}")

def main():
    log("=== Starting dummy data generation with image + metadata files ===")

    for b in range(1, NUM_BUCKETS + 1):
        bucket_name = f"dummybucket{b}"
        log(f"Creating bucket: {bucket_name}")
        create_bucket(bucket_name)

        for f in range(1, FILES_PER_BUCKET + 1):
            is_image = random.random() < 0.3

            if is_image and Image is not None:
                filename = f"image_{f}.png"
                file_bytes = generate_dummy_image_bytes()
                if file_bytes is None:
                    log("PIL not available or failed to generate image, falling back to text file.")
                    filename = f"file_{f}.txt"
                    file_bytes = generate_text_file_content()
            else:
                filename = f"file_{f}.txt"
                file_bytes = generate_text_file_content()

            metadata = {
                "description": f"Dummy file {filename} in bucket {bucket_name}",
                "index": f,
            }

            log(f"Uploading file '{filename}' with metadata file '{filename}.metadata.json'")
            resp_json = upload_files(bucket_name, filename, file_bytes, metadata)

            file_id = resp_json.get("id")
            file_url = resp_json.get("file_url")

            if not file_id or not file_url:
                fail(f"Upload response missing id or file_url: {resp_json}")

            ok(f"Uploaded file {filename} (ID: {file_id})")

            time.sleep(0.1)

    ok("✅ Dummy data generation completed successfully.")

if __name__ == "__main__":
    main()

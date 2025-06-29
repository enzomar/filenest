#!/bin/bash
set -e

API_KEY="supersecretapikey"
BASE_URL="http://localhost:8000"
FILE="dummyfile.txt"
BUCKET="test-bucket"
OBJECT_KEY="dummyfile.txt"

echo "=== Testing FileNest S3-Compatible API ==="

# Create bucket
echo "Creating bucket..."
CREATE_BUCKET_RESP=$(http PUT "$BASE_URL/$BUCKET/" "x-api-key:$API_KEY")
if [[ "$CREATE_BUCKET_RESP" != *"success"* ]]; then
  echo "Bucket creation failed:"
  echo "$CREATE_BUCKET_RESP"
  exit 1
fi
echo "Bucket created successfully."

# Upload object
echo "Uploading object..."
UPLOAD_RESP=$(http PUT "$BASE_URL/$BUCKET/$OBJECT_KEY" "x-api-key:$API_KEY" < "$FILE")
if [[ "$UPLOAD_RESP" != *"success"* ]]; then
  echo "Object upload failed:"
  echo "$UPLOAD_RESP"
  exit 1
fi
echo "Object uploaded successfully."

# Get object
echo "Downloading object..."
http GET "$BASE_URL/$BUCKET/$OBJECT_KEY" "x-api-key:$API_KEY" --download --output downloaded_dummyfile.txt

# Verify downloaded file matches original file
if ! cmp -s "$FILE" downloaded_dummyfile.txt; then
  echo "Downloaded file does not match original!"
  exit 1
fi
echo "Downloaded file matches original."

# Get bucket list
echo "Listing objects in bucket..."
LIST_RESP=$(http GET "$BASE_URL/$BUCKET/" "x-api-key:$API_KEY")
# Basic check: ensure object key is listed
if ! echo "$LIST_RESP" | grep -q "$OBJECT_KEY"; then
  echo "Object key not found in bucket list:"
  echo "$LIST_RESP"
  exit 1
fi
echo "Object key found in bucket list."

# Delete object
echo "Deleting object..."
DELETE_OBJ_RESP=$(http DELETE "$BASE_URL/$BUCKET/$OBJECT_KEY" "x-api-key:$API_KEY")
if [[ "$DELETE_OBJ_RESP" != *"success"* ]]; then
  echo "Object deletion failed:"
  echo "$DELETE_OBJ_RESP"
  exit 1
fi
echo "Object deleted successfully."

# Delete bucket
echo "Deleting bucket..."
DELETE_BUCKET_RESP=$(http DELETE "$BASE_URL/$BUCKET/" "x-api-key:$API_KEY")
if [[ "$DELETE_BUCKET_RESP" != *"success"* ]]; then
  echo "Bucket deletion failed:"
  echo "$DELETE_BUCKET_RESP"
  exit 1
fi
echo "Bucket deleted successfully."

echo "S3-Compatible API tests completed."

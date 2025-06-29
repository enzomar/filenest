#!/usr/bin/env bash
set -euo pipefail

# Config
API_KEY="supersecretapikey"
BASE_URL="http://0.0.0.0:8000/api/v1/buckets"
FILE="./dummyfile.txt"
BUCKET="testbucket"

# Colors
RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' NC='\033[0m'

log()  { echo -e "${YELLOW}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

http_call() {
  local METHOD=$1
  shift
  http "$METHOD" "$@" "x-api-key:$API_KEY"
}

check_response_field() {
  local response="$1"
  local field="$2"
  jq -e "$field" <<<"$response" > /dev/null 2>&1
}

log "=== Testing FileNest API with bucket: $BUCKET ==="

# Create Bucket
log "Creating bucket '$BUCKET'..."
CREATE_RESP=$(http_call POST "$BASE_URL/$BUCKET" || true)
if check_response_field "$CREATE_RESP" '.detail' ; then
  echo "$CREATE_RESP"
  ok "Bucket already exists or error handled gracefully."
else
  ok "Bucket created."
fi

# Upload File
log "Uploading file..."
UPLOAD_RESP=$(http --form POST "$BASE_URL/$BUCKET/records/" \
  "x-api-key:$API_KEY" \
  file@"$FILE" \
  ttl_seconds:=3600 \
  metadata_json='{"testkey":"testvalue"}')

FILE_ID=$(jq -r '.id // empty' <<<"$UPLOAD_RESP")
FILE_URL=$(jq -r '.file_url // empty' <<<"$UPLOAD_RESP")

[[ -z "$FILE_ID" || -z "$FILE_URL" ]] && fail "Upload failed:\n$UPLOAD_RESP"
ok "File uploaded: ID=$FILE_ID, URL=$FILE_URL"

# Get Metadata
log "Fetching metadata..."
META=$(http_call GET "$BASE_URL/$BUCKET/records/$FILE_ID")
[[ $(jq -r '.metadata.testkey' <<<"$META") == "testvalue" ]] || fail "Metadata mismatch:\n$META"
ok "Metadata testkey verified."

# Search
log "Searching for file by metadata..."
SEARCH=$(http_call GET "$BASE_URL/$BUCKET/records?key=testkey&value=testvalue&value_type=string&limit=5")
[[ $(jq 'length' <<<"$SEARCH") -gt 0 ]] || fail "No matching record found:\n$SEARCH"
ok "Search successful."

# Update Metadata
log "Updating metadata..."
UPDATE=$(http PUT "$BASE_URL/$BUCKET/records/$FILE_ID/metadata" \
  "x-api-key:$API_KEY" \
  testkey="updatedvalue" newkey="newvalue")
[[ $(jq -r '.status // empty' <<<"$UPDATE") == "success" ]] || fail "Update failed:\n$UPDATE"
ok "Metadata updated."

# Verify Update
log "Verifying metadata update..."
UPDATED=$(http_call GET "$BASE_URL/$BUCKET/records/$FILE_ID")
[[ $(jq -r '.metadata.testkey' <<<"$UPDATED") == "updatedvalue" ]] || fail "testkey not updated."
[[ $(jq -r '.metadata.newkey' <<<"$UPDATED") == "newvalue" ]] || fail "newkey not found."
ok "Metadata update verified."

# Delete File
log "Deleting file..."
DEL_FILE=$(http_call DELETE "$BASE_URL/$BUCKET/records/$FILE_ID")
[[ $(jq -r '.status // empty' <<<"$DEL_FILE") == "success" ]] || fail "File deletion failed:\n$DEL_FILE"
ok "File deleted."

# Delete Bucket
log "Deleting bucket '$BUCKET'..."
DEL_BUCKET=$(http_call DELETE "$BASE_URL/$BUCKET" || true)
if check_response_field "$DEL_BUCKET" '.detail' ; then
  echo "$DEL_BUCKET"
  ok "Bucket already deleted or error handled."
else
  ok "Bucket deleted."
fi

ok "✅ FileNest API test sequence completed successfully."

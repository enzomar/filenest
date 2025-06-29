#!/usr/bin/env bash
set -euo pipefail

API_KEY="supersecretapikey"
BASE_URL="http://0.0.0.0:8000/api/v1/buckets"

RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' NC='\033[0m'
log()  { echo -e "${YELLOW}[INFO]${NC} $1"; }
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
fail() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

http_call() {
  local METHOD=$1
  shift
  http "$METHOD" "$@" "x-api-key:$API_KEY"
}

log "Fetching list of all buckets..."

BUCKETS_JSON=$(http_call GET "$BASE_URL")
BUCKETS=$(jq -r '.buckets[]?' <<< "$BUCKETS_JSON")

if [[ -z "$BUCKETS" ]]; then
  ok "No buckets found to delete."
  exit 0
fi

for bucket in $BUCKETS; do
  log "Deleting bucket: $bucket"
  DEL_RESP=$(http_call DELETE "$BASE_URL/$bucket" || true)
  if echo "$DEL_RESP" | jq -e '.detail?' &> /dev/null; then
    echo "$DEL_RESP"
    log "Bucket $bucket was already deleted or deletion handled gracefully."
  else
    ok "Bucket $bucket deleted successfully."
  fi
done

ok "✅ All buckets deletion attempt finished."

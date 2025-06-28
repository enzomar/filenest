
curl -X POST http://127.0.0.1/upload/ \
  -H "x-api-key: supersecretapikey" \
  -F "file=@./file.txt" \
  -F "ttl_seconds=60"
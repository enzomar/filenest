
curl -X POST http://localhost/upload/ \
  -H "x-api-key: b14ef983-c085-48ce-a467-020fe5a3fd0e" \
  -F "file=@./file.txt" \
  -F "ttl_seconds=60"


  curl -X POST http://localhost/upload_base64/ \
  -H "x-api-key: b14ef983-c085-48ce-a467-020fe5a3fd0e" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "file.txt",
    "content_base64": "'"$(base64 -w 0 ./file.txt)"'",
    "ttl_seconds": 60
  }'
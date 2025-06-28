# FileNest - Secure TTL File Storage Service

A lightweight FastAPI-based file upload server with:

- API key authentication
- File size limit (default 10 MB)
- File TTL (automatic expiration and deletion)
- PostgreSQL or SQLite metadata storage
- File storage with static serving
- Background cleanup task
- Production-ready Docker Compose setup with Nginx reverse proxy
- Health check endpoint
- CORS middleware

---

## Features

- Upload files via `/upload/` with API key header
- Validate TTL (time to live) for automatic cleanup
- Files accessible via `/files/{filename}`
- Protect uploads with API key (default in `.env`)
- Size restriction with 413 error if exceeded
- Background cleanup every 60 seconds deletes expired files
- Logging for uploads and cleanup
- Static file serving optimized by Nginx

---

## Getting Started

### Prerequisites

- Docker & Docker Compose installed
- (Optional) Python 3.11+ if running without Docker
- `.env` file with `API_KEY` set


---

### Environment Variables

| Variable  | Description                   | Default               |
|-----------|-------------------------------|-----------------------|
| `API_KEY` | API key for authentication    | `supersecretapikey`   |

Set this in your environment or in the `docker-compose.yml` file.

---

### Running with Docker Compose

1. Clone the repo and navigate to the project root:
   ```bash
   git clone <repo-url>
   cd FileNest
   ```

2. Start the service:
   ```bash
   docker-compose up --build
   ```

3. The service runs on `http://localhost:8000`

---

### Uploading a File

Send a POST request to `/upload/` with:

- Header: `x-api-key: your_api_key`
- Form data:
  - `file`: file to upload
  - `ttl_seconds`: optional, time in seconds before auto-deletion

Example with `curl`:

```bash
curl -X POST "http://localhost:8000/upload/" \
  -H "x-api-key: supersecretapikey" \
  -F "file=@/path/to/your/file.png" \
  -F "ttl_seconds=3600"
```

Response:

```json
{
  "file_url": "/files/{generated-filename}.png"
}
```

---

### Accessing Files

Files are accessible publicly at:

```
http://localhost:8000/files/{filename}
```

---

### File Cleanup

- Files uploaded with TTL are automatically deleted after expiration.
- Cleanup runs every 60 seconds in the background.

---

## Project Structure

```
FileNest/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── storage/
├── file_metadata.db
├── docker-compose.yml
└── README.md
```

---

## Customization

Adjust settings in .env or modify backend/main.py (using Pydantic BaseSettings):

- API_KEY: API key for authentication
- MAX_FILE_SIZE: max upload size in bytes (default 10 MB)
- STORAGE_DIR: folder where files are stored
- DATABASE_URL: DB connection string (SQLite or Postgres)
- CLEANUP_INTERVAL_SEC: interval in seconds for cleanup task
- MAX_TTL_SECONDS: max allowed TTL in seconds

---

## Deployment Notes

- Run behind HTTPS proxy (Nginx, Traefik, etc.)
- For production, serve static files directly from Nginx
- Monitor logs and health endpoint
- Consider moving to Postgres for higher loads


---

## Troubleshooting


- 413 Payload Too Large: File size exceeds max limit (MAX_FILE_SIZE)
- 403 Forbidden: Invalid or missing API key
- File not found: May be expired or not uploaded correctly

---

## License

MIT License © Vincenzo Marafioti

---

Feel free to contribute or open issues!

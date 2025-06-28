# FileNest - Secure TTL File Storage Service

A lightweight, production-ready FastAPI-based file upload service with:

- ✅ API key authentication
- ✅ File size limit (default 10 MB)
- ✅ Automatic file expiration via TTL (default: 1 hour)
- ✅ SQLite or PostgreSQL metadata storage
- ✅ Metadata and file association via UUID
- ✅ Static file serving
- ✅ Background cleanup task
- ✅ Health check endpoint
- ✅ CORS support
- ✅ Docker Compose setup (optional)

---

## Features

- **Upload files with metadata** via `/upload_with_metadata/`
- Files and metadata are stored securely
- Files are deleted automatically after TTL expiration
- Publicly accessible file URLs
- Background cleanup task runs every 60 seconds
- API key protects all upload and metadata endpoints
- Static files served via `/files/{filename}`
- Health check endpoint at `/health`

---

## Getting Started

### Prerequisites

- Docker & Docker Compose (recommended)
- Or Python 3.11+ and pip (for manual run)
- `.env` file with at least the `API_KEY`

---

### Environment Variables

| Variable              | Description                            | Default                 |
|-----------------------|----------------------------------------|-------------------------|
| `API_KEY`             | API key for authentication             | `supersecretapikey`     |
| `API_KEY_NAME`        | Name of the header for API key         | `x-api-key`             |
| `MAX_FILE_SIZE`       | Max file size in bytes                 | `10485760` (10 MB)      |
| `DEFAULT_TTL_SECONDS` | Default time-to-live for files         | `3600` (1 hour)         |
| `MAX_TTL_SECONDS`     | Max allowed TTL                        | `2592000` (30 days)     |
| `DATABASE_URL`        | SQLite/PostgreSQL connection string    | `sqlite:///./data/file_metadata.db` |
| `CLEANUP_INTERVAL_SEC`| File cleanup task interval (in sec)    | `60`                    |
| `STORAGE_DIR`         | Directory where files are saved        | `storage`               |
| `CORS_ORIGINS`        | Allowed frontend domains (CORS)        | `["https://yourfrontend.domain"]` |

---

## Run with Docker Compose

```bash
git clone <repo-url>
cd FileNest
docker-compose up --build
```

The service will be accessible at:

```
http://localhost:8000
```

---

## Uploading a File with Metadata

Send a POST request to `/upload_with_metadata/` with:

- Header: `x-api-key: your_api_key`
- Form Data:
  - `file`: File to upload
  - `metadata_json`: Metadata in JSON format
  - `ttl_seconds`: Optional TTL in seconds

### Example with `curl`

```bash
curl -X POST "http://localhost:8000/upload_with_metadata/" \
  -H "x-api-key: supersecretapikey" \
  -F "file=@/path/to/image.png" \
  -F 'metadata_json={"author":"Vincenzo","description":"Test upload"}' \
  -F "ttl_seconds=3600"
```

#### Example Response:

```json
{
  "id": "c123f9e1-xxx-xxxx-xxxx-xxxxxx",
  "file_url": "http://localhost:8000/files/image.png"
}
```

---

## Retrieving File Metadata

Get full metadata and URL by record ID:

```http
GET /metadata/{id}
Header: x-api-key: your_api_key
```

#### Example:

```bash
curl -H "x-api-key: supersecretapikey" http://localhost:8000/metadata/c123f9e1-xxxx
```

#### Response:

```json
{
  "id": "c123f9e1-xxxx",
  "file_url": "http://localhost:8000/files/image.png",
  "metadata": {
    "author": "Vincenzo",
    "description": "Test upload"
  },
  "ttl_seconds": 3600,
  "upload_time": "2025-06-28T14:01:22.548Z"
}
```

---

## File Access

Files are served from:

```
http://localhost:8000/files/{filename}
```

These links are public, but the metadata requires API key access.

---

## Cleanup

- Files and metadata are removed automatically after TTL.
- Cleanup runs every 60 seconds.

---

## Health Check

Check service status with:

```http
GET /health
```

Response:

```json
{"status": "ok"}
```

---

## Project Structure

```
FileNest/
├── storage/                  # Uploaded files
├── data/                     # SQLite DB directory
│   └── file_metadata.db
├── backend/
│   ├── main.py               # FastAPI application
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Customization

You can override settings in `.env`:

```ini
API_KEY=your_own_api_key
MAX_FILE_SIZE=5242880
DEFAULT_TTL_SECONDS=1800
DATABASE_URL=sqlite:///./data/file_metadata.db
```

Or modify `main.py` for advanced tweaks.

---

## Deployment Tips

- Serve behind HTTPS proxy (Nginx, Traefik)
- Let Nginx serve static files directly for performance
- Mount volumes to persist files and database
- Use Postgres in production for scaling

---

## Troubleshooting

| Error Code | Meaning                         | Possible Fix                      |
|------------|----------------------------------|-----------------------------------|
| `413`      | Payload Too Large               | File exceeds `MAX_FILE_SIZE`      |
| `403`      | Forbidden                        | Invalid or missing API key        |
| `409`      | Conflict                         | File with same name already exists|
| `404`      | Not Found                        | ID does not exist or file expired |

---

## License

MIT License © [Vincenzo Marafioti](mailto:enzo.mar@gmail.com)

---

Feel free to submit issues, PRs, or feature requests. Contributions welcome!

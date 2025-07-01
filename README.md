# 🚀 FileNest – Secure, Lightweight TTL File Storage & Metadata API

**FileNest** is a minimal, production-ready file storage and metadata API built with FastAPI. It supports **time-to-live (TTL)** file expiration, **secure uploads**, **searchable metadata**, and **public file access**—ideal for automation workflows, content pipelines, or temporary asset storage.

---

## 🧩 Key Features

- 🔐 **API Key Authentication**
- 📁 **File Upload with JSON Metadata**
- 🕒 **Auto-Expiration via TTL (default 1h)**
- 🔎 **Metadata Search & Filtering**
- 🧹 **TTL-based Cleanup System** (cron/external trigger)
- 🌐 **Public Static File Serving**
- 💡 **Health Check Endpoint**
- ⚙️ **Built with FastAPI + SQLite (or PostgreSQL)**

---

## 🛠️ Use Cases

- Temporary content storage for AI workflows  
- Media delivery in headless CMS setups  
- Automation and backend pipelines (e.g., with [n8n](https://n8n.io/))  
- Any case where metadata + file + TTL matters

---

## ⚙️ Quick Start (Docker)

```bash
git clone https://github.com/enzomar/filenest.git
cd filenest
docker-compose up --build
```

🔗 Default server:  
```
http://localhost:8000
```

---

## 🌍 REST API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/buckets/{bucket}/records/` | Upload a file with TTL & metadata |
| `GET /api/v1/buckets/{bucket}/records/{id}` | Retrieve metadata for a file |
| `GET /api/v1/buckets/{bucket}/records` | Search records by metadata |
| `PUT /metadata/` | Replace metadata |
| `PATCH /metadata/` | Update a specific metadata field |
| `DELETE /api/v1/buckets/{bucket}/records/{id}` | Delete file and metadata |
| `GET /files/{filename}` | Serve static file (public) |
| `GET /health` | Service health check |

---

## 📤 Upload Example (cURL)

```bash
curl -X POST http://localhost:8000/api/v1/buckets/demo/records   -H "x-api-key: supersecretapikey"   -F "file=@image.png"   -F 'metadata_json={"author":"Vincenzo","description":"Test upload"}'   -F "ttl_seconds=3600"
```

📦 Response:
```json
{
  "id": "c123f9e1-xxxx",
  "file_url": "http://localhost:8000/files/image.png"
}
```

---

## 🔍 Fetch Metadata by ID

```bash
curl -H "x-api-key: supersecretapikey"   http://localhost:8000/api/v1/buckets/demo/records/c123f9e1-xxxx
```

---

## 🌐 Static File Access

Uploaded files are accessible publicly via:

```
http://localhost:8000/files/{filename}
```

Metadata and TTL logic remain secure.

---

## 🔒 Environment Variables (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | Required auth key | `supersecretapikey` |
| `MAX_FILE_SIZE` | Max upload size (bytes) | `10485760` (10MB) |
| `DEFAULT_TTL_SECONDS` | Default file TTL | `3600` |
| `MAX_TTL_SECONDS` | Max allowed TTL | `2592000` (30d) |
| `DATABASE_URL` | DB connection (SQLite/Postgres) | `sqlite:///./data/file_metadata.db` |
| `CLEANUP_INTERVAL_SEC` | Cleanup run interval | `60` |
| `STORAGE_DIR` | Path for storing files | `storage` |
| `CORS_ORIGINS` | Allowed frontend domains | `["*"]` |

---

## 🧹 Cleanup Expired Files

Files and records are deleted after TTL. Trigger cleanup manually:

```http
POST /cleanup-expired
Header: x-api-key: your_api_key
```

Or run via cron:
```bash
curl -X POST http://localhost:8000/cleanup-expired -H "x-api-key: supersecretapikey"
```

---

## 🧪 Health Check

```http
GET /health
```

Response:
```json
{ "status": "ok" }
```

---

## 🗂 Project Structure

```
filenest/
├── storage/           # Uploaded files
├── data/              # SQLite or Postgres data
├── backend/
│   ├── main.py        # FastAPI app
│   ├── api_filnest.py # Endpoints
│   └── settings.py    # Config loader
├── docker-compose.yml
└── .env
```

---

## 🧰 Tips for Production

- Use Nginx or Traefik to serve files & HTTPS  
- Mount volumes for persistent file + db storage  
- Use PostgreSQL for concurrency-heavy use  
- Protect cleanup route via API key or scheduling system  

---

## 📄 License

MIT License  
© [Vincenzo Marafioti](mailto:enzo.mar@gmail.com)

---

## 🤝 Contributions Welcome!

Open issues, fork, submit PRs, or suggest features.  
FileNest was built for flexibility—adapt it to your use case or automation workflow.
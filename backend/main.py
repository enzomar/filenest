from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from settings import settings
from api_filnest import router as filenest_router
from api_s3 import router as s3_router

app = FastAPI(title="FileNest")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(filenest_router)
# app.include_router(s3_router)

# Absolute path to frontend folder
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Serve static files (like /static/js/app.js, /static/css/style.css)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

# Serve index.html at root
@app.get("/", include_in_schema=False)
async def serve_frontend():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found"}

# Health check endpoint
@app.get("/health", include_in_schema=True, tags=["Health"])
async def health_check():
    return {"status": "ok"}

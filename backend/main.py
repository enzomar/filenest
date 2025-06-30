from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os


from settings import settings
from api_filnest import router as filenest_router
from api_s3 import router as s3_router

app = FastAPI(
    title="Filenest: File and Metadata Storage API",
    description="""
Filenest API is a lightweight, secure file storage and metadata tagging system. It supports bucket creation, file uploads, metadata updates, and TTL (time-to-live) for automatic expiration.

Designed for developers and technical users as well as non-technical admins using a simple UI.
""",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(filenest_router)
# app.include_router(s3_router, prefix="/api")

@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}

@app.post("/cleanup-expired", include_in_schema=False)
async def trigger_full_cleanup(request: Request):
    api_key = request.headers.get("x-api-key")
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    await cleanup_all_buckets()
    return {"detail": "All expired files cleaned up."}

# Serve frontend only in development
if settings.ENV.lower() == "dev":

    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse("static/index.html")

    app.mount("/files", StaticFiles(directory=os.path.abspath("../storage")), name="files")

 


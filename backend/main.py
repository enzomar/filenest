from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
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
#app.include_router(s3_router)

# Serve admin.html at root "/"
@app.get("/", include_in_schema=False)
async def serve_admin_root():
    admin_path = Path("static/admin.html")
    if admin_path.exists():
        return FileResponse(admin_path)
    return {"error": "Admin UI not found"}

# Mount static folder for assets like JS, CSS, images
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

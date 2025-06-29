from fastapi.security.api_key import APIKeyHeader
from fastapi import Security, HTTPException
from typing import Optional
from settings import settings

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    if api_key == settings.API_KEY:
        return api_key
    raise HTTPException(status_code=403, detail="Invalid API Key")

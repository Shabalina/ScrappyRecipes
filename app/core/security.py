"""API key authentication for the protected /api/v1/... surface.

`/health` stays public (container health probes have no way to carry a
secret), so this dependency is attached per-router/per-route rather than at
the FastAPI app level.
"""
import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    app_api_key = os.environ.get("APP_API_KEY", "local_dev_secret_key_123")
    if api_key != app_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key",
        )
    return api_key

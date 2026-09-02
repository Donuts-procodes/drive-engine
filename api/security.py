"""
API Key authentication dependency.

When API_SECRET_KEY is set in the environment, all protected endpoints
require an `X-API-Key` header matching that value. If the env var is
unset or empty, authentication is disabled (dev mode).
"""
import os
import logging
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_SECRET_KEY = os.getenv("API_SECRET_KEY", "")

if _SECRET_KEY:
    logger.info("API Key authentication is ENABLED.")
else:
    logger.warning("API_SECRET_KEY is not set — authentication is DISABLED (dev mode).")


async def require_api_key(api_key: str = Security(_API_KEY_HEADER)):
    """FastAPI dependency: validates the X-API-Key header."""
    if not _SECRET_KEY:
        # Dev mode — skip auth
        return None
    if not api_key or api_key != _SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )
    return api_key

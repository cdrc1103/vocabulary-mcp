import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

API_KEY = os.getenv("API_KEY", "")
if not API_KEY:
    raise RuntimeError("API_KEY environment variable is not set")

PWA_PASSWORD = os.getenv("PWA_PASSWORD", "")
if not PWA_PASSWORD:
    raise RuntimeError("PWA_PASSWORD environment variable is not set")

# Reuse API_KEY as JWT secret — one secret to manage
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_DAYS = 30

UNPROTECTED_PATHS = {"/health", "/auth/login"}


def create_token() -> str:
    payload = {
        "sub": "pwa",
        "exp": datetime.now(UTC) + timedelta(days=_JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, API_KEY, algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> bool:
    try:
        jwt.decode(token, API_KEY, algorithms=[_JWT_ALGORITHM])
        return True
    except jwt.PyJWTError:
        return False


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        # MCP server: static API key
        key = request.headers.get("X-API-Key")
        if key and key == API_KEY:
            return await call_next(request)

        # PWA: short-lived JWT
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if verify_token(token):
                return await call_next(request)

        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

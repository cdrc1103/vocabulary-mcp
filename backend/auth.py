import os
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


API_KEY = os.getenv("API_KEY", "")

UNPROTECTED_PATHS = {"/health"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        key = request.headers.get("X-API-Key")
        if not key or key != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

        return await call_next(request)

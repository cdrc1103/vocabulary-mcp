"""Authentication utilities for vocabulary API.

Provides JWT token generation, API key validation, and middleware for securing
FastAPI endpoints. Supports both Bearer token and API key authentication.
"""

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
    """Generate a JWT bearer token for API access.

    Creates a signed JWT token with a 30-day expiration for PWA authentication.
    The token subject is hardcoded to 'pwa' for single-client usage.

    Returns:
        A JWT token as a string.
    """
    payload = {
        "sub": "pwa",
        "exp": datetime.now(UTC) + timedelta(days=_JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, API_KEY, algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> bool:
    """Verify the validity of a JWT bearer token.

    Decodes and validates the token signature and expiration using the shared
    API_KEY secret. Returns False if the token is malformed or expired.

    Args:
        token: JWT token string to verify.

    Returns:
        True if the token is valid, False otherwise.
    """
    try:
        jwt.decode(token, API_KEY, algorithms=[_JWT_ALGORITHM])
        return True
    except jwt.PyJWTError:
        return False


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware for API key and JWT authentication in FastAPI.

    Validates incoming requests against configured API keys (for MCP servers)
    and JWT bearer tokens (for PWA clients). Skips authentication for OPTIONS
    requests and unprotected paths like /health and /auth/login.

    Raises 401 Unauthorized if the request lacks valid credentials.
    """

    async def dispatch(self, request: Request, call_next):
        """Process incoming request and validate authentication.

        Checks for valid API key (X-API-Key header) or Bearer token (Authorization
        header). Allows unauthenticated access to OPTIONS requests and paths in
        UNPROTECTED_PATHS.

        Args:
            request: The incoming HTTP request.
            call_next: Callable to proceed to the next middleware or handler.

        Returns:
            The response from the next handler if authenticated, or a 401 JSON
            response if authentication fails.
        """
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

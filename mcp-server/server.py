import os

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

VOCAB_API_URL = os.getenv("VOCAB_API_URL", "http://localhost:8000")
VOCAB_API_KEY = os.getenv("VOCAB_API_KEY", "")
if not VOCAB_API_KEY:
    raise RuntimeError("VOCAB_API_KEY environment variable is not set")

MCP_SECRET = os.getenv("MCP_SECRET", "")
if not MCP_SECRET:
    raise RuntimeError("MCP_SECRET environment variable is not set")

# Module-level client: reuses connection pool and TLS session across calls
_http_client = httpx.AsyncClient()

# ── MCP tools ─────────────────────────────────────────────────────────────────

mcp = FastMCP("vocabulary")


@mcp.tool(
    description=(
        "Add a vocabulary word to the personal study app. "
        "Use this when the user asks to save a word, or when you've "
        "explained a word and want to offer to save it."
    )
)
async def add_vocabulary(
    word: str,
    definition: str,
    example: str | None = None,
    language: str | None = None,
) -> str:
    # Only forward explicitly provided optional fields
    payload: dict[str, str] = {"word": word, "definition": definition}
    if example is not None:
        payload["example"] = example
    if language is not None:
        payload["language"] = language

    try:
        response = await _http_client.post(
            f"{VOCAB_API_URL}/vocabulary",
            json=payload,
            headers={"X-API-Key": VOCAB_API_KEY},
            timeout=10.0,
        )
        response.raise_for_status()
        word_data = response.json()
        return (
            f"Successfully saved '{word_data.get('word', word)}' to your vocabulary deck. "
            f"It will be due for review on {word_data.get('next_review', 'a future date')}."
        )
    except httpx.HTTPStatusError as e:
        return f"Failed to save word: HTTP {e.response.status_code} — {e.response.text}"
    except Exception as e:
        return f"Failed to save word: {e}"


# ── HTTP layer ─────────────────────────────────────────────────────────────────

_UNPROTECTED = {"/health"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in _UNPROTECTED:
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != MCP_SECRET:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", mcp.streamable_http_app()),
    ]
)
app.add_middleware(BearerAuthMiddleware)

# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

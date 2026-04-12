"""Model Context Protocol (MCP) server for vocabulary management.

Exposes vocabulary operations as MCP tools accessible to Claude and other AI clients.
Supports OAuth 2.0 authentication with configurable authorization endpoints.
"""

import os
from typing import Required, TypedDict

import httpx
import uvicorn
from database import init_db
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from oauth_provider import VocabularyOAuthProvider
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse


class VocabWord(TypedDict, total=False):
    """Schema for vocabulary word in MCP tool requests.

    Attributes:
        word: The vocabulary word (required).
        definition: Definition of the word (required).
        example: Optional example sentence or usage.
        language: Optional language code.
    """

    word: Required[str]
    definition: Required[str]
    example: str
    language: str


VOCAB_API_URL = os.getenv("VOCAB_API_URL", "http://localhost:8000")
VOCAB_API_KEY = os.getenv("VOCAB_API_KEY", "")
if not VOCAB_API_KEY:
    raise RuntimeError("VOCAB_API_KEY environment variable is not set")

MCP_SECRET = os.getenv("MCP_SECRET", "")
if not MCP_SECRET:
    raise RuntimeError("MCP_SECRET environment variable is not set")

ISSUER_URL = os.getenv("ISSUER_URL", "http://localhost:8080")
DATABASE_PATH = os.getenv("DATABASE_PATH", "oauth.db")

# Initialize database
init_db(DATABASE_PATH)

# Module-level client: reuses connection pool and TLS session across calls
_http_client = httpx.AsyncClient()

# ── OAuth provider ────────────────────────────────────────────────────────────

oauth_provider = VocabularyOAuthProvider(
    db_path=DATABASE_PATH,
    secret=MCP_SECRET,
    issuer_url=ISSUER_URL,
)

# ── MCP server with OAuth ─────────────────────────────────────────────────────

mcp = FastMCP(
    "vocabulary",
    auth_server_provider=oauth_provider,
    auth=AuthSettings(
        issuer_url=ISSUER_URL,
        resource_server_url=ISSUER_URL,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    ),
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8080")),
)

# ── MCP tools ─────────────────────────────────────────────────────────────────


@mcp.tool(
    description=(
        "Add multiple vocabulary words at once to the personal study app (max 50). "
        "Use this when the user has asked to save several words from a conversation, "
        "or when you've explained multiple words and want to offer to save them all."
    )
)
async def bulk_add_vocabulary(
    words: list[VocabWord],
) -> str:
    """Add multiple vocabulary words at once via MCP tool.

    Creates vocabulary entries in bulk, accessible to Claude and other MCP clients.
    Supports up to 50 words per request. Skips duplicate words automatically.

    Args:
        words: List of VocabWord entries, each containing word, definition, and
            optional example and language fields.

    Returns:
        Success message with count of saved and skipped words, or error message
        with HTTP status code or exception details if the request fails.

    Example:
        MCP clients can call this tool to save multiple words:
        {
            "words": [
                {
                    "word": "serendipity",
                    "definition": "Finding valuable things by chance",
                    "example": "It was pure serendipity that we met.",
                    "language": "en"
                },
                {
                    "word": "ephemeral",
                    "definition": "Lasting for a very short time",
                    "language": "en"
                }
            ]
        }
    """
    try:
        response = await _http_client.post(
            f"{VOCAB_API_URL}/vocabulary/bulk",
            json={"words": words},
            headers={"X-API-Key": VOCAB_API_KEY},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        inserted_count = len(data.get("inserted", []))
        skipped_count = data.get("skipped_count", 0)
        msg = f"Saved {inserted_count} words to your vocabulary deck."
        if skipped_count > 0:
            msg += f" {skipped_count} duplicates skipped."
        return msg
    except httpx.HTTPStatusError as e:
        return f"Failed to save words: HTTP {e.response.status_code} — {e.response.text}"
    except Exception as e:
        return f"Failed to save words: {e}"


# ── Custom routes (unprotected) ───────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    """Health check endpoint for MCP server.

    Provides a lightweight status check for monitoring and load balancers.

    Args:
        _request: HTTP request (unused).

    Returns:
        JSON response with status "ok".
    """
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/authorize/submit", methods=["GET", "POST"])
async def authorize_submit(request: Request) -> HTMLResponse | RedirectResponse:
    """Password-gated OAuth authorization endpoint.

    Handles MCP OAuth 2.0 authorization flows with password verification.
    GET requests display a login form; POST requests validate the password and
    redirect to the authorization completion URL on success.

    Args:
        request: HTTP request containing auth_params and password (on POST).

    Returns:
        GET: HTML login form with optional error message.
        POST: Redirect to authorization completion URL on success, or error form on failure.

    Raises:
        401 Unauthorized: If password is incorrect.
        400 Bad Request: If authorization session has expired.
    """
    if request.method == "GET":
        auth_params = request.query_params.get("auth_params", "")
        return HTMLResponse(oauth_provider.render_login_page(auth_params))

    # POST: validate password
    form = await request.form()
    auth_params_nonce = str(form.get("auth_params", ""))
    password = str(form.get("password", ""))

    if password != MCP_SECRET:
        return HTMLResponse(
            oauth_provider.render_login_page(auth_params_nonce, error="Invalid password"),
            status_code=401,
        )

    # Look up pending authorization params
    pending = oauth_provider._pending_params.pop(auth_params_nonce, None)
    if pending is None:
        return HTMLResponse(
            oauth_provider.render_login_page(
                auth_params_nonce, error="Session expired. Please try again."
            ),
            status_code=400,
        )

    client, params = pending
    redirect_url = oauth_provider.complete_authorization(client, params)
    return RedirectResponse(url=redirect_url, status_code=302)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8080")))

import os

import httpx
import uvicorn
from database import init_db
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from oauth_provider import VocabularyOAuthProvider
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

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


# ── Custom routes (unprotected) ───────────────────────────────────────────────


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.custom_route("/authorize/submit", methods=["GET", "POST"])
async def authorize_submit(request: Request) -> HTMLResponse | RedirectResponse:
    """Password-gated OAuth authorization endpoint."""
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

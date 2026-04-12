"""OAuth database operations for MCP server.

Manages OAuth 2.0 client registrations, authorization codes, and tokens.
Uses SQLite for persistent storage of client credentials and authorization state.
"""

import sqlite3
import time


def init_db(db_path: str) -> None:
    """Initialize OAuth database and create tables if missing.

    Args:
        db_path: Path to SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id TEXT PRIMARY KEY, client_secret TEXT,
            client_info_json TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_codes (
            code TEXT PRIMARY KEY, client_id TEXT NOT NULL,
            code_challenge TEXT NOT NULL, redirect_uri TEXT NOT NULL,
            redirect_uri_provided_explicitly INTEGER NOT NULL,
            scopes_json TEXT NOT NULL, expires_at REAL NOT NULL, resource TEXT
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token TEXT PRIMARY KEY, client_id TEXT NOT NULL,
            scopes_json TEXT NOT NULL, expires_at REAL
        );
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti TEXT PRIMARY KEY, revoked_at REAL NOT NULL
        );
    """)
    conn.close()


def _connect(db_path: str) -> sqlite3.Connection:
    """Create a database connection with Row factory enabled.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        SQLite connection object with Row factory for dict-like access.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def save_client(
    db_path: str, client_id: str, client_secret: str | None, client_info_json: str
) -> None:
    """Register or update an OAuth client.

    Args:
        db_path: Path to SQLite database file.
        client_id: Unique client identifier.
        client_secret: Client authentication secret (optional for public clients).
        client_info_json: JSON string containing client metadata.
    """
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO clients (client_id, client_secret, client_info_json, created_at) VALUES (?, ?, ?, ?)",
        (client_id, client_secret, client_info_json, time.time()),
    )
    conn.commit()
    conn.close()


def get_client(db_path: str, client_id: str) -> dict | None:
    """Retrieve OAuth client details by ID.

    Args:
        db_path: Path to SQLite database file.
        client_id: Client identifier.

    Returns:
        Dictionary with client data (client_id, client_secret, client_info_json, created_at) or None if not found.
    """
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def save_auth_code(
    db_path: str,
    code: str,
    client_id: str,
    code_challenge: str,
    redirect_uri: str,
    redirect_uri_provided_explicitly: bool,
    scopes_json: str,
    expires_at: float,
    resource: str | None,
) -> None:
    """Store an OAuth authorization code for PKCE flow.

    Args:
        db_path: Path to SQLite database file.
        code: Authorization code value.
        client_id: Associated client identifier.
        code_challenge: PKCE code challenge (SHA256 hash of code verifier).
        redirect_uri: Callback URI for code exchange.
        redirect_uri_provided_explicitly: Whether redirect_uri was provided in initial request.
        scopes_json: JSON string of requested OAuth scopes.
        expires_at: Unix timestamp when code expires.
        resource: Optional resource identifier for resource owner consent.
    """
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO auth_codes (code, client_id, code_challenge, redirect_uri, redirect_uri_provided_explicitly, scopes_json, expires_at, resource) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            code,
            client_id,
            code_challenge,
            redirect_uri,
            int(redirect_uri_provided_explicitly),
            scopes_json,
            expires_at,
            resource,
        ),
    )
    conn.commit()
    conn.close()


def get_auth_code(db_path: str, code: str) -> dict | None:
    """Retrieve authorization code details for exchange.

    Args:
        db_path: Path to SQLite database file.
        code: Authorization code value.

    Returns:
        Dictionary with code data (code, client_id, code_challenge, redirect_uri, scopes_json, expires_at, resource) or None if not found.
    """
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM auth_codes WHERE code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_auth_code(db_path: str, code: str) -> None:
    """Remove an authorization code after exchange or invalidation.

    Args:
        db_path: Path to SQLite database file.
        code: Authorization code to delete.
    """
    conn = _connect(db_path)
    conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
    conn.commit()
    conn.close()


def delete_expired_auth_codes(db_path: str) -> None:
    """Remove all expired authorization codes from database.

    Args:
        db_path: Path to SQLite database file.
    """
    conn = _connect(db_path)
    conn.execute("DELETE FROM auth_codes WHERE expires_at < ?", (time.time(),))
    conn.commit()
    conn.close()


def save_refresh_token(
    db_path: str, token: str, client_id: str, scopes_json: str, expires_at: int | None
) -> None:
    """Store a refresh token for long-lived authorization.

    Args:
        db_path: Path to SQLite database file.
        token: Refresh token value (JWT).
        client_id: Associated client identifier.
        scopes_json: JSON string of granted OAuth scopes.
        expires_at: Unix timestamp when token expires (None for non-expiring tokens).
    """
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO refresh_tokens (token, client_id, scopes_json, expires_at) VALUES (?, ?, ?, ?)",
        (token, client_id, scopes_json, expires_at),
    )
    conn.commit()
    conn.close()


def get_refresh_token(db_path: str, token: str) -> dict | None:
    """Retrieve refresh token details for token refresh.

    Args:
        db_path: Path to SQLite database file.
        token: Refresh token value.

    Returns:
        Dictionary with token data (token, client_id, scopes_json, expires_at) or None if not found.
    """
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM refresh_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_refresh_token(db_path: str, token: str) -> None:
    """Remove a refresh token on logout or revocation.

    Args:
        db_path: Path to SQLite database file.
        token: Refresh token to delete.
    """
    conn = _connect(db_path)
    conn.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def delete_expired_refresh_tokens(db_path: str) -> None:
    """Remove all expired refresh tokens from database.

    Args:
        db_path: Path to SQLite database file.
    """
    conn = _connect(db_path)
    conn.execute(
        "DELETE FROM refresh_tokens WHERE expires_at IS NOT NULL AND expires_at < ?", (time.time(),)
    )
    conn.commit()
    conn.close()


def save_revoked_token(db_path: str, jti: str) -> None:
    """Record a revoked JWT token by its JTI (JWT ID).

    Args:
        db_path: Path to SQLite database file.
        jti: JWT ID claim uniquely identifying the token.
    """
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at) VALUES (?, ?)", (jti, time.time())
    )
    conn.commit()
    conn.close()


def is_token_revoked(db_path: str, jti: str) -> bool:
    """Check if a JWT token has been revoked.

    Args:
        db_path: Path to SQLite database file.
        jti: JWT ID claim to check.

    Returns:
        True if token is revoked, False otherwise.
    """
    conn = _connect(db_path)
    row = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)).fetchone()
    conn.close()
    return row is not None

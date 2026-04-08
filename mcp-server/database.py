import sqlite3
import time


def init_db(db_path: str) -> None:
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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def save_client(
    db_path: str, client_id: str, client_secret: str | None, client_info_json: str
) -> None:
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO clients (client_id, client_secret, client_info_json, created_at) VALUES (?, ?, ?, ?)",
        (client_id, client_secret, client_info_json, time.time()),
    )
    conn.commit()
    conn.close()


def get_client(db_path: str, client_id: str) -> dict | None:
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
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM auth_codes WHERE code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_auth_code(db_path: str, code: str) -> None:
    conn = _connect(db_path)
    conn.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
    conn.commit()
    conn.close()


def delete_expired_auth_codes(db_path: str) -> None:
    conn = _connect(db_path)
    conn.execute("DELETE FROM auth_codes WHERE expires_at < ?", (time.time(),))
    conn.commit()
    conn.close()


def save_refresh_token(
    db_path: str, token: str, client_id: str, scopes_json: str, expires_at: int | None
) -> None:
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO refresh_tokens (token, client_id, scopes_json, expires_at) VALUES (?, ?, ?, ?)",
        (token, client_id, scopes_json, expires_at),
    )
    conn.commit()
    conn.close()


def get_refresh_token(db_path: str, token: str) -> dict | None:
    conn = _connect(db_path)
    row = conn.execute("SELECT * FROM refresh_tokens WHERE token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_refresh_token(db_path: str, token: str) -> None:
    conn = _connect(db_path)
    conn.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def delete_expired_refresh_tokens(db_path: str) -> None:
    conn = _connect(db_path)
    conn.execute(
        "DELETE FROM refresh_tokens WHERE expires_at IS NOT NULL AND expires_at < ?", (time.time(),)
    )
    conn.commit()
    conn.close()


def save_revoked_token(db_path: str, jti: str) -> None:
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO revoked_tokens (jti, revoked_at) VALUES (?, ?)", (jti, time.time())
    )
    conn.commit()
    conn.close()


def is_token_revoked(db_path: str, jti: str) -> bool:
    conn = _connect(db_path)
    row = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)).fetchone()
    conn.close()
    return row is not None

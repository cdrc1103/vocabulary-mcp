import json
import secrets
import time

import jwt
from database import (
    delete_auth_code,
    delete_refresh_token,
    get_auth_code,
    get_client,
    get_refresh_token,
    is_token_revoked,
    save_auth_code,
    save_client,
    save_refresh_token,
    save_revoked_token,
)
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from oauth_templates import LOGIN_PAGE_HTML
from pydantic import AnyUrl

ACCESS_TOKEN_EXPIRY = 3600
REFRESH_TOKEN_EXPIRY = 30 * 24 * 3600
AUTH_CODE_EXPIRY = 300


class VocabularyOAuthProvider:
    def __init__(self, db_path: str, secret: str, issuer_url: str):
        self.db_path = db_path
        self.secret = secret
        self.issuer_url = issuer_url
        self._pending_params: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = get_client(self.db_path, client_id)
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row["client_info_json"])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        client_info.client_id = secrets.token_hex(16)
        client_info.client_secret = secrets.token_hex(32)
        client_info.client_id_issued_at = int(time.time())
        save_client(
            self.db_path,
            client_info.client_id,
            client_info.client_secret,
            client_info.model_dump_json(),
        )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        nonce = secrets.token_hex(16)
        self._pending_params[nonce] = (client, params)
        return f"{self.issuer_url}/authorize/submit?auth_params={nonce}"

    def complete_authorization(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = secrets.token_hex(32)
        now = time.time()
        save_auth_code(
            self.db_path,
            code=code,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes_json=json.dumps(params.scopes or []),
            expires_at=now + AUTH_CODE_EXPIRY,
            resource=params.resource,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        row = get_auth_code(self.db_path, authorization_code)
        if row is None:
            return None
        if row["expires_at"] < time.time():
            delete_auth_code(self.db_path, authorization_code)
            return None
        if row["client_id"] != client.client_id:
            return None
        return AuthorizationCode(
            code=row["code"],
            scopes=json.loads(row["scopes_json"]),
            expires_at=row["expires_at"],
            client_id=row["client_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=AnyUrl(row["redirect_uri"]),
            redirect_uri_provided_explicitly=bool(row["redirect_uri_provided_explicitly"]),
            resource=row["resource"],
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        delete_auth_code(self.db_path, authorization_code.code)
        now = time.time()
        jti = secrets.token_hex(16)
        payload = {
            "sub": client.client_id,
            "jti": jti,
            "scopes": authorization_code.scopes,
            "iat": int(now),
            "exp": int(now) + ACCESS_TOKEN_EXPIRY,
            "iss": self.issuer_url,
        }
        access_token = jwt.encode(payload, self.secret, algorithm="HS256")
        refresh_token_str = secrets.token_hex(32)
        save_refresh_token(
            self.db_path,
            token=refresh_token_str,
            client_id=client.client_id,
            scopes_json=json.dumps(authorization_code.scopes),
            expires_at=int(now + REFRESH_TOKEN_EXPIRY),
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_EXPIRY,
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = get_refresh_token(self.db_path, refresh_token)
        if row is None:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            delete_refresh_token(self.db_path, refresh_token)
            return None
        if row["client_id"] != client.client_id:
            return None
        return RefreshToken(
            token=row["token"],
            client_id=row["client_id"],
            scopes=json.loads(row["scopes_json"]),
            expires_at=row["expires_at"],
        )

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        delete_refresh_token(self.db_path, refresh_token.token)
        effective_scopes = scopes if scopes else refresh_token.scopes
        now = time.time()
        jti = secrets.token_hex(16)
        payload = {
            "sub": client.client_id,
            "jti": jti,
            "scopes": effective_scopes,
            "iat": int(now),
            "exp": int(now) + ACCESS_TOKEN_EXPIRY,
            "iss": self.issuer_url,
        }
        access_token = jwt.encode(payload, self.secret, algorithm="HS256")
        new_refresh_token = secrets.token_hex(32)
        save_refresh_token(
            self.db_path,
            token=new_refresh_token,
            client_id=client.client_id,
            scopes_json=json.dumps(effective_scopes),
            expires_at=int(now + REFRESH_TOKEN_EXPIRY),
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_EXPIRY,
            refresh_token=new_refresh_token,
            scope=" ".join(effective_scopes) if effective_scopes else None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            payload = jwt.decode(
                token, self.secret, algorithms=["HS256"], options={"require": ["sub", "jti", "exp"]}
            )
        except jwt.PyJWTError:
            return None
        jti = payload.get("jti")
        if jti and is_token_revoked(self.db_path, jti):
            return None
        exp = payload.get("exp")
        return AccessToken(
            token=token,
            client_id=payload["sub"],
            scopes=payload.get("scopes", []),
            expires_at=int(exp) if exp is not None else None,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            try:
                payload = jwt.decode(
                    token.token, self.secret, algorithms=["HS256"], options={"require": ["jti"]}
                )
                save_revoked_token(self.db_path, payload["jti"])
            except jwt.PyJWTError:
                pass
        elif isinstance(token, RefreshToken):
            delete_refresh_token(self.db_path, token.token)

    def render_login_page(self, auth_params_nonce: str, error: str | None = None) -> str:
        error_html = f'<div class="error">{error}</div>' if error else ""
        return LOGIN_PAGE_HTML.format(auth_params_encoded=auth_params_nonce, error_html=error_html)

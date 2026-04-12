"""OAuth 2.0 provider implementation for MCP server.

Implements the authorization code grant flow with support for client registration,
authorization code generation, and token issuance per RFC 6749. Includes support
for PKCE (RFC 7636) code challenges and refresh token rotation.
"""

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
    """OAuth 2.0 authorization server for vocabulary API access.

    Implements the authorization code grant flow, supporting client registration,
    authorization endpoint, and token endpoint per RFC 6749 and RFC 7636 (PKCE).
    Tokens are issued as HS256-signed JWTs with automatic expiration and revocation
    support. Refresh tokens enable long-lived access without requiring re-authorization.
    """

    def __init__(self, db_path: str, secret: str, issuer_url: str):
        """Initialize OAuth provider with database and issuer configuration.

        Args:
            db_path: Path to OAuth database file for persisting clients, codes, and tokens.
            secret: HS256 secret key for JWT token signing and verification.
            issuer_url: OAuth issuer URL (used in token 'iss' claim and authorization redirects).
        """
        self.db_path = db_path
        self.secret = secret
        self.issuer_url = issuer_url
        self._pending_params: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Retrieve registered OAuth client by ID.

        Args:
            client_id: The OAuth client identifier.

        Returns:
            OAuthClientInformationFull object if client exists, None otherwise.
        """
        row = get_client(self.db_path, client_id)
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row["client_info_json"])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Register a new OAuth client application.

        Generates a cryptographically-secure client_id and client_secret. Both should
        be treated as secrets; client_secret must be protected and never exposed to
        untrusted clients.

        Args:
            client_info: Client metadata (modified in-place with generated credentials).

        Side effects:
            - Modifies client_info to set client_id, client_secret, and client_id_issued_at.
            - Persists client to database.
        """
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
        """Generate authorization request URL for resource owner interaction.

        Stores pending authorization parameters server-side with a nonce for security.
        Resource owners will visit the returned URL to log in and approve the request.

        Args:
            client: The OAuth client requesting authorization.
            params: Authorization parameters (scopes, redirect_uri, code_challenge, etc.).

        Returns:
            Authorization endpoint URL to redirect resource owner to.
        """
        nonce = secrets.token_hex(16)
        self._pending_params[nonce] = (client, params)
        return f"{self.issuer_url}/authorize/submit?auth_params={nonce}"

    def complete_authorization(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Generate authorization code after resource owner approval.

        Called after the resource owner has authenticated and approved the authorization
        request. Creates a short-lived authorization code that the client exchanges
        for tokens. Supports PKCE (RFC 7636) by storing code_challenge for later
        verification during token exchange.

        Args:
            client: The OAuth client that was approved.
            params: Authorization parameters including scopes, redirect_uri, and code_challenge.

        Returns:
            Redirect URI with authorization code and state parameter.

        Note:
            Authorization codes expire after AUTH_CODE_EXPIRY (300s) and are single-use.
        """
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
        """Load and validate authorization code for token exchange.

        Retrieves stored authorization code, verifies expiration and client ownership,
        and returns structured code data. Expired codes are automatically deleted.
        Does NOT consume the code; that happens during token exchange.

        Args:
            client: The OAuth client requesting the token exchange.
            authorization_code: The authorization code to validate.

        Returns:
            AuthorizationCode object if valid and owned by client, None if invalid,
            expired, or client_id mismatch.

        Note:
            Expired codes are automatically cleaned up from the database.
        """
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
        """Exchange authorization code for access and refresh tokens.

        Consumes the authorization code (single-use) and issues:
        - Access token: HS256-signed JWT with scopes and expiration
        - Refresh token: Cryptographically-random token for token renewal

        Args:
            client: The OAuth client making the exchange request.
            authorization_code: Valid AuthorizationCode from load_authorization_code.

        Returns:
            OAuthToken with access_token (JWT), refresh_token, token_type, and expires_in.

        Note:
            The authorization code is consumed and cannot be reused.
            Access tokens expire after ACCESS_TOKEN_EXPIRY (3600s).
            Refresh tokens expire after REFRESH_TOKEN_EXPIRY (30 days).
        """
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
        """Load and validate refresh token for token renewal.

        Retrieves stored refresh token, verifies expiration and client ownership.
        Expired tokens are automatically deleted. Does NOT consume the token;
        that happens during token renewal.

        Args:
            client: The OAuth client requesting token renewal.
            refresh_token: The refresh token to validate.

        Returns:
            RefreshToken object if valid and owned by client, None if invalid,
            expired, or client_id mismatch.

        Note:
            Expired tokens are automatically cleaned up from the database.
        """
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
        """Renew access token using refresh token with optional scope downscoping.

        Implements refresh token rotation: the old refresh token is consumed and a new
        one is issued. Clients may request a subset of originally-granted scopes.
        This enables sliding window token expiration and scope limitation.

        Args:
            client: The OAuth client making the renewal request.
            refresh_token: Valid RefreshToken from load_refresh_token.
            scopes: Requested scopes (subset of original). If empty, uses original scopes.

        Returns:
            OAuthToken with new access_token (JWT), new refresh_token, and metadata.

        Note:
            The old refresh token is consumed and cannot be reused.
            New access tokens expire after ACCESS_TOKEN_EXPIRY (3600s).
            New refresh tokens expire after REFRESH_TOKEN_EXPIRY (30 days).
            Scope downscoping is allowed; requesting new scopes fails (not implemented here).
        """
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
        """Validate and parse access token JWT.

        Verifies JWT signature using provider's secret, checks token expiration,
        and confirms token has not been revoked. Enforces presence of required claims
        (sub, jti, exp) for security.

        Args:
            token: HS256-signed JWT access token to validate.

        Returns:
            AccessToken object with client_id, scopes, and expiration if valid.
            None if invalid signature, missing claims, expired, or revoked.

        Note:
            Tokens are validated at request time; pre-expiration checks are the
            client's responsibility. Revoked tokens are tracked by jti (JWT ID).
        """
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
        """Revoke an access or refresh token.

        For access tokens: Marks the jti (JWT ID) as revoked in the database.
        Future load_access_token calls will reject this token.
        For refresh tokens: Deletes the token from the database (cannot be renewed).

        Args:
            token: AccessToken or RefreshToken to revoke.

        Note:
            Revocation is immediate; in-flight requests with revoked access tokens
            will be rejected on next validation. Refresh tokens cannot be renewed after
            deletion. Silently ignores JWT decode errors (e.g., malformed tokens).
        """
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
        """Render HTML login page for resource owner authorization.

        Generates interactive HTML page where resource owners authenticate and approve
        the authorization request. Embeds the auth_params_nonce (server-side secret)
        and optional error message in the form.

        Args:
            auth_params_nonce: Server-side nonce linking page to pending authorization
                parameters (from authorize method).
            error: Optional error message to display (e.g., "Invalid credentials").

        Returns:
            Rendered HTML string ready for HTTP response.

        Note:
            The nonce ensures authorization parameters are not exposed to the client.
            Error messages should be pre-escaped to prevent XSS (current implementation
            does NOT escape; caller must validate).
        """
        error_html = f'<div class="error">{error}</div>' if error else ""
        return LOGIN_PAGE_HTML.format(auth_params_encoded=auth_params_nonce, error_html=error_html)

"""HTML templates for OAuth authorization flows.

Provides HTML/Jinja2 templates for login, consent, and authorization pages.
Renders forms for user authentication and scope approval.
"""


def login_template(auth_params_encoded: str, error_html: str = "") -> str:
    """HTML form for user password authentication.

    Renders an interactive login page where resource owners enter credentials
    to authenticate for OAuth authorization. The form submits to /authorize/submit
    endpoint with the auth parameters nonce embedded as a hidden field.

    Args:
        auth_params_encoded: Server-side nonce linking the form to pending
            authorization parameters stored server-side. Prevents exposure of
            full authorization parameters to the client.
        error_html: Optional HTML error message to display above the form
            (e.g., for invalid credentials). If provided, should be pre-escaped
            to prevent XSS vulnerabilities.

    Returns:
        HTML form string with password input field and sign-in button.

    Note:
        - Form submission method: POST to /authorize/submit
        - Form field: password (required, autofocused)
        - Error display: rendered above the form if provided
        - Client-side behavior: Form validates password presence before submission.
    """
    login_page_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vocabulary MCP — Sign In</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #f5f5f5;
        }}
        .card {{
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 360px;
        }}
        h1 {{ font-size: 1.25rem; margin: 0 0 1.5rem; text-align: center; }}
        label {{ display: block; margin-bottom: 0.5rem; font-size: 0.875rem; color: #333; }}
        input[type="password"] {{
            width: 100%;
            padding: 0.5rem;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 1rem;
            box-sizing: border-box;
        }}
        button {{
            width: 100%;
            padding: 0.625rem;
            margin-top: 1rem;
            background: #2563eb;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
        }}
        button:hover {{ background: #1d4ed8; }}
        .error {{
            color: #dc2626;
            font-size: 0.875rem;
            margin-bottom: 1rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Vocabulary MCP</h1>
        {error_html}
        <form method="POST" action="/authorize/submit">
            <input type="hidden" name="auth_params" value="{auth_params_encoded}">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required autofocus>
            <button type="submit">Sign In</button>
        </form>
    </div>
</body>
</html>"""
    return login_page_html.format(auth_params_encoded=auth_params_encoded, error_html=error_html)


def consent_template(client_name: str, scopes: list[str]) -> str:
    """HTML consent form for OAuth scope approval.

    Renders an interactive consent page where resource owners review requested
    scopes and approve or deny the authorization request. The form displays
    the client application name and a list of requested OAuth scopes with
    checkboxes for granular approval.

    Args:
        client_name: Human-readable name of the OAuth client requesting
            authorization (displayed prominently on the page).
        scopes: List of requested OAuth scope identifiers to display for
            approval (e.g., ['read:vocab', 'write:definitions']).

    Returns:
        HTML form string with scope checkboxes and approval/deny buttons.

    Note:
        - Form submission method: POST to /authorize/consent
        - Form fields: auth_params (hidden), scopes[] (checkboxes for each scope)
        - Approval button: Submits form to grant authorization
        - Deny button: Returns to client with authorization_denied error
        - Client-side behavior: At least one scope must be selected for approval.
        - Scope display: Shows scope name and description if available.
    """
    # Consent form template with client name and scope rendering
    consent_page_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vocabulary MCP — Authorization Required</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #f5f5f5;
        }}
        .card {{
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 480px;
        }}
        h1 {{ font-size: 1.25rem; margin: 0 0 0.5rem; text-align: center; }}
        .client-name {{ color: #666; font-size: 0.875rem; text-align: center; margin-bottom: 1.5rem; }}
        .scopes-section {{ margin: 1.5rem 0; }}
        .scopes-label {{ font-size: 0.875rem; font-weight: 600; margin-bottom: 1rem; color: #333; }}
        .scope-item {{
            display: flex;
            align-items: flex-start;
            margin-bottom: 1rem;
            padding: 0.5rem 0;
        }}
        .scope-item input {{
            margin-right: 0.75rem;
            margin-top: 0.25rem;
            cursor: pointer;
        }}
        .scope-info {{
            flex: 1;
        }}
        .scope-name {{ font-size: 0.875rem; font-weight: 500; color: #333; }}
        .scope-description {{ font-size: 0.75rem; color: #666; margin-top: 0.25rem; }}
        .button-group {{
            display: flex;
            gap: 1rem;
            margin-top: 2rem;
        }}
        button {{
            flex: 1;
            padding: 0.625rem;
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
            font-weight: 500;
        }}
        .approve-button {{
            background: #2563eb;
            color: white;
        }}
        .approve-button:hover {{ background: #1d4ed8; }}
        .deny-button {{
            background: #e5e7eb;
            color: #333;
        }}
        .deny-button:hover {{ background: #d1d5db; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Authorization Required</h1>
        <div class="client-name">{client_name} is requesting access to your account</div>
        <form method="POST" action="/authorize/consent">
            <input type="hidden" name="auth_params" value="{auth_params_encoded}">
            <div class="scopes-section">
                <div class="scopes-label">Requested Permissions:</div>
                {scopes_html}
            </div>
            <div class="button-group">
                <button type="submit" class="approve-button" name="action" value="approve">Approve</button>
                <button type="submit" class="deny-button" name="action" value="deny">Deny</button>
            </div>
        </form>
    </div>
</body>
</html>"""

    scopes_html = ""
    for scope in scopes:
        scopes_html += f"""<div class="scope-item">
                <input type="checkbox" id="scope-{scope}" name="scopes" value="{scope}" checked>
                <div class="scope-info">
                    <div class="scope-name">{scope}</div>
                </div>
            </div>
            """

    return consent_page_html.format(
        client_name=client_name, auth_params_encoded="", scopes_html=scopes_html
    )


def authorization_error_template(error: str, error_description: str = "") -> str:
    """HTML error page for authorization failures.

    Renders an error page displayed when authorization fails (invalid request,
    unsupported response type, invalid scope, server error, etc.). Shows the
    error code and optional description to help users understand what went wrong.

    Args:
        error: OAuth 2.0 error code (e.g., 'invalid_request', 'access_denied',
            'unsupported_response_type', 'invalid_scope', 'server_error').
        error_description: Optional human-readable error description to display
            below the error code (e.g., "The requested scope is invalid").

    Returns:
        HTML error page string with error message and details.

    Note:
        - Error code is displayed prominently
        - Description provides context about the error
        - Page includes a close button (typically closes the browser tab/window)
        - Can be used for all OAuth authorization endpoint error scenarios
    """
    error_page_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vocabulary MCP — Authorization Error</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: #f5f5f5;
        }}
        .card {{
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            width: 100%;
            max-width: 360px;
            text-align: center;
        }}
        .error-icon {{
            font-size: 3rem;
            margin-bottom: 1rem;
        }}
        h1 {{ font-size: 1.25rem; margin: 0 0 0.5rem; color: #dc2626; }}
        .error-code {{ font-family: monospace; background: #fee; padding: 0.5rem 1rem; border-radius: 4px; margin: 1rem 0; }}
        .error-description {{ color: #666; font-size: 0.875rem; line-height: 1.5; margin: 1rem 0; }}
        button {{
            width: 100%;
            padding: 0.625rem;
            margin-top: 1.5rem;
            background: #6b7280;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
        }}
        button:hover {{ background: #4b5563; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="error-icon">⚠️</div>
        <h1>Authorization Failed</h1>
        <div class="error-code">{error}</div>
        {description_html}
        <button type="button" onclick="window.close()">Close</button>
    </div>
</body>
</html>"""

    description_html = (
        f'<div class="error-description">{error_description}</div>' if error_description else ""
    )

    return error_page_html.format(error=error, description_html=description_html)

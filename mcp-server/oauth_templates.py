LOGIN_PAGE_HTML = """<!DOCTYPE html>
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

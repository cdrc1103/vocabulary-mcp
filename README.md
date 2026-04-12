# Vocabulary App

A full-stack spaced-repetition vocabulary study system. An AI assistant can push words directly into your personal study deck via an MCP tool, and you review them on an installable mobile PWA.

## Components

| Component | Description |
|-----------|-------------|
| `backend/` | FastAPI + SQLite REST API |
| `mcp-server/` | MCP server exposing `add_vocabulary` to AI assistants |
| `pwa/` | Installable PWA flashcard study app |

---

## 1. Backend API

### Run locally

```bash
cd backend
uv sync

# Create a .env file
echo "API_KEY=$(openssl rand -hex 32)" > .env
echo "DATABASE_PATH=./vocab.db" >> .env

uv run --env-file .env uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Test endpoints

```bash
export API_KEY=<your-key>

# Health check (no auth required)
curl http://localhost:8000/health

# Add a word
curl -X POST http://localhost:8000/vocabulary \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"word":"épanouissement","definition":"A blossoming or fulfillment","language":"French"}'

# List all words
curl http://localhost:8000/vocabulary -H "X-API-Key: $API_KEY"

# Words due for review
curl http://localhost:8000/vocabulary/due -H "X-API-Key: $API_KEY"

# Submit a review (quality 0-5)
curl -X PATCH http://localhost:8000/vocabulary/1/review \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"quality":4}'

# Delete a word
curl -X DELETE http://localhost:8000/vocabulary/1 -H "X-API-Key: $API_KEY"
```

### Deploy

1. Host the backend on any platform that supports Python (e.g. a VPS, container service, or PaaS).
2. Mount a persistent volume for the SQLite database.
3. Set environment variables:
   - `API_KEY` — generate with `openssl rand -hex 32`
   - `DATABASE_PATH` — path to the `.db` file on the persistent volume
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Confirm the service is running: `curl https://your-backend-url/health`

---

## 2. MCP Server

### Setup

```bash
cd mcp-server
uv sync

cat > .env <<EOF
VOCAB_API_URL=https://your-backend-url
VOCAB_API_KEY=<same key as backend>
EOF
```

### Configure your AI assistant

Register the MCP server with your AI assistant's configuration. Point it at `mcp-server/server.py` and pass the following environment variables:

- `VOCAB_API_URL` — base URL of your deployed backend
- `VOCAB_API_KEY` — the API key from your backend `.env`

Once configured, you can ask your assistant: *"Save 'épanouissement' to my vocab deck."*

---

## 3. PWA

### Run locally

Open `pwa/index.html` directly in a browser, or serve with any static file server:

```bash
cd pwa
npx serve .
```

Update the `API_URL` and `API_KEY` constants at the top of `pwa/app.js` to point to your deployed backend.

### Deploy

Host the `pwa/` folder as a static site on any static hosting provider. The site **must** be served over HTTPS for service workers and "Add to Home Screen" to work.

### Install on mobile

- **iOS:** Open in Safari → Share → Add to Home Screen
- **Android:** Open in Chrome → menu → Add to Home Screen / Install App

---

## Security Notes

- The PWA communicates with the backend exclusively through a server-side proxy (`functions/api/`). The API key is never exposed to the browser.
- Store `BACKEND_URL` (and any secrets) as environment variables in your hosting platform — never commit them to version control.
- The backend allows all CORS origins (`*`). Restrict to the PWA's domain after deployment if desired.

---

## Architecture

```
AI Assistant
  │  MCP tool: add_vocabulary
  ▼
MCP Server (local) — POST /vocabulary
  ▼
Backend API — SQLite
  ▼
PWA — GET /vocabulary/due → flashcard study → PATCH /vocabulary/{id}/review
```

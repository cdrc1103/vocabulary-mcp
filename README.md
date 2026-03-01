# Vocabulary App

A full-stack spaced-repetition vocabulary study system. Claude can push words directly into your personal study deck via an MCP tool, and you review them on an installable mobile PWA.

## Components

| Component | Description |
|-----------|-------------|
| `backend/` | FastAPI + SQLite REST API |
| `mcp-server/` | MCP server exposing `add_vocabulary` to Claude Desktop |
| `pwa/` | Installable PWA flashcard study app |

---

## 1. Backend API

### Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Create a .env file
echo "API_KEY=$(openssl rand -hex 32)" > .env
echo "DATABASE_PATH=./vocab.db" >> .env

uvicorn main:app --reload
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

### Deploy to Railway

1. Create a new Railway project and connect this repository.
2. Add a persistent volume mounted at `/data`.
3. Set environment variables:
   - `API_KEY` — generate with `openssl rand -hex 32`
   - `DATABASE_PATH` — `/data/vocab.db`
4. Set the start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Confirm the service is running: `curl https://your-app.railway.app/health`

---

## 2. MCP Server

### Setup

```bash
cd mcp-server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cat > .env <<EOF
VOCAB_API_URL=https://your-app.railway.app
VOCAB_API_KEY=<same key as backend>
EOF
```

### Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "vocabulary": {
      "command": "python",
      "args": ["/absolute/path/to/vocab-app/mcp-server/server.py"],
      "env": {
        "VOCAB_API_URL": "https://your-app.railway.app",
        "VOCAB_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Restart Claude Desktop. You can now ask Claude: *"Save 'épanouissement' to my vocab deck."*

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

Host the `pwa/` folder as a static site on Netlify, Cloudflare Pages, or GitHub Pages. The site **must** be served over HTTPS for service workers and "Add to Home Screen" to work.

### Install on mobile

- **iOS:** Open in Safari → Share → Add to Home Screen
- **Android:** Open in Chrome → menu → Add to Home Screen / Install App

---

## Security Notes

- The API key is visible in `pwa/app.js`. This is acceptable for a personal app. Do not commit `.env` files or hardcode keys in public repositories.
- The backend allows all CORS origins (`*`). Restrict to the PWA's domain after deployment if desired.

---

## Architecture

```
Claude Desktop
  │  MCP tool: add_vocabulary
  ▼
MCP Server (local) — POST /vocabulary
  ▼
Backend API (Railway) — SQLite
  ▼
PWA (Netlify) — GET /vocabulary/due → flashcard study → PATCH /vocabulary/{id}/review
```

# Vocabulary App — Architecture & Implementation Guide

## Overview

A full-stack system that lets Claude push vocabulary words directly into a personal spaced-repetition study app via an MCP tool. The system has three components:

1. **Backend API** — FastAPI server with SQLite, hosted on Railway or Render
2. **MCP Server** — Exposes an `add_vocabulary` tool to Claude Desktop
3. **PWA Frontend** — Installable mobile web app for studying flashcards

---

## Repository Structure

```
vocab-app/
├── backend/
│   ├── main.py               # FastAPI app
│   ├── database.py           # SQLite setup and queries
│   ├── models.py             # Pydantic models
│   ├── auth.py               # API key middleware
│   └── requirements.txt
├── mcp-server/
│   ├── server.py             # MCP server exposing tools
│   └── requirements.txt
├── pwa/
│   ├── index.html            # Main app shell
│   ├── app.js                # App logic
│   ├── style.css             # Styles
│   ├── sw.js                 # Service worker (offline support)
│   └── manifest.json         # PWA manifest
└── README.md
```

---

## 1. Backend API

### Technology
- **Python 3.11+**
- **FastAPI** for the REST API
- **SQLite** via the built-in `sqlite3` module (no ORM needed)
- **Uvicorn** as the ASGI server

### Database Schema

```sql
CREATE TABLE vocabulary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word        TEXT NOT NULL,
    definition  TEXT NOT NULL,
    example     TEXT,
    language    TEXT DEFAULT 'unknown',
    created_at  TEXT DEFAULT (datetime('now')),

    -- Spaced repetition fields (SM-2 algorithm)
    interval        INTEGER DEFAULT 1,     -- days until next review
    ease_factor     REAL DEFAULT 2.5,      -- difficulty multiplier
    repetitions     INTEGER DEFAULT 0,     -- number of successful reviews
    next_review     TEXT DEFAULT (date('now'))  -- ISO date string
);
```

### API Endpoints

#### `POST /vocabulary`
Add a new word.

**Request headers:**
```
X-API-Key: <secret>
```

**Request body:**
```json
{
  "word": "épanouissement",
  "definition": "A blossoming or flourishing; a state of fulfillment",
  "example": "Elle rayonnait d'épanouissement après sa promotion.",
  "language": "French"
}
```

**Response:**
```json
{
  "id": 42,
  "word": "épanouissement",
  "definition": "A blossoming or flourishing; a state of fulfillment",
  "example": "Elle rayonnait d'épanouissement après sa promotion.",
  "language": "French",
  "created_at": "2025-02-27T14:30:00",
  "next_review": "2025-02-27",
  "interval": 1,
  "ease_factor": 2.5,
  "repetitions": 0
}
```

#### `GET /vocabulary`
Retrieve all words. Optional query params: `language`, `limit`, `offset`.

**Response:**
```json
{
  "total": 120,
  "words": [ /* array of vocab objects */ ]
}
```

#### `GET /vocabulary/due`
Get all words due for review today (where `next_review <= today`). Used by the PWA to populate the study session.

#### `PATCH /vocabulary/{id}/review`
Submit a review result. Applies SM-2 to update `interval`, `ease_factor`, `repetitions`, and `next_review`.

**Request body:**
```json
{
  "quality": 4
}
```
`quality` is an integer from 0–5 (SM-2 standard: 0 = complete blackout, 5 = perfect recall).

#### `DELETE /vocabulary/{id}`
Delete a word.

#### `GET /health`
Returns `{"status": "ok"}`. Used by hosting platform to confirm the server is alive.

### SM-2 Algorithm Implementation

Implement inside `database.py` as a pure function:

```python
def apply_sm2(interval: int, ease: float, reps: int, quality: int):
    if quality < 3:
        # Failed: reset
        return 1, ease, 0
    else:
        if reps == 0:
            new_interval = 1
        elif reps == 1:
            new_interval = 6
        else:
            new_interval = round(interval * ease)

        new_ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        new_ease = max(1.3, new_ease)
        return new_interval, new_ease, reps + 1
```

### Authentication

Simple API key via middleware. The key is stored as an environment variable `API_KEY`. All routes except `/health` require the `X-API-Key` header. Return `401` if missing or wrong.

### Environment Variables

```
API_KEY=<generate a long random string, e.g. via `openssl rand -hex 32`>
DATABASE_PATH=./vocab.db   # can use /data/vocab.db on Railway persistent volume
```

### CORS

Allow all origins (`*`) since the PWA will be served from a different domain. If security is a concern, restrict to the PWA's domain after deployment.

### Deployment (Railway)

- Set a persistent volume mounted at `/data` and set `DATABASE_PATH=/data/vocab.db`
- Set `API_KEY` in environment variables
- The start command is: `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## 2. MCP Server

### Technology
- **Python 3.11+**
- **`mcp` SDK** (`pip install mcp`)
- Runs locally on the developer's machine, configured in Claude Desktop

### Tool: `add_vocabulary`

**Description given to Claude:**
> Add a vocabulary word to the personal study app. Use this when the user asks to save a word, or when you've explained a word and want to offer to save it.

**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "word": {
      "type": "string",
      "description": "The word or phrase to save"
    },
    "definition": {
      "type": "string",
      "description": "A clear, concise definition in English"
    },
    "example": {
      "type": "string",
      "description": "An example sentence using the word in context"
    },
    "language": {
      "type": "string",
      "description": "The language of the word (e.g. French, Spanish, English)"
    }
  },
  "required": ["word", "definition"]
}
```

**Behavior:** POST to `{BACKEND_URL}/vocabulary` with the data and the API key. Return a success or failure message to Claude.

### Environment Variables (MCP server)

```
VOCAB_API_URL=https://your-app.railway.app
VOCAB_API_KEY=<same key as backend>
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

---

## 3. PWA Frontend

### Technology
- Vanilla HTML, CSS, JavaScript — no build step, no framework
- Service worker for offline support
- Installable via browser's "Add to Home Screen"

### Views / Screens

The app has three views rendered in a single `index.html` by toggling visibility:

#### View 1: Home
- Word count total
- Count of words due for review today
- Two buttons: **Study Now** and **Browse All Words**

#### View 2: Study (Flashcard mode)
- Shows words due today from `GET /vocabulary/due`
- Flashcard flip animation (CSS `transform: rotateY`)
- Front: the word
- Back: definition + example sentence
- After flipping, show 5 rating buttons labeled: Again (0), Hard (2), Okay (3), Good (4), Easy (5)
- On rating: PATCH `/vocabulary/{id}/review`, advance to next card
- When session is done: show a completion screen with count reviewed

#### View 3: Browse
- Scrollable list of all words grouped by language
- Each word shows: word, definition, next review date
- Tap to expand and see example sentence
- Delete button per word (calls DELETE endpoint, prompts for confirmation)

### Offline Support (Service Worker)

`sw.js` should:
1. On install: cache `index.html`, `app.js`, `style.css`, `manifest.json`
2. On fetch: serve from cache first, fall back to network
3. For API calls (`/vocabulary`): network first, fall back to a cached copy of the last successful response

The service worker does **not** need to support offline writes — if there's no connection, show a friendly message rather than queuing requests.

### PWA Manifest (`manifest.json`)

```json
{
  "name": "Vocab",
  "short_name": "Vocab",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#4f46e5",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

Generate placeholder icons programmatically (a colored square with a letter "V") if no icon assets are provided.

### API Config in Frontend

Set the backend URL and API key as constants at the top of `app.js`:

```javascript
const API_URL = "https://your-app.railway.app";
const API_KEY = "your-api-key-here";

async function apiFetch(path, options = {}) {
  return fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...(options.headers || {})
    }
  });
}
```

> **Note:** The API key is visible in the frontend JS. This is acceptable for a personal app, but document that the key should be treated as semi-secret (not committed to a public repo). Use a `.env`-style approach or a build step if this becomes a concern.

### Hosting the PWA

Host the `pwa/` folder as a static site. Options:
- **Netlify** — drag and drop the folder, free tier
- **Cloudflare Pages** — connect a GitHub repo, free tier
- **GitHub Pages** — free if the repo is public

The PWA must be served over HTTPS for service workers and "Add to Home Screen" to work.

---

## Data Flow Summary

```
User: "Save 'épanouissement' to my vocab deck"
  │
  ▼
Claude Desktop
  │  calls MCP tool: add_vocabulary({ word, definition, example, language })
  ▼
MCP Server (local)
  │  POST /vocabulary with X-API-Key
  ▼
Backend API (Railway)
  │  validates key, inserts row into SQLite
  ▼
Database
  │
  ▼  (later, on phone)
PWA fetches GET /vocabulary/due
  │
  ▼
User studies flashcards, submits ratings
  │
  ▼  PATCH /vocabulary/{id}/review
Backend updates SM-2 fields, schedules next review
```

---

## Implementation Order

Build and test in this order to avoid integration pain:

1. **Backend** — get the API running locally first, test all endpoints with curl or Insomnia
2. **Deploy backend** to Railway, confirm `/health` responds
3. **MCP server** — build and connect to Claude Desktop, test by asking Claude to save a word
4. **PWA** — build the frontend, test in browser pointing at the deployed backend
5. **Deploy PWA** to Netlify or Cloudflare Pages
6. **Install PWA** on phone via "Add to Home Screen"
7. **Service worker** — add last, after core functionality is confirmed working

---

## Dependencies

### Backend (`requirements.txt`)
```
fastapi>=0.110.0
uvicorn>=0.29.0
python-dotenv>=1.0.0
```

### MCP Server (`requirements.txt`)
```
mcp>=1.0.0
httpx>=0.27.0
python-dotenv>=1.0.0
```

### PWA
No dependencies. Pure HTML/CSS/JS.

---

## Notes for Implementation

- Use `python-dotenv` to load `.env` files in both the backend and MCP server during local development
- The SQLite database file should be excluded from version control (add to `.gitignore`)
- The API key should be excluded from version control (use `.env` files, add to `.gitignore`)
- Include a `README.md` with setup instructions covering: how to run locally, how to deploy, how to configure Claude Desktop, and how to install the PWA on iOS and Android

# Deployment Checklist

All three components are built and tested. This doc covers the remaining steps to go live.

---

## Auth architecture

```
claude.ai (phone)
    │  ① OAuth 2.1 (authorize → token → Bearer)
    ▼
MCP server (Railway)  — AS + RS, OAuth 2.1 + DCR
    │  ② X-API-Key: VOCAB_API_KEY
    ▼
Backend API (Railway) — already protected
    │
    ▼
SQLite
```

Claude.ai authenticates via OAuth 2.1 (Authorization Code + PKCE).
The MCP server acts as both Authorization Server and Resource Server.
Dynamic Client Registration (RFC 7591) is enabled.
`MCP_SECRET` serves as the login password and JWT signing key.
`VOCAB_API_KEY` is a separate secret for backend access.

---

## 1. Generate secrets

```bash
openssl rand -hex 32   # → API_KEY    (backend auth + JWT signing)
openssl rand -hex 32   # → MCP_SECRET (MCP server inbound auth)
```

Keep them separate. Pick a memorable passphrase for `PWA_PASSWORD`.

---

## 2. Deploy the backend (Railway)

1. Push this repo to GitHub.
2. New Railway project → **Deploy from GitHub repo** → root directory: `backend/`.
3. Add a **Persistent Volume** mounted at `/data`.
4. Set environment variables:
   ```
   API_KEY=<your-key>
   PWA_PASSWORD=<your-passphrase>
   DATABASE_PATH=/data/vocab.db
   PORT=8000
   ```
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Confirm:
   ```bash
   curl https://<backend>.railway.app/health
   # {"status": "ok"}
   ```

> Railway free tier sleeps after inactivity. Upgrade to Hobby ($5/mo) for always-on — worth it if MCP latency matters.

---

## 3. Deploy the MCP server (Railway — separate service)

1. In the same Railway project, add a second service → root directory: `mcp-server/`.
2. Add a **Persistent Volume** mounted at `/data`.
3. Set environment variables:
   ```
   VOCAB_API_URL=https://<backend>.railway.app
   VOCAB_API_KEY=<your-key>       # MCP server → backend
   MCP_SECRET=<your-mcp-secret>   # OAuth login password + JWT signing key
   ISSUER_URL=https://<mcp>.railway.app
   DATABASE_PATH=/data/oauth.db
   PORT=8080
   ```
4. Start command: `python server.py`
5. Railway will assign a public URL, e.g. `https://<mcp>.railway.app`.
6. Confirm: `curl https://<mcp>.railway.app/health` → `{"status": "ok"}`

---

## 4. Connect an MCP client

Any MCP client that supports OAuth 2.1 (Claude.ai, ChatGPT, etc.) can connect.

1. Add a remote MCP server with URL: `https://<mcp>.railway.app`
2. The client discovers OAuth metadata automatically via
   `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`.
3. You'll be redirected to the login page — enter your `MCP_SECRET` password.
4. After authorization, the client receives tokens and refreshes them automatically.
5. Smoke-test: ask the assistant _"Save the word 'épanouissement'
   (French, means flourishing) to my vocab deck."_
   Confirm it landed:
   ```bash
   curl https://<backend>.railway.app/vocabulary -H "X-API-Key: <your-key>"
   ```

---

## 5. Configure and deploy the PWA

1. Edit `pwa/app.js` line 2:
   ```js
   const API_URL = "https://<backend>.railway.app";
   ```
2. Deploy `pwa/` as a static site:

   | Option | How |
   |--------|-----|
   | **Cloudflare Pages** | Connect GitHub repo, set build output to `pwa/`, free |
   | **Netlify** | Drag-and-drop `pwa/` folder, free |
   | **GitHub Pages** | Enable Pages, set source to `pwa/` subdirectory |

3. Confirm HTTPS (required for service workers and PWA install prompt).

---

## 6. Install the PWA on your phone

**iOS (Safari):** Share → **Add to Home Screen** → Add.

**Android (Chrome):** three-dot menu → **Add to Home screen** (or accept the install banner).

---

## 7. Post-deploy smoke test

```bash
# Backend alive
curl https://<backend>.railway.app/health

# Add a word directly
curl -X POST https://<backend>.railway.app/vocabulary \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"word":"test","definition":"a trial","language":"English"}'

# Confirm it appears
curl https://<backend>.railway.app/vocabulary -H "X-API-Key: <your-key>"
```

Then use Claude on your phone to add a word via the MCP tool, and verify it shows up in the PWA.

---

## Open items / known gaps

| Item | Notes |
|------|-------|
| ~~MCP server HTTP transport + Bearer auth~~ | Replaced with OAuth 2.1 ✓ |
| `pwa/app.js` hardcodes `API_URL` | Railway URL is not a secret; fine to commit |
| SQLite on Railway | Fine for personal scale; migrate to Postgres only if you want managed backups |
| MCP exposes only `add_vocabulary` | Could add `list_vocabulary` / `get_due_words` so Claude can answer "what's due today?" |
| No CI pipeline | Add GitHub Actions to run `pytest` on push |
| PWA offline writes | Currently dropped; could queue to IndexedDB and sync on reconnect |

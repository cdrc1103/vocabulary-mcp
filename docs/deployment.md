# Deployment Checklist

All three components are built and tested. This doc covers the remaining steps to go live.

---

## Auth architecture

```
claude.ai (phone)
    │  ① Authorization: Bearer MCP_SECRET
    ▼
MCP server (Railway)  — rejects strangers at the HTTP layer
    │  ② X-API-Key: VOCAB_API_KEY
    ▼
Backend API (Railway) — already protected
    │
    ▼
SQLite
```

Two separate secrets, two separate trust boundaries.
`MCP_SECRET` and `VOCAB_API_KEY` are different values — if the MCP URL ever leaks,
the backend key is still safe.

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
2. Set environment variables:
   ```
   VOCAB_API_URL=https://<backend>.railway.app
   VOCAB_API_KEY=<your-key>       # MCP server → backend
   MCP_SECRET=<your-mcp-secret>   # inbound auth: claude.ai → MCP server
   PORT=8080
   ```
3. Start command: `python server.py`
4. Railway will assign a public URL, e.g. `https://<mcp>.railway.app`.
5. Confirm: `curl https://<mcp>.railway.app/health` → `{"status": "ok"}`

---

## 4. Connect the MCP server to Claude on your phone

Claude.ai supports remote MCP servers via the **Integrations** panel.

1. Open claude.ai → **Settings** → **Integrations** → **Add integration**.
2. Enter the MCP server URL: `https://<mcp>.railway.app`
3. When prompted for auth, provide `MCP_SECRET` as the Bearer token.
   > claude.ai's exact auth UI evolves — check current docs if the flow differs.
   > The server validates `Authorization: Bearer <MCP_SECRET>` on every request.
4. Smoke-test: ask Claude on your phone _"Save the word 'épanouissement'
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
| ~~MCP server HTTP transport + Bearer auth~~ | Done ✓ |
| `pwa/app.js` hardcodes `API_URL` | Railway URL is not a secret; fine to commit |
| SQLite on Railway | Fine for personal scale; migrate to Postgres only if you want managed backups |
| MCP exposes only `add_vocabulary` | Could add `list_vocabulary` / `get_due_words` so Claude can answer "what's due today?" |
| No CI pipeline | Add GitHub Actions to run `pytest` on push |
| PWA offline writes | Currently dropped; could queue to IndexedDB and sync on reconnect |

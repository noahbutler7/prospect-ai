# ProspectAI

AI-powered LinkedIn prospecting and cold email agent for SDR & BDR teams.

Scans LinkedIn for prospects that match your ICP, infers or looks up their email, and drafts personalized cold emails with Claude — all streamed to a real-time review UI.

## Architecture

```
frontend/           React UI (prospect queue, email editor, ICP config)
  api.js            Fetch wrapper for all backend endpoints
  useProspectScan.js  React hook — SSE stream + prospect state
  prospect-agent.jsx  Full UI component

backend/            FastAPI Python server
  main.py           API routes + SSE streaming engine
  scraper.py        LinkedIn Playwright scraper (stealth, cookie-based auth)
  icp_matcher.py    ICP scoring — title, seniority, buying signals
  enricher.py       Email discovery (Hunter → Apollo → pattern inference)
  drafter.py        Claude-powered personalized email generation
  models.py         Pydantic data models
  config.py         Environment-driven settings
```

## Quick start

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# Fill in ANTHROPIC_API_KEY, LINKEDIN_COOKIES_PATH (or LINKEDIN_LI_AT)

python main.py
# → API running at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

### Frontend

```bash
# Works with any React + Vite project
# Copy frontend/ files into your src/
# Set VITE_API_BASE_URL=http://localhost:8000 in your .env
```

## LinkedIn session setup

The scraper uses your real LinkedIn session to search profiles — no API key needed.

1. Log into [linkedin.com](https://linkedin.com) in Chrome
2. Install the [Cookie-Editor](https://cookie-editor.com/) extension
3. Click **Export → JSON**
4. Save the file and set `LINKEDIN_COOKIES_PATH=linkedin_cookies.json` in `.env`

> ⚠️ Never commit `linkedin_cookies.json` or `.env` — both are in `.gitignore`.

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scan/start` | Start a scan job |
| `GET`  | `/api/scan/{id}/stream` | SSE stream of prospects |
| `POST` | `/api/scan/{id}/stop` | Stop a running scan |
| `GET`  | `/api/prospects` | List all prospects |
| `PATCH`| `/api/prospects/{id}` | Update status / draft |
| `POST` | `/api/prospects/{id}/send` | Send approved email |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Email enrichment

Enrichment runs in a cascade — stops at first success:

1. **Hunter.io** (set `HUNTER_API_KEY`) — verified email lookup
2. **Apollo.io** (set `APOLLO_API_KEY`) — people search
3. **Pattern inference** — `first.last@domain.com` and 7 other common formats
4. Optional SMTP verification (set `SMTP_VERIFY=true`) — slow but accurate

## Roadmap

- [ ] Postgres + Redis for persistent state and job queues
- [ ] Lusha / ZoomInfo integration
- [ ] Multi-user auth (each SDR has their own accounts + ICP)
- [ ] Email reply tracking (SendGrid webhooks)
- [ ] Sequence support (follow-up threads)
- [ ] LinkedIn Sales Navigator API option

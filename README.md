# Axiom

Axiom is a self-hostable FastAPI gateway and React chat workspace. It streams chat
completions through Groq, Gemini, and OpenRouter, with provider/key/model
failover and continuation after an upstream stream failure. The browser client
keeps conversations and non-secret preferences in local storage. Gateway and
BYOK credentials remain in tab memory.

## Current features

- Streaming chat, provider failover, key rotation, cooldowns, and continuation
  prompts with word-boundary seam repair.
- Optional web search through Tavily, image input, PDF and office-document text
  extraction, and a lexical SQLite full-text index scoped to the authenticated
  client.
- Configurable routing preference, provider/model selection, parallel provider
  comparison, and a tool-using agent with bounded Python evaluation and MCP
  tools.
- OpenAI-compatible `POST /v1/chat/completions`.
- SQLite-backed daily quotas, API-key records, shares, encrypted-payload vault
  storage, document index, and routing latency observations.
- Prometheus-format metrics, structured event logs, health probes, and
  admin-protected provider diagnostics.
- Browser speech input/output, hands-free turn-taking, citation previews,
  artifact previews, and shareable chat links.

Failover is best-effort, not a guarantee of uninterrupted output. A continuation
model may rephrase or repeat text. Routing cost and quality modes use configured
provider rankings, not live price or benchmark data. Document retrieval uses
SQLite FTS; it is not embedding-based RAG. Scanned-PDF OCR is not implemented.
The default model catalog is configured in code/environment; live upstream model
lookup is available to admins, but model availability still depends on the
provider account and has not been verified here with live credentials.

## Run locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add provider keys and configure AXIOM_API_KEY / ADMIN_TOKEN as appropriate.
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Set `VITE_API_URL` to the backend origin. If gateway authentication is enabled,
enter the gateway key in Settings or set `VITE_AXIOM_API_KEY` for a
single-user/local setup. Do not expose a shared gateway key in a public frontend.

## Security and deployment

- Set `ENVIRONMENT=production` or `AUTH_REQUIRED=true` and configure
  `AXIOM_API_KEY`. An admin can mint per-user keys at `/api/admin/keys` using
  `X-Admin-Token`.
- Use individual issued keys for account-level isolation and encrypted sync
  across devices. A shared `AXIOM_API_KEY` is scoped by client address.
- Set a high-entropy `ADMIN_TOKEN`; chaos controls, provider status/configuration,
  live model lookup, and `/metrics` are unavailable without it.
- Configure `CORS_ORIGINS` to the exact frontend origins. Set `TRUST_PROXY=1`
  only behind a trusted proxy that overwrites `X-Forwarded-For`.
- MCP servers must use HTTPS and resolve to public addresses. Add exact hostnames
  to `MCP_ALLOWED_HOSTS` only when private or plain-HTTP MCP endpoints are
  intentionally trusted.
- SQLite data is stored under `backend/data` unless `AXIOM_DATA_DIR` is set.
  Back it up and restrict filesystem access. Vault payloads are opaque to the
  server; encryption and key management must be performed by the client.
- Rate-limit counters are in-process; daily quotas are persisted in SQLite.
  For multi-worker deployments, use a shared rate-limit store or place a
  rate-limiting proxy in front of Axiom.

See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md)
for component-level details.

## API overview

| Method | Endpoint | Access |
| --- | --- | --- |
| `POST` | `/api/chat/stream` | Authenticated; SSE |
| `POST` | `/api/chat/compare` | Authenticated; parallel SSE comparison |
| `POST` | `/v1/chat/completions` | Authenticated; OpenAI-compatible |
| `GET` | `/v1/models` | Authenticated OpenAI-compatible model catalog |
| `POST` | `/api/title` | Authenticated |
| `POST` | `/api/extract` | Authenticated |
| `POST` / `GET` | `/api/share`, `/api/share/{id}` | Create authenticated; read public share |
| `POST` / `GET` | `/api/vault`, `/api/vault/{id}` | Authenticated and owner-scoped |
| `GET` | `/api/models` | Authenticated model catalog |
| `GET` | `/api/health` | Public liveness |
| `GET` | `/api/status`, `/api/stats`, `/api/config-check`, `/metrics` | Admin token |
| `POST` | `/api/debug/*` | Admin token; disabled if unset |
| `GET` | `/api/models/{provider}` | Admin token; live upstream lookup |

## Tests

```bash
cd backend
python -m pytest tests -q
cd ../frontend
npm test
npm run lint
npm run build
```

CI runs the mocked/unit backend suite and frontend tests, lint, and production
build without requiring live provider credentials.

# Axiom Backend

FastAPI gateway for streaming chat, provider/key/model failover, and local
workspace services. See the repository [README](../README.md) for setup and
deployment guidance.

## Configuration

Copy `.env.example` to `.env` and configure provider keys. For deployment, set
`ENVIRONMENT=production` (or `AUTH_REQUIRED=true`), `AXIOM_API_KEY`, and a
high-entropy `ADMIN_TOKEN`. Keep admin and provider credentials on the backend;
never bundle them into a public frontend.
Use issued per-user keys for account-level data isolation and encrypted sync
across devices; the shared gateway key is scoped to the caller's client address.

`CORS_ORIGINS` controls browser origins. `TRUST_PROXY=1` is appropriate only
behind a trusted proxy that replaces forwarding headers. `MCP_ALLOWED_HOSTS`
is an explicit allowlist for MCP hosts that may use HTTP or resolve to private
addresses. Other MCP servers must use HTTPS and resolve only to public IPs.

SQLite persists quotas, issued API-key hashes, shared chats, opaque encrypted
vault payloads, user-scoped uploaded-document text/FTS, and latency observations.
Select its directory with `AXIOM_DATA_DIR`.

## API

- `POST /api/chat/stream`: authenticated streaming chat; optional web search,
  vision, tools, provider/model selection, and route preference.
- `POST /api/chat/compare`: authenticated concurrent multi-provider SSE compare.
- `POST /v1/chat/completions`: OpenAI-compatible completion API.
- `GET /v1/models`: authenticated OpenAI-compatible model catalog.
- `POST /api/title`: short chat title generation.
- `POST /api/extract`: upload extraction for text, PDF, DOCX, XLSX, and PPTX.
- `POST /api/share` and `GET /api/share/{id}`: create and read shareable chats.
- `POST /api/vault` and `GET /api/vault/{id}`: store and retrieve opaque
  owner-scoped ciphertext.
- `GET /api/models`: authenticated configured model catalog.
- `GET /api/health`: public liveness endpoint.
- `GET /api/status`, `/api/stats`, `/api/config-check`, `/api/models/{provider}`,
  and `/metrics`: admin-token protected diagnostics.
- `POST /api/debug/*`: admin-token protected chaos-testing endpoints.
- `POST`, `GET`, and `DELETE /api/admin/keys`: mint, list, and revoke user API keys.

The backend implements lexical SQLite FTS, not embedding-based retrieval. It
does not perform scanned-PDF OCR. The built-in Python tool intentionally
supports only a bounded subset of Python syntax; it does not execute arbitrary
Python code or permit imports, filesystem access, or network access.

## Testing

```bash
python -m pytest tests -q
```

The unit/mocked tests do not call live provider APIs and need no provider keys.
The scripts `test_failover.py` and `test_midstream.py` are optional manual
integration checks and require a running backend, configured live provider
keys, and an admin token.

# Axiom Frontend

React 19 and Vite chat client for the Axiom gateway. Messages and non-secret
preferences are stored in browser `localStorage`; gateway/BYOK credentials remain
in tab memory. Creating a share link stores a copy on the backend. The client
supports streaming SSE, provider/model selection, routing
preferences, compare mode, web search, document/image attachments, browser speech
input/output, MCP configuration, and sandboxed HTML artifact previews.

## Development

```bash
npm ci
cp .env.example .env.local
npm run dev
```

Configure `VITE_API_URL` in `.env.local` if the backend is not at
`http://127.0.0.1:8000`. For a local single-user setup, `VITE_AXIOM_API_KEY` can
provide the gateway key. Do not ship a shared backend key in a public frontend.
Admin-only cockpit actions additionally need `VITE_ADMIN_TOKEN`; only provide
that to a trusted local/admin client.

## Validation

```bash
npm test
npm run lint
npm run build
```

Keyboard shortcuts: `⌘K` / `Ctrl+K` focuses chat search, `⌘B` / `Ctrl+B`
toggles the sidebar, `⌘N` / `Ctrl+N` starts a new chat, and `Esc` closes open
menus and dialogs.

# Axiom Frontend Client 🌐

The modern, ultra-responsive conversational interface for **Axiom**. Crafted with **React 19**, **Vite 8**, and styled with custom CSS inspired by Claude and ChatGPT desktop workspaces.

---

## ✨ Features

- **Ultra-Responsive Token Streaming**: Native Server-Sent Events (SSE) reader with instantaneous token rendering and auto-scroll tracking.
- **Failover Status Telemetry**: Live badges and announcements when an answer is salvaged by a secondary provider.
- **Collapsible Reasoning Accordions**: Full parsing for `<think>...</think>` Chain-of-Thought (CoT) tokens (e.g. DeepSeek-R1, Gemini Thinking Experimental).
- **Perplexity-Style Source Drawers**: Interactive expandable citations for grounded web search results with domain previews.
- **Multimodal Upload Capsule**: Drag-and-drop and clipboard paste for images (auto-scaled via HTML5 Canvas) and documents (PDF, code, text).
- **Voice Intelligence**: Bi-directional Web Speech API integration with real-time Speech-to-Text (STT) and scored neural Text-to-Speech (TTS).
- **Chaos Engineering Cockpit**: Modal for real-time telemetry, node state visualization, and simulated failure injection.
- **Local Data Persistence**: Zero-cloud privacy with `localStorage` persistence, chat pinning, chronological categorization, Markdown export, and JSON backup/restore.

---

## 🛠 Technology Stack

- **Framework**: [React 19](https://react.dev/)
- **Bundler**: [Vite 8](https://vitejs.dev/) with Rolldown / Oxc
- **Typography**: `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`
- **Markdown & Syntax**: `react-markdown`, `remark-gfm`, `rehype-highlight`, `highlight.js`
- **Iconography**: `lucide-react`

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Start Development Server
```bash
npm run dev
```
The application will launch at `http://localhost:5173`. Ensure the backend server is running concurrently at `http://127.0.0.1:8000`.

### 3. Production Build
```bash
npm run build
npm run preview
```

---

## ⌨️ Global Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `⌘K` / `Ctrl+K` | Open chat search & spotlight |
| `⌘B` / `Ctrl+B` | Toggle collapsible sidebar |
| `⌘N` / `Ctrl+N` | Start a new chat session |
| `Enter` | Send message |
| `Shift + Enter` | New line in composer |
| `Esc` | Dismiss modals, dropdowns, and search |

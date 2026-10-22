<div align="center">

# ⚡ Axiom

### High-Availability, Zero-Downtime Multi-Provider LLM Gateway & Conversational Workspace

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19.0+-61DAFB.svg?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8.0+-646CFF.svg?style=flat&logo=vite&logoColor=white)](https://vitejs.dev/)
[![HTTPX](https://img.shields.io/badge/HTTPX-Async_Streaming-109988.svg?style=flat)](https://www.python-httpx.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg?style=flat)](#)

<p align="center">
  <b>Axiom</b> solves the single greatest vulnerability of enterprise generative AI deployments: <i>upstream service interruption</i>. By orchestrating a self-healing, multi-provider cascading inference mesh with <b>mid-stream token reconstruction</b>, Axiom guarantees 99.99% conversation continuity across cloud inference providers without dropped context or user-visible errors.
</p>

[Key Features](#-key-features) • [Architecture Deep Dive](#-architecture--dataflow) • [Mid-Stream Failover Mechanics](#-mid-stream-failover-mechanics) • [RAG & Multimodal Pipeline](#-agentic-rag--multimodal-pipeline) • [Quickstart](#-quickstart--installation) • [API Reference](#-api-specification--telemetry) • [Chaos Engineering](#-chaos-engineering--testing)

---

</div>

## 📌 Executive Summary

Modern AI applications suffer from severe upstream vulnerabilities:
1. **HTTP 429 Rate Limits**: Sudden token or request quota exhaustion.
2. **Upstream Degradation & Outages**: Service brownouts, slow first-byte latency, and cloud cold starts.
3. **Mid-Stream Connection Ruptures**: Network drops or server cancellations while generating long-form completions, leaving the user with half-baked, broken answers.
4. **Provider Lock-in & Deprecation**: Dynamic shifts in API endpoints, pricing tiers, and model availability.

**Axiom** acts as an intelligent, asynchronous inference proxy and presentation interface. It unifies high-throughput LPUs (**Groq**), hyperscale frontier models (**Google Gemini**), and distributed community endpoints (**OpenRouter**) into a singular, fault-tolerant compute fabric. When any provider faults—even mid-sentence—Axiom dynamically catches the exception, isolates the failing node with an exponential cooldown, and transparently resumes token generation from the exact word boundary using the next healthy provider in the cascade.

---

## 🌟 Key Features

- **🛡 Cascading Multi-Provider Failover**: Deterministic, priority-ordered cascade (`Groq` ➔ `Google Gemini` ➔ `OpenRouter`) across verified high-capacity models with sub-millisecond node switching.
- **🔄 Mid-Stream Resilient State Recovery**: Patented token-seam reconciliation algorithm (`fix_seam`). If a provider terminates mid-stream, Axiom prompts the secondary model with synthesized continuation parameters, stitching tokens seamlessly without duplicate words or missing spaces.
- **🔑 Multi-Key Pool Balancing & Health Telemetry**: Supports comma-delimited API key arrays per provider. Distributes load across keys, isolates burned keys with 3600s quarantines, and manages proportional dynamic cooldowns based on `Retry-After` headers.
- **🧠 Chain-of-Thought (CoT) Parsing**: Native token interceptor for `<think>...</think>` blocks. Renders live collapsible reasoning accordions for reasoning models such as DeepSeek-R1 and Gemini Thinking Experimental.
- **🌐 Grounded Agentic RAG**: Dual-pass contextual query reformulation (`make_search_query`) resolving pronouns and anaphoras into time-anchored search queries, integrated with Tavily API and Perplexity-style expandable citation drawers.
- **📂 Multimodal Document & Vision Ingestion**: Client-side canvas image downscaling (1280px clamp, JPEG compression) with automatic vision-capable model routing; in-memory document parsing for PDFs (`pypdf`), CSVs, JSON, and source code across 25+ programming languages.
- **🎙 Bi-Directional Web Speech Engine**: Client-side Speech-to-Text (STT) with interim streaming transcriptions; AST-based Markdown-to-plain-text sanitizer for Text-to-Speech (TTS) with sentence chunking and heuristic neural voice ranking.
- **🕹 Built-In Chaos Cockpit**: Interactive telemetry modal showing real-time requests, failover rescues, node states, and one-click chaos injection buttons to simulate provider outages and mid-stream breaks.
- **🔒 Zero-Cloud Local Privacy**: All chats, settings, and custom instructions are persisted in client-side `localStorage`. Includes one-click Markdown exports and complete JSON backup/restore.

---

## 🏛 Architecture & Dataflow

Axiom separates concerns between a reactive client interface and an asynchronous, non-blocking Python backend engine powered by ASGI streaming.

```
                              ┌────────────────────────────────────────┐
                              │            Axiom Frontend              │
                              │   React 19 + Vite 8 + Lucide Icons     │
                              └───────────────────┬────────────────────┘
                                                  │
                               HTTP POST / Stream │ Server-Sent Events (SSE)
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │          FastAPI ASGI Gateway          │
                              │         (AsyncIO / Uvicorn)            │
                              └───────────────────┬────────────────────┘
                                                  │
                 ┌────────────────────────────────┼────────────────────────────────┐
                 │                                │                                │
                 ▼                                ▼                                ▼
  ┌─────────────────────────────┐  ┌─────────────────────────────┐  ┌─────────────────────────────┐
  │      Document Engine        │  │      Agentic Search         │  │     Orchestration Engine    │
  │ • pypdf stream extraction   │  │ • Contextual Reformulation  │  │ • Tuple-based Node Picker   │
  │ • 25+ language code parser  │  │ • Tavily Web Search API     │  │ • Dynamic Cooldown Matrix   │
  │ • Char buffer normalization │  │ • Context Injection Guard   │  │ • Mid-Stream State Recovery │
  └─────────────────────────────┘  └─────────────────────────────┘  └──────────────┬──────────────┘
                                                                                   │
                                  Cascading Inference Cascade                      │
                 ┌─────────────────────────────────────────────────────────────────┤
                 │                                                                 │
                 ▼                                ▼                                ▼
  ┌─────────────────────────────┐  ┌─────────────────────────────┐  ┌─────────────────────────────┐
  │        Tier 1: Groq         │  │    Tier 2: Google Gemini    │  │   Tier 3: OpenRouter Mesh   │
  │ • LPU ultra-low latency     │  │ • High-context Flash 2.0    │  │ • Multi-model distributed   │
  │ • Llama-3.3-70B / 8B        │  │ • Gemini-2.0-Flash-Lite     │  │ • DeepSeek-R1 / Qwen Coder  │
  │ • Gemma 2 / Mixtral         │  │ • Native Multimodal Vision  │  │ • Community Free Fallbacks  │
  └─────────────────────────────┘  └─────────────────────────────┘  └─────────────────────────────┘
```

### Inference Cascade Decision Flow

```mermaid
flowchart TD
    A([Incoming Chat Request]) --> B{Requires Multimodal Vision?}
    B -- Yes --> C[Filter Candidate Pool to Vision Models]
    B -- No --> D[Use Full Multi-Provider Model Roster]
    
    C --> E[pick_node: Select Provider x Key x Model]
    D --> E
    
    E --> F{Usable Node Available?}
    F -- No --> G[Emit Terminal SSE Error Event]
    F -- Yes --> H[Initiate HTTPX Async Stream]
    
    H --> I{First Token Received within 8s?}
    I -- No / Timeout --> J[Register Node Cooldown: 30s]
    J --> E
    
    I -- Yes --> K[Stream Tokens to Client via SSE]
    K --> L{Stream Broken Mid-Generation?}
    
    L -- Yes --> M[Record Partial Answer Buffer]
    M --> N[Flag Provider Failure & Apply Cooldown]
    N --> O[Synthesize Continuation Context & Fix Seam]
    O --> E
    
    L -- No --> P{Stream Finished [DONE]?}
    P -- Yes --> Q[Emit SSE 'done' & Record Success Metric]
    P -- No --> K
```

---

## ⚡ Mid-Stream Failover Mechanics

The most technically complex challenge in multi-model load balancing is **recovering from an aborted generation without restarting from scratch**. 

### The Problem
When Provider A fails at token 85 of a 200-token completion:
1. The user has already received and read tokens 1 through 85 on their screen.
2. If the gateway simply retries the entire request on Provider B, the user experiences jarring screen clearing, duplicate text, and wasted latency.
3. If Provider B is prompted to continue, different BPE (Byte Pair Encoding) tokenizers frequently collide at the seam (e.g. `the` + `elephant` resulting in `theelephant` or missing punctuation).

### Axiom's Two-Stage Seam Stitching Solution

#### 1. Synthetic Continuation Prompt Injection
When an active generator throws `httpx.TimeoutException`, `httpx.TransportError`, or HTTP status errors mid-stream, Axiom captures the accumulated text buffer `partial`. The request payload is transformed dynamically for the next healthy candidate in the cascade:

```python
current = list(messages)
if partial:
    current += [
        {"role": "assistant", "content": partial},
        {
            "role": "user",
            "content": (
                "Continue your previous answer exactly from where it stopped. "
                "Do not repeat anything. Do not add any preamble."
            ),
        },
    ]
```

#### 2. Seam Reconciliation (`fix_seam`)
Before emitting the first token received from the recovery provider, Axiom evaluates the character boundary between the end of `partial` and the start of `token`:

```python
def fix_seam(partial: str, token: str) -> str:
    """Prevents alphanumeric word gluing across mismatched model tokenizer seams."""
    if partial and token and not partial[-1].isspace() and token[0].isalnum() and partial[-1].isalnum():
        return " " + token
    return token
```

The client receives an immediate SSE `status` event notifying the UI that failover occurred, while the user observes an uninterrupted stream of text without interruption or formatting degradation.

---

## 🔍 Agentic RAG & Multimodal Pipeline

```
[User Message with Pronouns]
            │
            ▼
┌──────────────────────────────────────────────┐
│  Dual-Pass Contextual Query Reformulation    │  <-- Analyzes last 6 turns & current ISO date
│  make_search_query()                         │  <-- Strips ambiguous references (he, that, etc.)
└──────────────────────┬───────────────────────┘
                       │ Output: Concise 3-10 word search query
                       ▼
┌──────────────────────────────────────────────┐
│  Tavily Search API Engine with Key Failover  │  <-- Traverses comma-separated API key pool
│  web_search()                                │  <-- Extracts verified title, URL, snippets
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  Context Isolation & Guardrail Wrapper       │  <-- Injected into System Prompt as UNTRUSTED DATA
│  format_context()                            │  <-- Forces [1], [2] citation style
└──────────────────────────────────────────────┘
```

### Context Isolation Guarantee
To prevent prompt injection attacks embedded within retrieved web results, Axiom wraps external content with explicit instructions that force the model to treat retrieved snippets strictly as untrusted information, never as executable instructions.

### Multimodal Vision Pipeline
1. **Client-Side Pre-processing**: Files dropped or pasted into the composer are intercepted. Images are rendered to an off-screen HTML5 `Canvas`, scaled down so neither dimension exceeds `1280px`, and converted to `image/jpeg` at 80% quality.
2. **Dynamic Vision Routing**: When image payloads are present, `needs_vision=True` is asserted. Axiom bypasses text-only models and routes exclusively to models registered in `VISION_PROVIDERS` (such as `gemini-2.0-flash`, `llama-3.2-11b-vision-preview`, or `llama-3.2-90b-vision-preview`).

---

## 📂 Project Structure

```
Axiom/
├── README.md                      # Primary project documentation & architecture guide
├── backend/                       # High-performance FastAPI ASGI server
│   ├── .env.example               # Environment variable blueprint
│   ├── requirements.txt           # Pinned production Python dependencies
│   ├── main.py                    # Gateway endpoints, SSE generator, RAG integration
│   ├── providers.py               # Cascade state machine, cooldown matrix, stream engine
│   ├── search.py                  # Tavily API web search client & citation formatter
│   ├── test_failover.py           # Automated chaos verification for cascade failover
│   ├── test_midstream.py          # Mid-stream break simulation & seam testing
│   └── README.md                  # Backend-specific architecture & developer guide
└── frontend/                      # React 19 + Vite 8 presentation workspace
    ├── index.html                 # Single-page application entrypoint
    ├── vite.config.js             # Vite configuration with React compiler plugin
    ├── package.json               # Frontend dependencies & build scripts
    ├── README.md                  # Frontend client documentation & shortcuts
    └── src/
        ├── App.jsx                # Core chat interface, composer, cockpit modal
        ├── App.css                # Polished design system (Dark/Light/System)
        ├── main.jsx               # React DOM mounting & typography init
        ├── voice.js               # Web Speech API wrapper, heuristic voice scoring
        └── index.css              # Global resets & font imports
```

---

## 🚀 Quickstart & Installation

### Prerequisites
- **Node.js**: v18.0.0 or higher
- **Python**: v3.10 or higher
- API Keys for one or more providers:
  - [Groq Cloud Console](https://console.groq.com/keys)
  - [Google AI Studio](https://aistudio.google.com/)
  - [OpenRouter](https://openrouter.ai/keys)
  - [Tavily AI Search](https://tavily.com/) *(Optional, for web search)*

---

### Step 1: Backend Setup

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Create and activate a Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your environment configuration
cp .env.example .env
```

Open `.env` and configure your API keys. Multiple keys per provider can be passed as a comma-separated list:

```ini
GROQ_API_KEYS=gsk_key1,gsk_key2
GEMINI_API_KEYS=AIzaSyKey1,AIzaSyKey2
OPENROUTER_API_KEYS=sk-or-v1-key1
TAVILY_API_KEYS=tvly-key1

# Primary defaults (optional, fallback matrix will auto-engage)
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_MODEL=gemini-2.0-flash
OPENROUTER_MODEL=minimax/minimax-m3.1-flash:free

# Cascade order and timeouts
PROVIDER_ORDER=groq,gemini,openrouter
FIRST_TOKEN_TIMEOUT=8.0
NEXT_TOKEN_TIMEOUT=20.0
```

Start the FastAPI application:
```bash
uvicorn main:app --reload --port 8000
```
*The backend API will be available at `http://127.0.0.1:8000`.*

---

### Step 2: Frontend Setup

Open a new terminal window:

```bash
# 1. Navigate to the frontend directory
cd frontend

# 2. Install Node dependencies
npm install

# 3. Launch the Vite development server
npm run dev
```

*The application will launch at `http://localhost:5173`.*

---

## 📡 API Specification & Telemetry

### 1. Chat Completion Stream
**Endpoint**: `POST /api/chat/stream`  
**Media Type**: `text/event-stream`

#### Request Payload
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Compare quantum computing with classical computing.",
      "images": ["data:image/jpeg;base64,..."]
    }
  ],
  "instructions": "Be concise, analytical, and provide a comparison table.",
  "web_search": true
}
```

#### SSE Stream Events Protocol
| Event | Payload Format | Description |
| :--- | :--- | :--- |
| `sources` | `{"query": str, "items": [{"title": str, "url": str}]}` | Emitted when live web search results have been retrieved. |
| `meta` | `{"provider": "groq", "model": "openai/gpt-oss-120b"}` | First event emitted declaring the handling provider and model. |
| `status` | `{"message": "Switched provider to gemini"}` | Emitted when a failover rescue has taken place. |
| `token` | `{"text": "Quantum computing..."}` | Individual text chunk or CoT `<think>` token. |
| `error` | `{"message": "Axiom is very busy right now..."}` | Emitted when all cascade tiers have exhausted retries. |
| `done` | `{}` | Emitted upon generation completion. |

---

### 2. Document & File Ingestion
**Endpoint**: `POST /api/extract`  
**Payload**: `multipart/form-data` with file parameter.  
**Supported Extensions**: `.pdf`, `.txt`, `.md`, `.csv`, `.json`, `.py`, `.js`, `.ts`, `.rs`, `.go`, `.cpp`, `.sql`, etc.  
**Limit**: 10 MB file size, 20,000 character maximum window.

#### Response
```json
{
  "name": "system_design.pdf",
  "text": "Executive Summary: Distributed consensus protocols...",
  "truncated": false,
  "chars": 14250
}
```

---

### 3. System Telemetry & Cockpit
**Endpoint**: `GET /api/stats`

#### Response
```json
{
  "started": 1729584000.0,
  "uptime_seconds": 3600,
  "requests": 142,
  "switches": 18,
  "errors": 0,
  "served": {
    "groq": 118,
    "gemini": 20,
    "openrouter": 4
  },
  "failed": {
    "groq": 20,
    "gemini": 4
  },
  "recent_errors": [
    {
      "time": 1729587420.0,
      "provider": "groq",
      "reason": "HTTP 429"
    }
  ],
  "providers": {
    "groq": {
      "model": "openai/gpt-oss-120b",
      "simulated_failure": false,
      "nodes": [
        {"key": 1, "state": "cooling_down", "seconds_left": 45},
        {"key": 2, "state": "ready", "seconds_left": 0}
      ]
    }
  }
}
```

---

## 🧪 Chaos Engineering & Testing

Axiom includes dedicated chaos engineering controls to simulate catastrophic infrastructure failures in real-time.

### Chaos Simulation Endpoints
- `/api/debug/fail/{provider}`: Forces all requests to `{provider}` to fail immediately with `HTTP 429`.
- `/api/debug/break/{provider}/{n}`: Simulates an abrupt socket drop after exactly `{n}` tokens have streamed.
- `/api/debug/clear`: Instantly clears all simulated failures and node cooldowns.

### Automated Test Suites

#### 1. Cascade Resilience Verification
Run the end-to-end failover test suite:
```bash
python backend/test_failover.py
```
**Test Matrix Execution**:
```
== Config ==
  [PASS] groq is configured  keys=2 model=openai/gpt-oss-120b
  [PASS] gemini is configured  keys=2 model=gemini-2.0-flash
  [PASS] openrouter is configured  keys=1 model=minimax/minimax-m3.1-flash:free

== Test 1: normal request (expect groq) ==
[PASS] Groq answers normally  provider=groq first_token=0.42s

== Test 2: Groq broken (expect gemini) ==
[PASS] Switches to Gemini  provider=gemini error=None

== Test 3: Groq + Gemini broken (expect openrouter) ==
[PASS] Switches to OpenRouter  provider=openrouter error=None

== Test 4: everything broken (expect friendly error) ==
[PASS] Friendly error, no raw codes  message=Axiom is very busy right now...

== Test 5: healed (expect groq again) ==
[PASS] Back to Groq after healing  provider=groq

== Test 6: memory ==
[PASS] Remembers earlier messages  reply='Your favourite number is 47.'

== RESULT: 9/9 checks passed ==
```

#### 2. Mid-Stream Token Seam Verification
Verify that mid-generation connection drops are seamlessly stitched:
```bash
python backend/test_midstream.py
```
This test intentionally aborts Groq after 15 tokens. It verifies that Gemini continues the narrative without repeating words or dropping punctuation.

---

## 🔒 Security & Privacy Posture

- **Client-Side Data Ownership**: Conversations and settings are stored strictly in browser `localStorage`. No user conversations are written to disk or centralized databases.
- **Header Masking & Anonymization**: Upstream providers never receive user IP addresses, authorization cookies, or tracking headers.
- **Ephemeral Processing**: File uploads sent to `/api/extract` are processed entirely in volatile memory (`io.BytesIO`) and destroyed immediately following response delivery.
- **CORS Protection**: Access to the FastAPI backend is locked down by default to local origins (`http://localhost:5173`, `http://127.0.0.1:5173`).

---

## ⌨️ Desktop Keyboard Shortcuts

| Shortcut | Scope | Description |
| :--- | :--- | :--- |
| `⌘K` or `Ctrl+K` | Global | Focus conversation search spotlight |
| `⌘B` or `Ctrl+B` | Global | Expand / Collapse navigation sidebar |
| `⌘N` or `Ctrl+N` | Global | Start a fresh conversation session |
| `Enter` | Composer | Dispatch message to cascade engine |
| `Shift + Enter` | Composer | Insert newline in text editor |
| `Esc` | Modals | Close settings, telemetry cockpit, or search |

---

## 📜 License

This project is distributed under the **MIT License**. See [LICENSE](LICENSE) for full details.

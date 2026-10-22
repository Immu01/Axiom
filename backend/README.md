# Axiom Backend Engine ⚡

The high-performance, asynchronous orchestration core powering **Axiom**. Built on **FastAPI**, **HTTPX**, and **AsyncIO**, this engine provides resilient, multi-provider cascading failover, mid-stream token continuation, live web search retrieval (RAG), and multimodal document extraction.

---

## 🏛 Architecture Overview

- **Asynchronous Non-Blocking I/O**: High-concurrency token streaming using FastAPI and HTTPX async connection pooling.
- **Cascading Failover Pipeline**: Seamless routing across Groq, Google Gemini, and OpenRouter with automatic provider fallback upon HTTP errors, timeouts, or rate limits (HTTP 429).
- **Mid-Stream Resilient State Recovery**: Recovers interrupted token streams mid-sentence without losing earlier progress or creating token seams.
- **Temporal Query Reformulation & RAG**: Automatically turns conversational messages into standalone search queries and queries Tavily API with citation generation.
- **Multimodal Document Processing**: In-memory parsing of PDFs (`pypdf`), source code files across 25+ formats, CSV, and text.

---

## 🚀 Quick Start

### 1. Environment Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and provide your API keys:
```bash
cp .env.example .env
```
Edit `.env` with your keys for Groq, Gemini, OpenRouter, and Tavily. Multiple comma-separated keys per provider are supported for key-level pool rotation.

### 3. Launch Development Server
```bash
uvicorn main:app --reload --port 8000
```
The backend will be live at `http://127.0.0.1:8000`.

---

## 📡 API Specification

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/chat/stream` | Server-Sent Events (SSE) chat stream with auto-failover and optional RAG |
| `POST` | `/api/extract` | Multipart upload for text/PDF extraction (`pypdf`) |
| `POST` | `/api/title` | Automated semantic title generator for chat threads |
| `GET` | `/api/stats` | Real-time telemetry, provider uptime, served/failed metrics |
| `GET` | `/api/status` | Current active model, key states, and cooldown countdowns |
| `GET` | `/api/models/{provider}` | Query available upstream models for a provider |
| `GET` | `/api/debug/fail/{provider}` | Chaos testing: simulate provider outage |
| `GET` | `/api/debug/break/{provider}/{n}` | Chaos testing: simulate mid-stream break after *n* tokens |
| `GET` | `/api/debug/clear` | Reset all simulated failures and cooldown states |

---

## 🧪 Chaos & Automated Testing

Axiom includes automated test scripts to verify cascading failover and mid-stream recovery:

```bash
# Verify multi-provider fallback cascade
python test_failover.py

# Verify midstream interruption token stitching
python test_midstream.py
```

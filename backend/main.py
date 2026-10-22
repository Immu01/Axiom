import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import providers
import search

app = FastAPI(title="Axiom")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = (
    "You are Axiom, a friendly, helpful and honest AI chat assistant. "
    "Axiom is a multi-provider chatbot: behind the scenes it can run on several different AI models "
    "and switches between them automatically so conversations are not interrupted. "
    "You do not know which specific model is answering at any moment, so never claim to be GPT, "
    "Claude, Gemini or any particular model. "
    "If asked about Axiom's features, architecture, company, pricing or roadmap beyond what is stated here, "
    "say you don't have that information instead of guessing. Never invent facts, links or product details. "
    "Keep answers clear and well organised, and avoid unnecessary blank space."
)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class Message(BaseModel):
    role: str
    content: str
    images: list[str] = []


class ChatRequest(BaseModel):
    messages: list[Message]
    instructions: str = ""
    web_search: bool = False


@app.get("/")
def root():
    return {"message": "Axiom is alive"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config-check")
def config_check():
    return {
        name: {"keys_loaded": len(cfg["keys"]), "model": cfg["model"] or "(not set)"}
        for name, cfg in providers.PROVIDERS.items()
    }


@app.get("/api/status")
def status():
    return providers.get_status()


@app.get("/api/models/{provider}")
async def list_models(provider: str):
    cfg = providers.PROVIDERS.get(provider)
    if not cfg or not cfg["keys"]:
        raise HTTPException(status_code=404, detail="Unknown provider or no key configured")

    headers = {"Authorization": f"Bearer {cfg['keys'][0]}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(cfg["models_url"], headers=headers)

    if r.status_code != 200:
        print("Models error:", provider, r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail=f"Provider error {r.status_code}")

    data = r.json().get("data", [])
    if provider == "openrouter":
        ids = [m["id"] for m in data if str(m.get("pricing", {}).get("prompt")) == "0"]
    else:
        ids = [m["id"].removeprefix("models/") for m in data]
    return sorted(ids)


# ---- Testing helpers (we will remove these before going public) ----
@app.get("/api/debug/fail/{provider}")
def debug_fail(provider: str):
    providers.forced_fail.add(provider)
    return {"simulated_failures": sorted(providers.forced_fail)}


@app.get("/api/debug/clear")
def debug_clear():
    providers.forced_fail.clear()
    providers.break_after.clear()
    providers.cooldown_until.clear()
    return {"simulated_failures": [], "cooldowns": "reset"}


@app.get("/api/debug/break/{provider}/{n}")
def debug_break(provider: str, n: int):
    providers.break_after[provider] = n
    return {"break_after": providers.break_after}


async def make_search_query(messages: list[Message]) -> str:
    """Turns the latest message into a standalone web search query using recent context."""
    import asyncio
    from datetime import date

    last = messages[-1].content.strip()
    fallback = last[:200]
    if sum(1 for x in messages if x.role == "user") < 2:
        return fallback

    convo = "\n".join(f"{x.role}: {x.content[:300]}" for x in messages[-6:])
    prompt = [
        {
            "role": "system",
            "content": (
                f"Today is {date.today().isoformat()}. You turn the LAST user message of a conversation "
                "into one standalone web search query. Replace pronouns and vague references (he, she, it, "
                "that, there, them) with the real names or topics from the conversation. Keep it short, "
                "3 to 10 words, and do not add information that was not asked about. "
                "Reply with ONLY the search query: no quotes, no explanation."
            ),
        },
        {"role": "user", "content": convo},
    ]

    async def run() -> str:
        text = ""
        async for event, data in providers.stream_with_failover(prompt):
            if event == "token":
                text += data["text"]
            elif event == "error":
                return ""
        return text

    try:
        text = await asyncio.wait_for(run(), timeout=8)
    except Exception:
        return fallback

    q = text.strip().split("\n")[0].strip().strip("\"'`*# ")
    return q[:200] if len(q) >= 3 else fallback


def to_provider_message(m: Message) -> dict:
    """Turns a chat message (with optional images) into the format AI providers expect."""
    images = [
        u for u in m.images[:3]
        if u.startswith("data:image/") and ";base64," in u[:60] and len(u) < 4_000_000
    ]
    if not images:
        return {"role": m.role, "content": m.content}
    parts = [{"type": "text", "text": m.content}]
    parts += [{"type": "image_url", "image_url": {"url": u}} for u in images]
    return {"role": m.role, "content": parts}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    system = SYSTEM_PROMPT
    if req.instructions.strip():
        system += (
            "\n\nThe user has set these custom instructions. Follow them when reasonable:\n"
            + req.instructions.strip()[:1500]
        )
    sources = []
    query = ""
    if req.web_search and req.messages:
        query = await make_search_query(req.messages)
        print(f"[search] query: {query!r}")
        sources = await search.web_search(query)
        if sources:
            system += "\n\n" + search.format_context(sources)
    messages = [{"role": "system", "content": system}] + [
        to_provider_message(m) for m in req.messages
    ]
    needs_vision = any(isinstance(x['content'], list) for x in messages)

    async def event_generator():
        if sources:
            yield sse("sources", {"query": query, "items": [{"title": s["title"], "url": s["url"]} for s in sources]})
        async for event, data in providers.stream_with_failover(messages, needs_vision):
            yield sse(event, data)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

class TitleRequest(BaseModel):
    question: str


@app.post("/api/title")
async def make_title(req: TitleRequest):
    prompt = [
        {
            "role": "system",
            "content": "You write short chat titles of 2 to 5 words. Use a noun phrase in Title Case that names the topic, for example Magnet Basics, Python Function Example, or Recursion Explained. Never start with Understanding or Explaining. Never copy the user sentence. Never use a question mark. Reply with ONLY the title.",
        },
        {"role": "user", "content": "Write a title for a chat that starts with this message:\n\n" + req.question[:500]},
    ]
    text = ""
    async for event, data in providers.stream_with_failover(prompt):
        if event == "token":
            text += data["text"]
        elif event == "error":
            return {"title": ""}

    title = text.strip().split("\n")[0].strip().strip("\"'*#. ?!")
    return {"title": title[:50]}


@app.get("/api/stats")
def get_stats():
    import time

    s = providers.stats
    return {
        **s,
        "uptime_seconds": int(time.time() - s["started"]),
        "providers": providers.get_status(),
    }


import asyncio
import io

from fastapi import File, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_DOC_CHARS = 20000
TEXT_EXTENSIONS = {
    "txt", "md", "markdown", "csv", "tsv", "json", "log", "yaml", "yml", "xml", "html", "css",
    "js", "jsx", "ts", "tsx", "py", "java", "c", "cpp", "h", "go", "rs", "sql", "sh", "rb", "php", "ini", "toml",
}


def _read_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("This PDF is password protected.")
    parts, total = [], 0
    for page in reader.pages[:150]:
        t = page.extract_text() or ""
        parts.append(t)
        total += len(t)
        if total > MAX_DOC_CHARS * 2:
            break
    return "\n\n".join(parts)


@app.post("/api/extract")
async def extract_file(file: UploadFile = File(...)):
    name = (file.filename or "file")[:120]
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 10 MB.")

    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if ext == "pdf":
            text = await asyncio.to_thread(_read_pdf, data)
        elif ext in TEXT_EXTENSIONS or (file.content_type or "").startswith("text/"):
            text = data.decode("utf-8", errors="replace")
        else:
            raise HTTPException(
                status_code=415,
                detail="This file type is not supported yet. Try a PDF, text, code, CSV or an image.",
            )
    except HTTPException:
        raise
    except Exception as e:
        print("[extract] failed:", type(e).__name__, str(e)[:150])
        detail = str(e) if isinstance(e, ValueError) else "Could not read this file."
        raise HTTPException(status_code=422, detail=detail)

    text = text.replace("\x00", "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="No readable text found. Scanned PDFs are not supported yet.")

    return {
        "name": name,
        "text": text[:MAX_DOC_CHARS],
        "truncated": len(text) > MAX_DOC_CHARS,
        "chars": len(text),
    }

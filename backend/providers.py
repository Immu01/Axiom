import os
import time
import json
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()


def load_keys(env_name: str) -> list[str]:
    raw = os.getenv(env_name, "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def _clean_models(model_list: list[str]) -> list[str]:
    seen = set()
    out = []
    for m in model_list:
        m = m.strip() if m else ""
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


# Verified Free Models Roster for Zero-Downtime High Token Capacity
# The primary model is taken from .env, followed by high-quality free fallbacks.
GROQ_MODELS = _clean_models([
    os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
])

GROQ_VISION_MODELS = _clean_models([
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
])

GEMINI_MODELS = _clean_models([
    os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
    "gemini-2.0-flash-thinking-exp-01-21",
])

OPENROUTER_MODELS = _clean_models([
    os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3.1-flash:free"),
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-chat:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-2.0-flash-thinking-exp:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
])

OPENROUTER_VISION_MODELS = _clean_models([
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.2-11b-vision-instruct:free",
])

PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "models_url": "https://api.groq.com/openai/v1/models",
        "model": GROQ_MODELS[0] if GROQ_MODELS else "openai/gpt-oss-120b",
        "models": GROQ_MODELS,
        "vision_models": GROQ_VISION_MODELS or GROQ_MODELS,
        "keys": load_keys("GROQ_API_KEYS"),
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "model": GEMINI_MODELS[0] if GEMINI_MODELS else "gemini-2.0-flash",
        "models": GEMINI_MODELS,
        "vision_models": GEMINI_MODELS,
        "keys": load_keys("GEMINI_API_KEYS"),
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "models_url": "https://openrouter.ai/api/v1/models",
        "model": OPENROUTER_MODELS[0] if OPENROUTER_MODELS else "minimax/minimax-m3.1-flash:free",
        "models": OPENROUTER_MODELS,
        "vision_models": OPENROUTER_VISION_MODELS or OPENROUTER_MODELS,
        "keys": load_keys("OPENROUTER_API_KEYS"),
    },
}

# Provider priority order
ORDER = [p.strip() for p in os.getenv("PROVIDER_ORDER", "groq,gemini,openrouter").split(",")]

# All 3 providers now have vision-capable free models
VISION_PROVIDERS = [
    v.strip() for v in os.getenv("VISION_PROVIDERS", "gemini,groq,openrouter").split(",") if v.strip()
]

# Track the single model currently being used for each provider (shown in system health)
current_active_model: dict[str, str] = {
    name: cfg["model"] for name, cfg in PROVIDERS.items()
}

# A provider must send its first token within this many seconds, or Axiom moves on
FIRST_TOKEN_TIMEOUT = float(os.getenv("FIRST_TOKEN_TIMEOUT", "8"))
# After the first token, a pause longer than this means the stream is stuck
NEXT_TOKEN_TIMEOUT = float(os.getenv("NEXT_TOKEN_TIMEOUT", "20"))

# (provider, key_index, model) or (provider, key_index) -> time when the node may be used again
cooldown_until: dict[tuple, float] = {}

# Live counters for the status panel (reset when the server restarts)
stats = {
    "started": time.time(),
    "requests": 0,
    "switches": 0,
    "errors": 0,
    "served": {},
    "failed": {},
    "recent_errors": [],
}
# providers we are pretending are broken (for testing only)
forced_fail: set[str] = set()
# provider -> number of tokens after which we simulate a mid-answer break (testing only)
break_after: dict[str, int] = {}


class ProviderError(Exception):
    def __init__(self, status: int, detail: str = "", retry_after: float | None = None):
        super().__init__(f"{status} {detail}")
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


def cooldown_seconds(err: ProviderError) -> float:
    if err.status == 429:
        return err.retry_after or 60
    if err.status in (401, 403, 404):
        return 3600  # bad key or deprecated model: cool down longer
    return 30


async def stream_one(client: httpx.AsyncClient, name: str, key: str, model: str, messages: list[dict]):
    """Streams tokens from one provider using one key and model, supporting reasoning models."""
    cfg = PROVIDERS[name]
    if name in forced_fail:
        raise ProviderError(429, "simulated failure", 30)

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    # OpenRouter recommends HTTP-Referer and X-Title for free model routing
    if name == "openrouter":
        headers["HTTP-Referer"] = "https://axiom.chat"
        headers["X-Title"] = "Axiom Assistant"

    payload = {"model": model, "stream": True, "messages": messages}
    sent = 0
    in_reasoning = False

    async with client.stream("POST", cfg["url"], json=payload, headers=headers) as r:
        if r.status_code != 200:
            body = (await r.aread()).decode(errors="ignore")[:300]
            ra = r.headers.get("retry-after")
            retry_after = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
            raise ProviderError(r.status_code, body, retry_after)

        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                if in_reasoning:
                    yield "\n</think>\n\n"
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            # Support reasoning / thinking output (e.g. DeepSeek R1, Gemini Thinking)
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if reasoning:
                if not in_reasoning:
                    in_reasoning = True
                    sent += 1
                    yield "<think>\n"
                sent += 1
                yield reasoning

            token = delta.get("content")
            if token:
                if in_reasoning:
                    in_reasoning = False
                    sent += 1
                    yield "\n</think>\n\n"
                sent += 1
                if name in break_after and sent > break_after[name]:
                    raise ProviderError(503, "simulated mid-stream break", 30)
                yield token

        if in_reasoning:
            yield "\n</think>\n\n"


def fix_seam(partial: str, token: str) -> str:
    """When another provider continues an answer, make sure words don't get glued together."""
    if partial and token and not partial[-1].isspace() and token[0].isalnum() and partial[-1].isalnum():
        return " " + token
    return token


def record_success(name: str, switched: bool):
    stats["served"][name] = stats["served"].get(name, 0) + 1
    if switched:
        stats["switches"] += 1


def record_failure(name: str, e: Exception):
    stats["failed"][name] = stats["failed"].get(name, 0) + 1
    reason = f"HTTP {e.status}" if isinstance(e, ProviderError) else type(e).__name__
    entry = {"time": time.time(), "provider": name, "reason": reason}
    stats["recent_errors"] = ([entry] + stats["recent_errors"])[:5]


def pick_node(tried: set, needs_vision: bool = False):
    """Returns the first usable (provider, key_index, key, model), or None."""
    now = time.time()
    for name in ORDER:
        cfg = PROVIDERS.get(name)
        if not cfg or not cfg["keys"]:
            continue
        models_pool = cfg["vision_models"] if needs_vision else cfg["models"]
        if not models_pool:
            continue
        for i, key in enumerate(cfg["keys"]):
            # Check key-level cooldown
            if cooldown_until.get((name, i), 0) > now:
                continue
            for model in models_pool:
                node_id = (name, i, model)
                if node_id in tried or cooldown_until.get(node_id, 0) > now:
                    continue
                return name, i, key, model
    return None


async def stream_with_failover(messages: list[dict], needs_vision: bool = False):
    """Yields (event_name, data_dict).
    Always sends 'meta' for the provider and model that answers, and 'status' when a switch happened.
    If a stream breaks midway, the partial answer is continued on the next provider/model."""
    timeout = httpx.Timeout(connect=10, read=30, write=10, pool=10)
    tried: set = set()
    partial = ""
    switched = False
    stats["requests"] += 1

    # Cascade through available providers, keys, and free models
    for _ in range(12):
        node = pick_node(tried, needs_vision)
        if node is None:
            break
        name, i, key, model = node
        node_id = (name, i, model)
        cfg = PROVIDERS[name]

        current = list(messages)
        if partial:
            current += [
                {"role": "assistant", "content": partial},
                {
                    "role": "user",
                    "content": "Continue your previous answer exactly from where it stopped. "
                               "Do not repeat anything. Do not add any preamble.",
                },
            ]

        announced = False
        seam_pending = bool(partial)
        gen = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                gen = stream_one(client, name, key, model, current)
                while True:
                    wait = NEXT_TOKEN_TIMEOUT if announced else FIRST_TOKEN_TIMEOUT
                    try:
                        token = await asyncio.wait_for(gen.__anext__(), timeout=wait)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        raise httpx.ReadTimeout("no data within the allowed time")

                    if not announced:
                        # Update currently active model for this provider
                        current_active_model[name] = model
                        PROVIDERS[name]["model"] = model
                        yield "meta", {"provider": name, "model": model}
                        if switched:
                            yield "status", {"message": f"Switched provider to {name}"}
                        announced = True
                    if seam_pending:
                        token = fix_seam(partial, token)
                        seam_pending = False
                    partial += token
                    yield "token", {"text": token}

            if not announced:
                raise ProviderError(502, "empty response")

            record_success(name, switched)
            yield "done", {}
            return

        except (ProviderError, httpx.TimeoutException, httpx.TransportError) as e:
            tried.add(node_id)
            secs = cooldown_seconds(e) if isinstance(e, ProviderError) else 30
            cooldown_until[node_id] = time.time() + secs
            if isinstance(e, ProviderError) and e.status in (401, 403):
                # Bad key: cool down this key entirely
                cooldown_until[(name, i)] = time.time() + 3600
            switched = True
            if isinstance(e, ProviderError):
                detail = f"{e.status} {e.detail[:200]}"
            else:
                detail = type(e).__name__
            print(f"[failover] {name} key#{i + 1} ({model}) failed: {detail} -> cooling down {int(secs)}s")
            record_failure(name, e)

        finally:
            if gen is not None:
                try:
                    await gen.aclose()
                except Exception:
                    pass

    stats["errors"] += 1
    if needs_vision:
        yield "error", {"message": "Image understanding is unavailable right now. Please try again in a moment, or ask without the image."}
        return
    yield "error", {"message": "Axiom is very busy right now. Please try again in a moment."}


def get_status() -> dict:
    """Returns provider status showing ONLY the currently active model for each provider."""
    now = time.time()
    out = {}
    for name, cfg in PROVIDERS.items():
        nodes = []
        active_mod = current_active_model.get(name) or cfg["model"]
        for i in range(len(cfg["keys"])):
            wait_key = max(0, int(cooldown_until.get((name, i), 0) - now))
            wait_model = max(0, int(cooldown_until.get((name, i, active_mod), 0) - now))
            wait = max(wait_key, wait_model)
            nodes.append({"key": i + 1, "state": "cooling_down" if wait else "ready", "seconds_left": wait})
        out[name] = {
            "model": active_mod or "(not set)",
            "simulated_failure": name in forced_fail,
            "nodes": nodes,
        }
    return out

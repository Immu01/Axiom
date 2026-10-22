import contextlib
import os
import re
import time
import json
import asyncio
import sqlite3
import httpx
from dotenv import load_dotenv

import logutil
import metrics
import store

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


# Primary model comes from .env; the rest are fallbacks. Stale IDs are cooled down on 404.
GROQ_MODELS = _clean_models([
    os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "gemma2-9b-it",
])

GROQ_VISION_MODELS = _clean_models([
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
])

GEMINI_MODELS = _clean_models([
    os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
])

OPENROUTER_MODELS = _clean_models([
    os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3.1-flash:free"),
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
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
ORDER = [p.strip() for p in os.getenv("PROVIDER_ORDER", "groq,gemini,openrouter").split(",") if p.strip()]
ROUTING_MODE = os.getenv("ROUTING_MODE", "failover").strip().lower()
CIRCUIT_THRESHOLD = int(os.getenv("CIRCUIT_THRESHOLD", "4") or 4)
CIRCUIT_OPEN_SECS = float(os.getenv("CIRCUIT_OPEN_SECS", "60") or 60)
COST_RANK = {"groq": 1, "gemini": 2, "openrouter": 3}
QUALITY_RANK = {"gemini": 1, "groq": 2, "openrouter": 1}

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


# (provider, model) -> time when this model may be used again, on ANY key (e.g. model was retired)
model_cooldown: dict[tuple, float] = {}
# provider -> index of the key to try first on the next request (round-robin)
_rr: dict[str, int] = {}
# circuit breaker: consecutive failures open the provider for a while
circuit_fails: dict[str, int] = {}
circuit_open_until: dict[str, float] = {}
# live EWMA of time-to-first-token (ms), used by latency routing
ewma_ttft: dict[str, float] = {}

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """One shared HTTP client (connection pooling + keep-alive) for all provider calls."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=30, write=10, pool=10),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _client


async def close_client():
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def reset_state():
    """Clears simulated failures and every cooldown (used by the chaos cockpit)."""
    forced_fail.clear()
    break_after.clear()
    cooldown_until.clear()
    model_cooldown.clear()
    circuit_fails.clear()
    circuit_open_until.clear()


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


async def stream_one(
    client: httpx.AsyncClient,
    name: str,
    key: str,
    model: str,
    messages: list[dict],
    temperature: float | None = None,
):
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
    if temperature is not None:
        payload["temperature"] = temperature
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


def strip_think(text: str) -> str:
    """Removes <think>...</think> reasoning blocks (and an unfinished trailing <think> block)."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*\Z", "", text, flags=re.DOTALL)
    return text.strip()


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


def _provider_order(mode: str, pin: str | None = None) -> list[str]:
    if pin and pin in PROVIDERS:
        rest = [p for p in ORDER if p != pin]
        return [pin] + rest
    names = [n for n in ORDER if n in PROVIDERS]
    now = time.time()
    names = [n for n in names if circuit_open_until.get(n, 0) <= now]
    if mode == "cost":
        names.sort(key=lambda n: COST_RANK.get(n, 9))
    elif mode == "quality":
        names.sort(key=lambda n: QUALITY_RANK.get(n, 9))
    elif mode == "latency":
        names.sort(key=lambda n: ewma_ttft.get(n, 1e9))
    elif mode == "auto":
        names.sort(
            key=lambda n: (
                n not in ewma_ttft,
                ewma_ttft.get(n, 0),
                ORDER.index(n) if n in ORDER else 9,
            )
        )
    return names


def restore_routing_telemetry() -> None:
    totals: dict[str, list[float]] = {}
    for (provider, _model), latency in store.latency_map().items():
        aggregate = totals.setdefault(provider, [0.0, 0.0])
        aggregate[0] += latency
        aggregate[1] += 1
    for provider, (latency_total, samples) in totals.items():
        ewma_ttft[provider] = latency_total / samples


def _mark_circuit(name: str, ok: bool) -> None:
    if ok:
        circuit_fails[name] = 0
        circuit_open_until.pop(name, None)
        return
    circuit_fails[name] = circuit_fails.get(name, 0) + 1
    if circuit_fails[name] >= CIRCUIT_THRESHOLD:
        circuit_open_until[name] = time.time() + CIRCUIT_OPEN_SECS
        circuit_fails[name] = 0


def pick_node(tried: set, needs_vision: bool = False, extra_keys: dict | None = None,
              mode: str | None = None, pin_provider: str | None = None, pin_model: str | None = None):
    """Returns the first usable (provider, key_index, key, model), or None.
    Keys rotate round-robin. Providers can be reordered by routing mode."""
    now = time.time()
    extra_keys = extra_keys or {}
    mode = (mode or ROUTING_MODE or "failover").lower()
    for name in _provider_order(mode, pin_provider):
        cfg = PROVIDERS.get(name)
        if not cfg:
            continue
        keys = [extra_keys[name]] if extra_keys.get(name) else cfg["keys"]
        if not keys:
            continue
        models_pool = cfg["vision_models"] if needs_vision else cfg["models"]
        if pin_model:
            models_pool = [pin_model] + [m for m in models_pool if m != pin_model]
        if not models_pool:
            continue
        start = _rr.get(name, 0) % len(keys)
        for offset in range(len(keys)):
            i = (start + offset) % len(keys)
            if cooldown_until.get((name, i), 0) > now:
                continue
            for model in models_pool:
                node_id = (name, i, model)
                if node_id in tried or cooldown_until.get(node_id, 0) > now:
                    continue
                if model_cooldown.get((name, model), 0) > now:
                    continue
                _rr[name] = i + 1
                return name, i, keys[i], model
    return None


async def stream_with_failover(
    messages: list[dict],
    needs_vision: bool = False,
    internal: bool = False,
    extra_keys: dict | None = None,
    mode: str | None = None,
    pin_provider: str | None = None,
    pin_model: str | None = None,
    temperature: float | None = None,
):
    """Yields (event_name, data_dict).
    Always sends 'meta' for the provider and model that answers, and 'status' when a switch happened.
    If a stream breaks midway, the partial answer is continued on the next provider/model."""
    tried: set = set()
    partial = ""
    switched = False
    if not internal:
        stats["requests"] += 1
        metrics.inc("axiom_chat_requests_total")

    # Cascade through available providers, keys, and free models
    for _ in range(12):
        node = pick_node(tried, needs_vision, extra_keys, mode, pin_provider, pin_model)
        if node is None:
            break
        name, i, key, model = node
        node_id = (name, i, model)

        current = list(messages)
        visible = strip_think(partial)  # never feed another model's private reasoning back in
        if visible:
            current += [
                {"role": "assistant", "content": visible},
                {
                    "role": "user",
                    "content": "Continue your previous answer exactly from where it stopped. "
                               "Do not repeat anything. Do not add any preamble.",
                },
            ]

        announced = False
        seam_pending = bool(visible)
        gen = None
        t0 = time.time()
        yield "timeline", {"t": t0, "provider": name, "model": model, "phase": "attempt"}
        try:
            async with contextlib.nullcontext(get_client()) as client:
                gen = stream_one(client, name, key, model, current, temperature=temperature)
                while True:
                    wait = NEXT_TOKEN_TIMEOUT if announced else FIRST_TOKEN_TIMEOUT
                    try:
                        token = await asyncio.wait_for(gen.__anext__(), timeout=wait)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        raise httpx.ReadTimeout("no data within the allowed time")

                    if not announced:
                        ttft = (time.time() - t0) * 1000
                        prev = ewma_ttft.get(name)
                        ewma_ttft[name] = ttft if prev is None else 0.3 * ttft + 0.7 * prev
                        try:
                            store.record_latency(name, model, ttft)
                        except sqlite3.Error as error:
                            logutil.log(
                                "latency_store_error",
                                provider=name,
                                model=model,
                                error=type(error).__name__,
                            )
                        metrics.observe("axiom_ttft_ms", ttft, provider=name)
                        current_active_model[name] = model
                        PROVIDERS[name]["model"] = model
                        logutil.log("provider_selected", provider=name, key_index=i + 1, model=model)
                        yield "meta", {"provider": name, "model": model}
                        if switched:
                            yield "status", {"message": f"Switched provider to {name}"}
                        announced = True
                    if seam_pending:
                        token = fix_seam(visible, token)
                        seam_pending = False
                    partial += token
                    yield "token", {"text": token}

            if not announced:
                raise ProviderError(502, "empty response")

            record_success(name, switched and not internal)
            _mark_circuit(name, True)
            yield "timeline", {"t": time.time(), "provider": name, "model": model, "phase": "ok"}
            yield "done", {}
            return

        except (ProviderError, httpx.TimeoutException, httpx.TransportError) as e:
            tried.add(node_id)
            secs = cooldown_seconds(e) if isinstance(e, ProviderError) else 30
            cooldown_until[node_id] = time.time() + secs
            if isinstance(e, ProviderError) and e.status in (401, 403):
                cooldown_until[(name, i)] = time.time() + 3600
            elif isinstance(e, ProviderError) and e.status == 404:
                model_cooldown[(name, model)] = time.time() + 3600
            switched = True
            if isinstance(e, ProviderError):
                detail = f"{e.status} {e.detail[:200]}"
                failure_reason = f"HTTP {e.status}"
            else:
                detail = type(e).__name__
                failure_reason = detail
            logutil.log(
                "provider_failure",
                provider=name,
                key_index=i + 1,
                model=model,
                reason=failure_reason,
                cooldown_seconds=int(secs),
            )
            record_failure(name, e)
            _mark_circuit(name, False)
            yield "timeline", {"t": time.time(), "provider": name, "model": model, "phase": "fail", "detail": detail[:120]}

        finally:
            if gen is not None:
                try:
                    await gen.aclose()
                except Exception:
                    pass

    if not internal:
        stats["errors"] += 1
    if needs_vision:
        yield "error", {"message": "Image understanding is unavailable right now. Please try again in a moment, or ask without the image."}
        return
    yield "error", {"message": "Axiom is very busy right now. Please try again in a moment."}


async def complete_one(client: httpx.AsyncClient, name: str, key: str, model: str, messages: list[dict], tools=None) -> dict:
    cfg = PROVIDERS[name]
    if name in forced_fail:
        raise ProviderError(429, "simulated failure", 30)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if name == "openrouter":
        headers["HTTP-Referer"] = "https://axiom.chat"
        headers["X-Title"] = "Axiom Assistant"
    payload = {"model": model, "stream": False, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    r = await client.post(cfg["url"], json=payload, headers=headers)
    if r.status_code != 200:
        ra = r.headers.get("retry-after")
        retry_after = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
        raise ProviderError(r.status_code, r.text[:300], retry_after)
    return r.json()


async def complete_with_failover(
    messages: list[dict],
    tools=None,
    extra_keys: dict | None = None,
    mode: str | None = None,
    pin_provider: str | None = None,
    pin_model: str | None = None,
):
    """Non-streaming completion used by the agent loop (needs tool_calls)."""
    tried: set = set()
    for _ in range(8):
        node = pick_node(tried, False, extra_keys, mode, pin_provider, pin_model)
        if node is None:
            break
        name, i, key, model = node
        node_id = (name, i, model)
        try:
            data = await complete_one(get_client(), name, key, model, messages, tools)
            current_active_model[name] = model
            _mark_circuit(name, True)
            record_success(name, False)
            return name, model, data
        except (ProviderError, httpx.TimeoutException, httpx.TransportError) as e:
            tried.add(node_id)
            secs = cooldown_seconds(e) if isinstance(e, ProviderError) else 30
            cooldown_until[node_id] = time.time() + secs
            record_failure(name, e)
            _mark_circuit(name, False)
    return None, None, None


async def probe_providers() -> dict:
    """Health probe: hit each provider's /models endpoint and cool down on failure."""
    out = {}
    for name, cfg in PROVIDERS.items():
        if not cfg["keys"]:
            out[name] = "no_key"
            continue
        try:
            r = await get_client().get(
                cfg["models_url"],
                headers={"Authorization": f"Bearer {cfg['keys'][0]}"},
                timeout=15,
            )
            if r.status_code == 200:
                _mark_circuit(name, True)
                out[name] = "ok"
            else:
                _mark_circuit(name, False)
                out[name] = f"http_{r.status_code}"
        except Exception as e:
            _mark_circuit(name, False)
            out[name] = type(e).__name__
    return out


def get_status() -> dict:
    """Returns provider status showing ONLY the currently active model for each provider."""
    now = time.time()
    out = {}
    for name, cfg in PROVIDERS.items():
        nodes = []
        active_mod = current_active_model.get(name) or cfg["model"]
        for i in range(len(cfg["keys"])):
            wait_key = max(0, int(cooldown_until.get((name, i), 0) - now))
            wait_model = max(
                0,
                int(max(cooldown_until.get((name, i, active_mod), 0), model_cooldown.get((name, active_mod), 0)) - now),
            )
            wait = max(wait_key, wait_model)
            nodes.append({"key": i + 1, "state": "cooling_down" if wait else "ready", "seconds_left": wait})
        out[name] = {
            "model": active_mod or "(not set)",
            "simulated_failure": name in forced_fail,
            "circuit_open": circuit_open_until.get(name, 0) > now,
            "ttft_ms": round(ewma_ttft[name], 1) if name in ewma_ttft else None,
            "nodes": nodes,
        }
    return out

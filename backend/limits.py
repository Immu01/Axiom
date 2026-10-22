"""Per-client rate limiting and request-size guards (in-memory, no extra dependencies).

Note: counters live in this process only. If you run several workers or servers,
each keeps its own counts (a shared store such as Redis would be the next step).
"""
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

# Hard caps for chat payloads
MAX_MESSAGES = 400
MAX_MESSAGE_CHARS = 100_000
MAX_TOTAL_CHARS = 400_000
MAX_CHAT_BODY_BYTES = int(os.getenv("MAX_CHAT_BODY_MB", "16")) * 1024 * 1024
MAX_EXTRACT_BODY_BYTES = 12 * 1024 * 1024


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def client_key(request: Request) -> str:
    """Who is calling? Uses the socket address, or X-Forwarded-For only if TRUST_PROXY=1."""
    if os.getenv("TRUST_PROXY", "") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Sliding-window limiter: at most `limit` calls per `window` seconds per client. limit<=0 disables."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.hits: dict[str, deque] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def check(self, key: str) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry = int(q[0] + self.window - now) + 1
            raise HTTPException(
                status_code=429,
                detail="You're sending requests too quickly. Please wait a moment and try again.",
                headers={"Retry-After": str(retry)},
            )
        q.append(now)
        self._sweep(now)

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        for k in [k for k, q in self.hits.items() if not q or q[-1] <= now - self.window]:
            del self.hits[k]


chat_limiter = RateLimiter(_int_env("RATE_LIMIT_CHAT", 20))
title_limiter = RateLimiter(_int_env("RATE_LIMIT_TITLE", 30))
extract_limiter = RateLimiter(_int_env("RATE_LIMIT_EXTRACT", 10))
admin_limiter = RateLimiter(_int_env("RATE_LIMIT_ADMIN", 30))


def chat_limit(request: Request) -> None:
    chat_limiter.check(client_key(request))


def title_limit(request: Request) -> None:
    title_limiter.check(client_key(request))


def extract_limit(request: Request) -> None:
    extract_limiter.check(client_key(request))


def body_limit(max_bytes: int):
    """Rejects requests whose declared Content-Length is bigger than max_bytes (HTTP 413)."""

    def dep(request: Request) -> None:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise HTTPException(status_code=413, detail="Request is too large.")

    return dep


chat_body = body_limit(MAX_CHAT_BODY_BYTES)
extract_body = body_limit(MAX_EXTRACT_BODY_BYTES)

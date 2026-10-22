"""Gateway auth: optional shared API key, issued user keys, BYO provider keys, quotas."""
import hmac
import os
from typing import Any

from fastapi import Header, HTTPException, Request

import limits
import store

AXIOM_API_KEY = lambda: os.getenv("AXIOM_API_KEY", "")
DAILY_REQUESTS = int(os.getenv("DAILY_REQUESTS", "200") or 200)
DAILY_TOKENS = int(os.getenv("DAILY_TOKENS", "500000") or 500000)
_auth_required = os.getenv("AUTH_REQUIRED", "").strip()
AUTH_REQUIRED = (
    _auth_required.lower() in {"1", "true", "yes"}
    if _auth_required
    else os.getenv("ENVIRONMENT", "").lower() == "production"
)


def _extract_token(authorization: str, x_api_key: str) -> str:
    if x_api_key.strip():
        return x_api_key.strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def require_user(
    request: Request,
    authorization: str = Header(default=""),
    x_api_key: str = Header(default=""),
) -> dict[str, Any]:
    """If AXIOM_API_KEY is set, callers must present it or a minted user key."""
    expected = AXIOM_API_KEY()
    token = _extract_token(authorization, x_api_key)
    client = limits.client_key(request)
    if expected and token and hmac.compare_digest(token.encode(), expected.encode()):
        user = {
            "id": f"primary:{client}",
            "kind": "server",
            "daily_requests": DAILY_REQUESTS,
            "daily_tokens": DAILY_TOKENS,
        }
        _enforce_quota(user)
        return user
    row = store.lookup_api_key(token) if token else None
    if row:
        user = {
            "id": f"key:{row['id']}",
            "kind": "user",
            "daily_requests": int(row["daily_requests"]),
            "daily_tokens": int(row["daily_tokens"]),
        }
        _enforce_quota(user)
        return user
    if expected or AUTH_REQUIRED:
        if not expected and not token:
            raise HTTPException(status_code=503, detail="Gateway authentication is required but not configured.")
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")
    user = {"id": client, "kind": "anon", "daily_requests": DAILY_REQUESTS, "daily_tokens": DAILY_TOKENS}
    _enforce_quota(user)
    return user


def _enforce_quota(user: dict) -> None:
    if store.reserve_request(
        user["id"],
        int(user["daily_requests"]),
        int(user["daily_tokens"]),
    ) is None:
        reqs, toks = store.quota_usage(user["id"])
        detail = "Daily request quota exceeded." if reqs >= int(user["daily_requests"]) else "Daily token quota exceeded."
        raise HTTPException(status_code=429, detail=detail)


def sanitize_byok(raw: dict | None) -> dict[str, str]:
    """Accepts optional per-request provider keys from the user. Never logs them."""
    if not raw or not isinstance(raw, dict):
        return {}
    out = {}
    for name in ("groq", "gemini", "openrouter", "tavily"):
        val = raw.get(name)
        if isinstance(val, str) and 8 < len(val) < 400:
            out[name] = val.strip()
    return out

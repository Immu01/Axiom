"""Minimal MCP client: JSON-RPC over HTTP (tools/list + tools/call)."""
import asyncio
import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx

import providers


async def validate_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("MCP server URL must be an http(s) URL without embedded credentials.")

    host = parsed.hostname.lower().rstrip(".")
    allowed = {
        item.strip().lower().rstrip(".")
        for item in os.getenv("MCP_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    if parsed.scheme != "https" and host not in allowed:
        raise ValueError("MCP servers must use HTTPS unless their host is listed in MCP_ALLOWED_HOSTS.")
    if host in allowed:
        return url

    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, host, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("MCP server hostname could not be resolved.") from exc
    ips = {ipaddress.ip_address(item[4][0].split("%", 1)[0]) for item in addresses}
    if not ips or any(not ip.is_global for ip in ips):
        raise ValueError("MCP server must resolve only to public IP addresses.")
    return url


async def list_tools(url: str) -> list[dict]:
    url = await validate_endpoint(url)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    r = await providers.get_client().post(url, json=payload, timeout=12, follow_redirects=False)
    r.raise_for_status()
    result = r.json().get("result") or {}
    return result.get("tools") or []


async def call_tool(url: str, name: str, arguments: dict[str, Any]) -> str:
    try:
        url = await validate_endpoint(url)
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        r = await providers.get_client().post(url, json=payload, timeout=20, follow_redirects=False)
        r.raise_for_status()
        result = r.json().get("result") or {}
        if isinstance(result, str):
            return result[:8000]
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(parts)[:8000]
        return str(result)[:8000]
    except (httpx.HTTPError, ValueError) as e:
        return f"MCP tool error: {type(e).__name__}"

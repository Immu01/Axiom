import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import mcp_client


@pytest.mark.asyncio
async def test_private_mcp_address_is_rejected():
    with pytest.raises(ValueError, match="public IP"):
        await mcp_client.validate_endpoint("https://127.0.0.1/mcp")


@pytest.mark.asyncio
async def test_http_mcp_requires_explicit_host_allowlist(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "localhost")
    assert await mcp_client.validate_endpoint("http://localhost:3000/mcp") == "http://localhost:3000/mcp"

    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "")
    with pytest.raises(ValueError, match="HTTPS"):
        await mcp_client.validate_endpoint("http://example.com/mcp")

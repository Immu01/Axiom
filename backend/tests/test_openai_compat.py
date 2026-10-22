import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import openai_compat
import providers


@pytest.mark.asyncio
async def test_collect_completion(monkeypatch):
    async def fake_stream(messages, **kwargs):
        yield "meta", {"provider": "groq", "model": "llama"}
        yield "token", {"text": "<think>x</think>Hi there"}
        yield "done", {}

    monkeypatch.setattr(providers, "stream_with_failover", fake_stream)
    req = openai_compat.OAChatRequest(model="axiom", messages=[openai_compat.OAMessage(role="user", content="hey")])
    data = await openai_compat.collect_completion(req)
    assert data["choices"][0]["message"]["content"] == "Hi there"
    assert data["object"] == "chat.completion"
    assert data["usage"]["completion_tokens"] > 0


@pytest.mark.asyncio
async def test_stream_completion_hides_think_blocks_across_chunk_boundaries(monkeypatch):
    async def fake_stream(messages, **kwargs):
        yield "token", {"text": "Start <thi"}
        yield "token", {"text": "nk>private reasoning</thi"}
        yield "token", {"text": "nk>Answer"}
        yield "done", {}

    monkeypatch.setattr(providers, "stream_with_failover", fake_stream)
    req = openai_compat.OAChatRequest(
        messages=[openai_compat.OAMessage(role="user", content="hey")],
        stream=True,
    )
    chunks = [chunk async for chunk in openai_compat.stream_completion(req)]

    combined = "".join(chunks)
    assert "private reasoning" not in combined
    visible = "".join(
        json.loads(chunk.removeprefix("data: ").strip())["choices"][0]["delta"].get("content", "")
        for chunk in chunks
        if chunk.startswith("data: {")
    )
    assert visible == "Start Answer"


def test_pin_from_model():
    assert openai_compat._pin_from_model("axiom") == (None, None)
    assert openai_compat._pin_from_model("groq") == ("groq", None)
    assert openai_compat._pin_from_model("groq/llama-3.3-70b-versatile") == ("groq", "llama-3.3-70b-versatile")

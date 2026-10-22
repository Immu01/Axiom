import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import providers


class FakeStream:
    def __init__(self, tokens=None, error=None):
        self.tokens = list(tokens or [])
        self.error = error

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.tokens:
            return self.tokens.pop(0)
        if self.error:
            err, self.error = self.error, None
            raise err
        raise StopAsyncIteration

    async def aclose(self):
        return


@pytest.mark.asyncio
async def test_failover_to_second_provider(monkeypatch):
    providers.reset_state()
    providers.PROVIDERS["groq"]["keys"] = ["g1"]
    providers.PROVIDERS["gemini"]["keys"] = ["e1"]
    providers.PROVIDERS["openrouter"]["keys"] = []
    providers.ORDER[:] = ["groq", "gemini", "openrouter"]

    calls = []

    def fake_stream_one(client, name, key, model, messages, temperature=None):
        calls.append(name)
        if name == "groq":
            return FakeStream(error=providers.ProviderError(429, "rate", 1))
        return FakeStream(tokens=["Hello", " world"])

    monkeypatch.setattr(providers, "stream_one", fake_stream_one)
    monkeypatch.setattr(providers, "get_client", lambda: object())

    events = []
    async for ev, data in providers.stream_with_failover(
        [{"role": "user", "content": "hi"}], internal=True
    ):
        events.append((ev, data))

    kinds = [e[0] for e in events]
    assert "groq" in calls and "gemini" in calls
    assert "token" in kinds
    assert "done" in kinds
    text = "".join(d.get("text", "") for k, d in events if k == "token")
    assert "Hello" in text


@pytest.mark.asyncio
async def test_continuation_strips_think(monkeypatch):
    providers.reset_state()
    providers.PROVIDERS["groq"]["keys"] = ["g1"]
    providers.PROVIDERS["gemini"]["keys"] = ["e1"]
    providers.PROVIDERS["openrouter"]["keys"] = []
    providers.ORDER[:] = ["groq", "gemini"]

    seen = []

    def fake_stream_one(client, name, key, model, messages, temperature=None):
        seen.append((name, messages))
        if name == "groq":
            return FakeStream(tokens=["<think>nope</think>partial"], error=providers.ProviderError(503, "break", 1))
        return FakeStream(tokens=[" more"])

    monkeypatch.setattr(providers, "stream_one", fake_stream_one)
    monkeypatch.setattr(providers, "get_client", lambda: object())

    async for _ev, _data in providers.stream_with_failover(
        [{"role": "user", "content": "hi"}], internal=True
    ):
        pass

    gemini_msgs = next(messages for name, messages in seen if name == "gemini")
    # reasoning must not be replayed to the next model
    dumped = str(gemini_msgs)
    assert "<think>" not in dumped
    assert "partial" in dumped


def test_auto_route_prefers_observed_low_latency(monkeypatch):
    providers.circuit_open_until.clear()
    monkeypatch.setattr(providers, "ORDER", ["groq", "gemini", "openrouter"])
    monkeypatch.setattr(providers, "ewma_ttft", {"gemini": 80.0, "groq": 110.0})

    assert providers._provider_order("auto") == ["gemini", "groq", "openrouter"]

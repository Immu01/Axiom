"""OpenAI-compatible /v1/chat/completions adapter over Axiom's cascade."""
import json
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

import providers


class OAMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Any = ""

    @model_validator(mode="after")
    def _check_content(self):
        if not isinstance(self.content, (str, list)) and self.content is not None:
            raise ValueError("Message content must be a string or a multimodal content list")
        if len(self.content or "") > 100_000:
            raise ValueError("Message content is too long")
        return self


class OAChatRequest(BaseModel):
    model: str = Field(default="axiom", max_length=160)
    messages: list[OAMessage] = Field(min_length=1, max_length=400)
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def _check_total_size(self):
        if sum(len(str(message.content)) for message in self.messages) > 400_000:
            raise ValueError("Conversation is too long")
        return self


def _to_provider_messages(messages: list[OAMessage]) -> list[dict]:
    out = []
    for m in messages:
        content = m.content
        if isinstance(content, list):
            out.append({"role": m.role, "content": content})
        else:
            out.append({"role": m.role, "content": str(content or "")})
    return out


def _pin_from_model(model: str) -> tuple[str | None, str | None]:
    if not model or model in ("axiom", "axiom-auto", "auto"):
        return None, None
    if model in providers.PROVIDERS:
        return model, None
    if "/" in model and model.split("/", 1)[0] in providers.PROVIDERS:
        # groq/llama-3.3-70b-versatile
        name, rest = model.split("/", 1)
        return name, rest
    return None, model


def _drain_visible(state: dict[str, Any], final: bool = False) -> list[str]:
    emitted = []
    while state["buffer"]:
        marker = "</think>" if state["inside"] else "<think>"
        index = state["buffer"].find(marker)
        if index >= 0:
            if not state["inside"] and index:
                emitted.append(state["buffer"][:index])
            state["buffer"] = state["buffer"][index + len(marker):]
            state["inside"] = not state["inside"]
            continue
        if final:
            if not state["inside"]:
                emitted.append(state["buffer"])
            state["buffer"] = ""
            break
        safe_length = max(0, len(state["buffer"]) - len(marker) + 1)
        if safe_length:
            safe_text = state["buffer"][:safe_length]
            state["buffer"] = state["buffer"][safe_length:]
            if not state["inside"]:
                emitted.append(safe_text)
        break
    return emitted


async def collect_completion(req: OAChatRequest) -> dict:
    pin_p, pin_m = _pin_from_model(req.model)
    messages = _to_provider_messages(req.messages)
    text = ""
    provider, model = "axiom", req.model
    async for event, data in providers.stream_with_failover(
        messages,
        pin_provider=pin_p,
        pin_model=pin_m,
        temperature=req.temperature,
    ):
        if event == "meta":
            provider, model = data.get("provider") or provider, data.get("model") or model
        elif event == "token":
            text += data.get("text") or ""
        elif event == "error":
            return {
                "error": {"message": data.get("message"), "type": "axiom_error"},
            }
    cid = "chatcmpl-" + uuid.uuid4().hex[:24]
    return {
        "id": cid,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": f"{provider}/{model}",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": providers.strip_think(text)},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": sum(len(str(message.content)) for message in req.messages) // 4,
            "completion_tokens": len(text) // 4,
            "total_tokens": (sum(len(str(message.content)) for message in req.messages) + len(text)) // 4,
        },
    }


async def stream_completion(req: OAChatRequest):
    pin_p, pin_m = _pin_from_model(req.model)
    messages = _to_provider_messages(req.messages)
    cid = "chatcmpl-" + uuid.uuid4().hex[:24]
    created = int(time.time())
    model_name = req.model

    def chunk(delta: dict, finish=None) -> str:
        body = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(body)}\n\n"

    yield chunk({"role": "assistant"})
    filter_state = {"buffer": "", "inside": False}
    async for event, data in providers.stream_with_failover(
        messages,
        pin_provider=pin_p,
        pin_model=pin_m,
        temperature=req.temperature,
    ):
        if event == "meta":
            model_name = f"{data.get('provider')}/{data.get('model')}"
        elif event == "token":
            filter_state["buffer"] += data.get("text") or ""
            for text in _drain_visible(filter_state):
                yield chunk({"content": text})
        elif event == "error":
            for text in _drain_visible(filter_state, final=True):
                yield chunk({"content": text})
            yield chunk({"content": ""}, finish="stop")
            yield "data: [DONE]\n\n"
            return
    for text in _drain_visible(filter_state, final=True):
        yield chunk({"content": text})
    yield chunk({}, finish="stop")
    yield "data: [DONE]\n\n"

"""Planner/executor loop: the model may call tools, then continues until it answers."""
import json
import time

import httpx

import providers
import tools as toolmod


async def run_agent(
    messages: list[dict],
    mcp_url: str = "",
    extra_keys: dict | None = None,
    mode: str | None = None,
    owner_id: str = "",
    pin_provider: str | None = None,
    pin_model: str | None = None,
):
    """Yields the same (event, data) pairs as stream_with_failover, plus 'tool' events."""
    try:
        schemas = await toolmod.schemas(mcp_url)
    except (httpx.HTTPError, ValueError, OSError) as exc:
        yield "error", {"message": f"Could not connect to the configured MCP server: {type(exc).__name__}."}
        return
    working = list(messages)
    for step in range(6):
        yield "timeline", {"t": time.time(), "phase": "plan", "detail": f"step {step + 1}"}
        name, model, data = await providers.complete_with_failover(
            working,
            tools=schemas,
            extra_keys=extra_keys,
            mode=mode,
            pin_provider=pin_provider,
            pin_model=pin_model,
        )
        if not data:
            yield "error", {"message": "Axiom could not reach a model for the agent loop."}
            return
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            working.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = (tc.get("function") or {})
                fname = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}
                yield "tool", {"name": fname, "arguments": args}
                result = await toolmod.execute(fname, args, mcp_url=mcp_url, owner_id=owner_id)
                yield "tool", {"name": fname, "result": result[:1500]}
                working.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or fname,
                    "content": result,
                })
            continue
        content = msg.get("content") or ""
        if content:
            yield "meta", {"provider": name, "model": model}
            yield "token", {"text": content}
            yield "done", {}
            return
        break

    async for event, payload in providers.stream_with_failover(
        working,
        extra_keys=extra_keys,
        mode=mode,
        pin_provider=pin_provider,
        pin_model=pin_model,
    ):
        yield event, payload

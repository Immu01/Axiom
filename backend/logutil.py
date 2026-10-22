"""JSON structured logs for the gateway (one event per line)."""
import json
import sys
import time


def log(event: str, **fields) -> None:
    payload = {"ts": round(time.time(), 3), "event": event, **fields}
    print(json.dumps(payload, default=str), file=sys.stderr, flush=True)

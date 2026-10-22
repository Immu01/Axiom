"""In-process Prometheus text metrics (no extra dependency)."""
import time
from collections import defaultdict

_started = time.time()
_counters: dict[str, float] = defaultdict(float)
_gauges: dict[str, float] = {}
_hist: dict[str, list[float]] = defaultdict(list)


def inc(name: str, value: float = 1, **labels) -> None:
    _counters[_key(name, labels)] += value


def set_gauge(name: str, value: float, **labels) -> None:
    _gauges[_key(name, labels)] = value


def observe(name: str, value: float, **labels) -> None:
    bucket = _hist[_key(name, labels)]
    bucket.append(value)
    if len(bucket) > 500:
        del bucket[: len(bucket) - 500]


def _key(name: str, labels: dict) -> str:
    if not labels:
        return name
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def render() -> str:
    lines = [
        "# HELP axiom_uptime_seconds Process uptime",
        "# TYPE axiom_uptime_seconds gauge",
        f"axiom_uptime_seconds {int(time.time() - _started)}",
    ]
    for k, v in sorted(_counters.items()):
        lines.append(f"{k} {v}")
    for k, v in sorted(_gauges.items()):
        lines.append(f"{k} {v}")
    for k, samples in sorted(_hist.items()):
        if not samples:
            continue
        avg = sum(samples) / len(samples)
        lines.append(f"{k}_avg {avg:.4f}")
        lines.append(f"{k}_count {len(samples)}")
    return "\n".join(lines) + "\n"

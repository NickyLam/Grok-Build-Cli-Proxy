from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsRegistry:
    """In-process counters/gauges for /metrics (Prometheus text format)."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    counters: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    gauges: dict[str, float] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = _metric_key(name, labels)
        with self._lock:
            self.counters[key] += value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = _metric_key(name, labels)
        with self._lock:
            self.gauges[key] = value

    def observe_duration(self, name: str, seconds: float, **labels: str) -> None:
        # Simple sum + count for average-capable clients
        self.inc(f"{name}_seconds_sum", seconds, **labels)
        self.inc(f"{name}_seconds_count", 1.0, **labels)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "uptime_seconds": time.time() - self.started_at,
            }

    def render_prometheus(self) -> str:
        snap = self.snapshot()
        lines: list[str] = [
            "# HELP grok_proxy_uptime_seconds Process uptime",
            "# TYPE grok_proxy_uptime_seconds gauge",
            f"grok_proxy_uptime_seconds {snap['uptime_seconds']:.3f}",
        ]
        for key, val in sorted(snap["counters"].items()):
            name, label_str = _split_key(key)
            lines.append(f"{name}{label_str} {val}")
        for key, val in sorted(snap["gauges"].items()):
            name, label_str = _split_key(key)
            lines.append(f"{name}{label_str} {val}")
        return "\n".join(lines) + "\n"


def _metric_key(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{parts}}}"


def _split_key(key: str) -> tuple[str, str]:
    if "{" not in key:
        return key, ""
    name, rest = key.split("{", 1)
    return name, "{" + rest


# process-global default (also stored on app.state)
_default = MetricsRegistry()


def get_default_metrics() -> MetricsRegistry:
    return _default

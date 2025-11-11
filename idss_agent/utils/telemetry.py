"""
Lightweight telemetry helpers for capturing agent latency and diagnostics.
"""
from __future__ import annotations

from time import perf_counter
from typing import Dict, Any, List


def start_span(name: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Create a span token that can be finished later.
    """
    return {
        "name": name,
        "metadata": metadata or {},
        "_start": perf_counter(),
    }


def finish_span(span: Dict[str, Any]) -> Dict[str, Any]:
    """
    Close a span dictionary and compute elapsed duration.
    """
    span = span.copy()
    start = span.pop("_start", None)
    if start is None:
        span["duration_ms"] = None
    else:
        span["duration_ms"] = (perf_counter() - start) * 1000.0
    return span


def append_span(container: Dict[str, Any], span: Dict[str, Any]) -> None:
    """
    Append a span to the telemetry container on the provided state.
    """
    telemetry: List[Dict[str, Any]] = container.setdefault("_telemetry", [])
    telemetry.append(span)






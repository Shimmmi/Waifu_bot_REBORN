"""Lightweight in-process latency samples for Stage 1 baseline (P50/P95 in logs)."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)

_MAX_SAMPLES = 2000
_buckets: dict[str, list[float]] = defaultdict(list)


def enabled() -> bool:
    return bool(getattr(settings, "perf_metrics_enabled", False))


def record_ms(name: str, duration_ms: float) -> None:
    if not enabled():
        return
    buf = _buckets[name]
    buf.append(duration_ms)
    if len(buf) > _MAX_SAMPLES:
        del buf[: len(buf) - _MAX_SAMPLES]


@asynccontextmanager
async def track_async(name: str) -> AsyncIterator[None]:
    if not enabled():
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record_ms(name, (time.perf_counter() - t0) * 1000.0)


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def log_summary() -> None:
    """Emit one log line per metric with count, p50, p95 (for grep / Loki)."""
    if not enabled() or not _buckets:
        return
    parts: list[str] = []
    for name in sorted(_buckets):
        vals = sorted(_buckets[name])
        if not vals:
            continue
        parts.append(
            f"{name}:n={len(vals)} p50={_percentile(vals, 0.5):.1f}ms "
            f"p95={_percentile(vals, 0.95):.1f}ms max={vals[-1]:.1f}ms"
        )
    if parts:
        logger.info("perf_metric summary | %s", " | ".join(parts))


def reset() -> None:
    _buckets.clear()

"""Unit tests: perf_metrics percentile logging."""

from __future__ import annotations

from waifu_bot.services import perf_metrics as pm


def test_percentile_via_log_summary(monkeypatch):
    pm.reset()
    monkeypatch.setattr(pm, "enabled", lambda: True)
    for v in [10.0, 20.0, 30.0, 40.0, 100.0]:
        pm.record_ms("test_metric_ms", v)
    logged: list[str] = []

    def capture(msg, *args):
        logged.append(msg % args if args else msg)

    monkeypatch.setattr(pm.logger, "info", capture)
    pm.log_summary()
    assert logged
    line = logged[0]
    assert "test_metric_ms" in line
    assert "p50=" in line
    assert "p95=" in line
    pm.reset()


def test_record_skipped_when_disabled(monkeypatch):
    pm.reset()
    monkeypatch.setattr(pm, "enabled", lambda: False)
    pm.record_ms("x_ms", 99.0)
    assert "x_ms" not in pm._buckets or not pm._buckets.get("x_ms")

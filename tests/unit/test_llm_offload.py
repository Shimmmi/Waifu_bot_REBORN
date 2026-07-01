"""Unit tests: LLM worker offload gating."""

from __future__ import annotations

from waifu_bot.services import llm_client as lc


def test_should_offload_gd_callers(monkeypatch):
    monkeypatch.setattr(lc.settings, "llm_worker_enabled", True)
    monkeypatch.setattr(lc.settings, "worker_role", "api")
    assert lc.should_offload_llm("gd-round") is True
    assert lc.should_offload_llm("expedition tick") is True
    assert lc.should_offload_llm("guild war narrative") is True


def test_should_not_offload_in_llm_worker(monkeypatch):
    monkeypatch.setattr(lc.settings, "llm_worker_enabled", True)
    monkeypatch.setattr(lc.settings, "worker_role", "llm")
    assert lc.should_offload_llm("gd-round") is False


def test_should_not_offload_when_disabled(monkeypatch):
    monkeypatch.setattr(lc.settings, "llm_worker_enabled", False)
    monkeypatch.setattr(lc.settings, "worker_role", "api")
    assert lc.should_offload_llm("gd-round") is False

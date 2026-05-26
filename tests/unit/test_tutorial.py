"""Unit tests for tutorial progress service."""
from __future__ import annotations

import pytest

from waifu_bot.services.tutorial import (
    INTRO_TUTORIAL_GOLD_REWARD,
    KNOWN_TUTORIAL_STEPS,
    normalize_tutorial_progress,
)


def test_normalize_tutorial_progress_empty():
    state = normalize_tutorial_progress(None)
    assert state["version"] == 1
    assert state["completed"] == {}
    assert state["skipped"] is False
    assert state["intro_reward_claimed"] is False


def test_normalize_tutorial_progress_parses_completed():
    raw = {
        "version": 2,
        "completed": {"intro": "2026-05-23T12:00:00+00:00", "bad": 123},
        "skipped": True,
        "intro_reward_claimed": True,
    }
    state = normalize_tutorial_progress(raw)
    assert state["version"] == 2
    assert state["completed"] == {"intro": "2026-05-23T12:00:00+00:00"}
    assert state["skipped"] is True
    assert state["intro_reward_claimed"] is True


def test_known_steps_include_intro_and_sections():
    assert "intro" in KNOWN_TUTORIAL_STEPS
    assert "shop" in KNOWN_TUTORIAL_STEPS
    assert INTRO_TUTORIAL_GOLD_REWARD == 500

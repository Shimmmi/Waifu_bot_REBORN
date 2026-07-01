"""Unit tests for GD battle log formatting."""
from __future__ import annotations

from waifu_bot.services.gd_battle_log import format_gd_round_log_lines_ru


def test_text_damage_includes_guild_skill_suffix():
    ctx = {
        "party": [
            {"user_id": 101, "name": "Алиса"},
            {"user_id": 202, "name": "Боб"},
        ],
        "monsters": [],
    }
    resolved = [
        {
            "user_id": 101,
            "kind": "text",
            "damage": 120,
            "guild_skill_lines": ["Боевой клич (+6%)"],
        }
    ]
    lines = format_gd_round_log_lines_ru(resolved, ctx)
    assert len(lines) == 1
    assert "120" in lines[0]
    assert "Боевой клич (+6%)" in lines[0]
    assert "ОВ игрока 1 (Алиса)" in lines[0]


def test_text_damage_fallback_guild_damage_pct():
    ctx = {"party": [{"user_id": 5, "name": "Test"}], "monsters": []}
    resolved = [{"user_id": 5, "kind": "text", "damage": 50, "guild_damage_pct": 0.06}]
    lines = format_gd_round_log_lines_ru(resolved, ctx)
    assert "Боевой клич +6%" in lines[0]

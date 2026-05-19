"""Unit tests: GD narrative prompts (party size, no invented allies)."""
from __future__ import annotations

from waifu_bot.services.gd_narrative_ai import (
    GD_SYSTEM_PROMPT,
    build_gd_composition_instructions,
    build_user_prompt_finale,
    build_user_prompt_round,
    build_user_prompt_start,
    gd_party_size_mode,
    gd_silent_members,
)


def _solo_party() -> list[dict]:
    return [
        {
            "user_id": 305174198,
            "name": "Алиса",
            "class_id": 4,
            "race_id": 4,
            "level": 12,
            "current_hp": 80,
            "max_hp": 100,
        }
    ]


def test_gd_party_size_mode_solo_small_large() -> None:
    assert gd_party_size_mode([{"user_id": 1}]) == "solo"
    assert gd_party_size_mode([{"user_id": i} for i in range(3)]) == "small"
    assert gd_party_size_mode([{"user_id": i} for i in range(6)]) == "large"


def test_system_prompt_no_unconditional_silent_jokes() -> None:
    assert "Для каждого молчавшего" not in GD_SYSTEM_PROMPT
    assert "следуй им строго" in GD_SYSTEM_PROMPT


def test_solo_round_prompt_forbids_invented_allies() -> None:
    party = _solo_party()
    ctx = {
        "dungeon_name": "Пустыня",
        "biome_tag": "песок",
        "round": 1,
        "total_est": 10,
        "round_outcome": "ongoing",
        "party": party,
        "monsters": [{"name": "Скорпион", "level": 5, "hp": 50, "max_hp": 100}],
        "actions": [{"user_id": 305174198, "kind": "text", "damage": 20}],
        "flags": {},
        "raw_buffer_users": {"305174198": {"text_len": 42, "media": [], "silent": False}},
        "outcomes_summary": {},
    }
    prompt = build_user_prompt_round(ctx)
    assert "одиночный поход" in prompt
    assert "Алиса" in prompt
    assert "не выдумывай бездействующих" in prompt.lower() or "нет молчавших" in prompt.lower()
    assert "Для каждого молчавшего" not in prompt
    assert "Алиса (user 305174198): текстовые атаки" in prompt


def test_small_party_one_silent_named() -> None:
    party = [
        {"user_id": 1, "name": "Аня", "class_id": 1, "race_id": 1, "level": 5},
        {"user_id": 2, "name": "Бэль", "class_id": 2, "race_id": 2, "level": 6},
        {"user_id": 3, "name": "Вера", "class_id": 3, "race_id": 3, "level": 7},
    ]
    actions = [
        {"user_id": 1, "kind": "text", "damage": 10},
        {"user_id": 2, "kind": "silent"},
        {"user_id": 3, "kind": "silent"},
    ]
    block = build_gd_composition_instructions(party, actions, phase="round")
    assert "молчали" in block
    assert "Бэль" in block
    assert "Вера" in block
    assert "Аня" not in block.split("молчали")[1] or "Бэль" in block


def test_large_party_focus_limit() -> None:
    party = [{"user_id": i, "name": f"W{i}", "class_id": 1, "race_id": 1, "level": 1} for i in range(6)]
    actions = [
        {"user_id": 1, "kind": "text", "damage": 50},
        {"user_id": 2, "kind": "text", "damage": 40},
        {"user_id": 3, "kind": "silent"},
        {"user_id": 4, "kind": "silent"},
        {"user_id": 5, "kind": "silent"},
        {"user_id": 6, "kind": "silent"},
    ]
    raw = {
        "1": {"text_len": 100, "media": [], "silent": False},
        "2": {"text_len": 80, "media": [], "silent": False},
    }
    block = build_gd_composition_instructions(party, actions, phase="round", raw_buffer_users=raw)
    assert "большой отряд" in block
    assert "до 3" in block


def test_start_solo_instructions() -> None:
    prompt = build_user_prompt_start("Пещера", "темнота", _solo_party())
    assert "одиночный поход" in prompt
    assert "Алиса" in prompt
    assert "несуществующих союзников" in prompt


def test_finale_uses_party_not_raw_json_dump() -> None:
    party = _solo_party()
    ctx = {
        "dungeon_name": "Лабиринт",
        "party": party,
        "contributions": {305174198: 100.0},
    }
    prompt = build_user_prompt_finale(ctx)
    assert "ФИНАЛ ПОХОДА" in prompt
    assert "Алиса" in prompt
    assert "MVP по вкладу: Алиса" in prompt
    assert '"contributions"' not in prompt


def test_gd_silent_members_only_from_party() -> None:
    party = _solo_party()
    silent = gd_silent_members(party, [{"user_id": 999, "kind": "silent"}])
    assert silent == []

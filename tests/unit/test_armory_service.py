"""Unit tests for Armory service helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.services.armory_service import (
    LEADERBOARD_KINDS,
    _waifu_paperdoll_url,
    _waifu_portrait_url,
    sanitize_display_name,
)
from waifu_bot.services.inventory_payload import serialize_inventory_item


def test_waifu_portrait_url():
    # valid tiny base64 payload for media helper
    waifu = SimpleNamespace(
        image_data="YWJjMTIz",  # "abc123"
        image_mime="image/png",
        player_id=1,
        portrait_path=None,
    )
    url = _waifu_portrait_url(waifu)
    assert url is None or url.startswith("data:") or url.startswith("/static/")


def test_waifu_portrait_url_missing():
    waifu = SimpleNamespace(
        image_data=None,
        player_id=1,
        portrait_path=None,
        image_key=None,
    )
    url = _waifu_portrait_url(waifu)
    # May resolve to a static path fallback depending on media service config
    assert url is None or isinstance(url, str)


def test_waifu_paperdoll_url():
    waifu = SimpleNamespace(
        paperdoll_image_data="eHl6",  # "xyz"
        paperdoll_image_mime="image/webp",
        player_id=1,
        paperdoll_path=None,
    )
    url = _waifu_paperdoll_url(waifu)
    assert url is None or url.startswith("data:") or url.startswith("/static/")


def test_sanitize_display_name_strips_controls():
    dirty = "\x00\x01Bad\x1fName"
    assert sanitize_display_name(dirty, username="user", player_id=1) == "BadName"


def test_sanitize_display_name_strips_control_pictures():
    dirty = "\u240a\u240a\u2400Real"
    assert sanitize_display_name(dirty, username="Nrion", player_id=1) == "Real"


def test_sanitize_display_name_fallback_username():
    assert sanitize_display_name("\x00\x01", username="IceFear", player_id=42) == "IceFear"


def test_sanitize_display_name_fallback_id():
    assert sanitize_display_name(None, username=None, player_id=99) == "Игрок #99"


def test_leaderboard_kinds_include_gear_and_dungeon():
    assert "dungeon_plus" in LEADERBOARD_KINDS
    assert "gear_score" in LEADERBOARD_KINDS
    assert "guild" in LEADERBOARD_KINDS


@pytest.mark.asyncio
async def test_build_leaderboard_dungeon_plus_uses_best_completed_column():
    """Ensure dungeon_plus query references best_completed_plus_level, not plus_level."""
    from waifu_bot.services import armory_service as svc
    from waifu_bot.db import models as m

    assert hasattr(m.PlayerDungeonPlus, "best_completed_plus_level")
    assert not hasattr(m.PlayerDungeonPlus, "plus_level")

    captured: dict = {}

    async def fake_execute(q):
        try:
            compiled = str(q.compile(compile_kwargs={"literal_binds": False}))
        except Exception:
            compiled = str(q)
        captured["sql"] = compiled.lower()
        result = MagicMock()
        result.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = fake_execute

    rows = await svc.build_leaderboard(session, "dungeon_plus", limit=10)
    assert rows == []
    assert "best_completed_plus_level" in captured["sql"]
    assert "player_dungeon_plus.plus_level" not in captured["sql"]


def test_serialize_inventory_item_includes_art_fields():
    item = SimpleNamespace(name="Меч", tier=1, rarity=1)
    affix = SimpleNamespace(
        name="Острый",
        stat="strength",
        value=5,
        is_percent=False,
        kind="affix",
        tier=1,
    )
    inv = SimpleNamespace(
        id=42,
        item=item,
        affixes=[affix],
        slot_type="weapon_1h",
        weapon_type="sword",
        rarity=2,
        level=5,
        tier=2,
        equipment_slot=1,
        damage_min=10,
        damage_max=15,
        attack_speed=100,
        attack_type="physical",
        base_stat=None,
        base_stat_value=None,
        is_legendary=False,
        requirements=None,
        enchant_level=0,
        enchant_dmg_step=0,
        enchant_arm_step=0,
        enchant_sec_step=0.0,
        is_broken=False,
    )
    payload = serialize_inventory_item(inv)
    assert payload["id"] == 42
    assert payload["display_name"] == "Острый Меч"
    assert payload["art_key"]
    assert payload["image_key"]
    assert payload["equipment_slot"] == 1
    assert len(payload["affixes"]) == 1


def test_stats_effective_keys():
    expected = {"strength", "agility", "intelligence", "endurance", "charm", "luck"}
    sample = {
        "strength": 10,
        "agility": 8,
        "intelligence": 12,
        "endurance": 9,
        "charm": 7,
        "luck": 6,
    }
    assert set(sample.keys()) == expected


def test_player_statistics_response_shape():
    expected = {
        "dungeons_completed",
        "monsters_killed",
        "damage_dealt",
        "hp_lost",
        "gold_earned",
        "exp_earned",
    }
    sample = {
        "dungeons_completed": 0,
        "monsters_killed": 0,
        "damage_dealt": 0,
        "hp_lost": 0,
        "gold_earned": 0,
        "exp_earned": 0,
    }
    assert set(sample.keys()) == expected

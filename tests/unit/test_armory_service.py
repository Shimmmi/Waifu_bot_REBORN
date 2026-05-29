"""Unit tests for Armory service helpers."""

from types import SimpleNamespace

from waifu_bot.services.armory_service import _waifu_paperdoll_url, _waifu_portrait_url
from waifu_bot.services.inventory_payload import serialize_inventory_item


def test_waifu_portrait_url():
    waifu = SimpleNamespace(image_data="abc123", image_mime="image/png")
    assert _waifu_portrait_url(waifu) == "data:image/png;base64,abc123"


def test_waifu_portrait_url_missing():
    waifu = SimpleNamespace(image_data=None)
    assert _waifu_portrait_url(waifu) is None


def test_waifu_paperdoll_url():
    waifu = SimpleNamespace(paperdoll_image_data="xyz", paperdoll_image_mime="image/webp")
    assert _waifu_paperdoll_url(waifu) == "data:image/webp;base64,xyz"


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

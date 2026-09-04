"""One identity name across tiers 1–10; extra webp slugs in the pool."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from waifu_bot.game.drop_act_weights import ACT_RARITY_WEIGHTS
from waifu_bot.game.item_art_identities import extra_identity_seed_rows, load_identity_map
from waifu_bot.game.item_tier_stats import apply_drop_tier_to_base, level_band_for_tier
from waifu_bot.services.inventory_payload import _resolve_template_row_for_inv, _template_row_index
from waifu_bot.services.item_art import default_relative_path, derive_item_art_key
from waifu_bot.services.item_service import ItemService, _tier_from_level


def test_kinzhal_art_key_and_tier_files() -> None:
    key = derive_item_art_key("weapon_1h", "one_hand", "Кинжал", display_name="Кинжал")
    assert key.endswith("/kinzhal")
    assert default_relative_path(key, 1).endswith("/t1.webp")
    assert default_relative_path(key, 10).endswith("/t10.webp")
    assert "/t1.webp" in default_relative_path(key, 1)
    assert default_relative_path(key, 1) != default_relative_path(key, 10)


def test_apply_drop_tier_keeps_name_changes_stats() -> None:
    base = {
        "id": 1,
        "name": "Кинжал",
        "item_type": "weapon",
        "subtype": "one_hand",
        "tier": 1,
        "level_min": 1,
        "level_max": 5,
        "dmg_min": 3,
        "dmg_max": 5,
        "stat1_value": 1,
        "base_price": 8,
    }
    t1 = apply_drop_tier_to_base(base, 1)
    t10 = apply_drop_tier_to_base(base, 10)
    assert t1["name"] == t10["name"] == "Кинжал"
    assert t1["tier"] == 1
    assert t10["tier"] == 10
    assert int(t10["dmg_min"]) > int(t1["dmg_min"])
    assert level_band_for_tier(1) == (1, 5)
    assert level_band_for_tier(10) == (46, 50)
    assert t10["level_min"] == 46


def test_ilvl_maps_to_drop_tier() -> None:
    assert _tier_from_level(1) == 1
    assert _tier_from_level(5) == 1
    assert _tier_from_level(6) == 2
    assert _tier_from_level(48) == 10


def test_extra_webp_slugs_in_identity_map() -> None:
    data = load_identity_map()
    extras = data.get("extra_identities") or []
    slugs = {str(x.get("slug")) for x in extras}
    assert "luk_novichka" in slugs
    assert data.get("extra_count") == len(extras)
    assert data.get("extra_count", 0) >= 1


def test_extra_identity_seed_rows_cover_bow_slug() -> None:
    rows = extra_identity_seed_rows()
    by_family = {r["family_key"]: r for r in rows}
    assert "luk_novichka" in by_family
    row = by_family["luk_novichka"]
    assert row["tier"] == 5
    assert row["base_grade"] == 0
    assert row["item_type"] == "weapon"
    assert row["subtype"] == "bow"
    assert row["weight"] == 100


def test_pick_identity_does_not_filter_native_tier() -> None:
    async def _run() -> None:
        svc = ItemService()
        session = MagicMock()
        sqls: list[str] = []

        async def _execute(sql, params=None):
            sqls.append(str(sql))
            result = MagicMock()
            result.mappings.return_value.first.return_value = {
                "id": 1,
                "name": "Кинжал",
                "tier": 1,
                "base_grade": 0,
                "item_type": "weapon",
                "subtype": "one_hand",
                "dmg_min": 3,
                "dmg_max": 5,
                "level_min": 1,
            }
            return result

        session.execute = AsyncMock(side_effect=_execute)
        row = await svc._pick_item_base_template_for_tier_grade(
            session, tier=10, base_grade=0, item_rarity=2
        )
        assert row is not None
        blob = " ".join(sqls).lower()
        assert "tier =" not in blob
        assert ":tier" not in blob

    asyncio.run(_run())


def test_payload_resolves_identity_without_matching_native_tier() -> None:
    tpl = SimpleNamespace(
        id=7,
        name="Кинжал",
        legendary_name_ru="",
        tier=1,
        armor_base=0,
        flavor_ru="",
        secondary_bonus_type=None,
        secondary_bonus_value=0,
    )
    by_id, by_name, by_leg = _template_row_index([tpl])
    inv = SimpleNamespace(item=SimpleNamespace(name="Кинжал"), tier=10, _base_template_id=None)
    found = _resolve_template_row_for_inv(
        inv, by_id=by_id, by_name=by_name, by_legendary=by_leg
    )
    assert found is tpl


def test_early_act_legendary_weight_positive() -> None:
    for act in (1, 2, 3):
        w = ACT_RARITY_WEIGHTS[act]
        assert int(w.get("5") or 0) > 0
    # Shop remains Rare-capped in shop.py (min(rarity, 3)); these weights are dungeon chests.

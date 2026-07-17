"""Unit tests: protection stone consumption on risky enchant (+8+)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from waifu_bot.services.enchanting import build_enchant_preview, enchant_inventory_item


def _make_inv(*, enchant_level: int = 7) -> SimpleNamespace:
    item = SimpleNamespace(base_value=1000, rarity=1, level=1)
    return SimpleNamespace(
        id=101,
        player_id=1,
        item=item,
        enchant_level=enchant_level,
        is_broken=False,
        damage_min=10,
        damage_max=20,
        enchant_dmg_step=1,
        enchant_arm_step=0,
        enchant_sec_step=0.0,
        slot_type="weapon",
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
        secondary_awakened=False,
        tier=1,
        rarity=1,
        level=1,
        total_level=1,
    )


def _make_player(*, stones: int = 3, gold: int = 999999) -> SimpleNamespace:
    return SimpleNamespace(id=1, gold=gold, protection_stones=stones)


def test_enchant_success_plus8_keeps_protection_stone() -> None:
    async def _run() -> None:
        inv = _make_inv(enchant_level=7)
        player = _make_player(stones=2)
        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[inv, player])
        session.get = AsyncMock(return_value=player)
        session.commit = AsyncMock()

        cfg = {"enchant.safe_max": "7", "enchant.chance_8": "0.70"}

        with (
            patch("waifu_bot.services.enchanting.get_game_config_map", AsyncMock(return_value=cfg)),
            patch("waifu_bot.services.enchanting.get_hidden_skill_bonuses", AsyncMock(return_value={})),
            patch("waifu_bot.services.enchanting.record_hidden_gold_spend", AsyncMock()),
            patch("waifu_bot.services.enchanting.random.random", return_value=0.01),
            patch("waifu_bot.services.enchanting._maybe_awaken_fraction", AsyncMock(return_value=None)),
            patch("waifu_bot.services.enchanting.increment_skill_counter", AsyncMock()),
        ):
            res = await enchant_inventory_item(session, 101, 1, use_protection_stone=True)

        assert res.get("success") is True
        assert res.get("new_level") == 8
        assert res.get("stone_used") is False
        assert player.protection_stones == 2

    asyncio.run(_run())


def test_enchant_fail_plus8_consumes_protection_stone() -> None:
    async def _run() -> None:
        inv = _make_inv(enchant_level=7)
        player = _make_player(stones=2)
        session = AsyncMock()
        session.scalar = AsyncMock(side_effect=[inv, player])
        session.get = AsyncMock(return_value=player)
        session.commit = AsyncMock()

        cfg = {"enchant.safe_max": "7", "enchant.chance_8": "0.70"}

        with (
            patch("waifu_bot.services.enchanting.get_game_config_map", AsyncMock(return_value=cfg)),
            patch("waifu_bot.services.enchanting.get_hidden_skill_bonuses", AsyncMock(return_value={})),
            patch("waifu_bot.services.enchanting.record_hidden_gold_spend", AsyncMock()),
            patch("waifu_bot.services.enchanting.random.random", return_value=0.99),
        ):
            res = await enchant_inventory_item(session, 101, 1, use_protection_stone=True)

        assert res.get("success") is False
        assert res.get("new_level") == 6
        assert res.get("stone_used") is True
        assert player.protection_stones == 1
        assert inv.enchant_level == 6

    asyncio.run(_run())


def test_build_enchant_preview_stone_hints() -> None:
    async def _run() -> None:
        from waifu_bot.game.item_secondary import ResolvedSecondaries

        inv = _make_inv(enchant_level=7)
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=inv)

        cfg = {"enchant.safe_max": "7", "enchant.chance_8": "0.70", "enchant.sec_ratio": "0.20"}
        resolved = ResolvedSecondaries(
            armor_base=0,
            bonus_type=None,
            bonus_value=0.0,
            fraction_type="evade_pct",
            fraction_value=0.01,
            fraction_awakened=False,
        )

        with (
            patch("waifu_bot.services.enchanting.get_game_config_map", AsyncMock(return_value=cfg)),
            patch("waifu_bot.services.enchanting.get_hidden_skill_bonuses", AsyncMock(return_value={})),
            patch("waifu_bot.services.enchanting._resolve_for_inv", AsyncMock(return_value=resolved)),
        ):
            preview = await build_enchant_preview(session, 101, 1)

        assert preview.get("target_level") == 8
        assert preview.get("stone_on_success") is False
        assert preview.get("stone_on_fail") is True

    asyncio.run(_run())


def test_build_enchant_preview_max_level() -> None:
    async def _run() -> None:
        from waifu_bot.game.item_secondary import ResolvedSecondaries

        inv = _make_inv(enchant_level=10)
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=inv)

        cfg = {"enchant.safe_max": "7", "enchant.sec_ratio": "0.20"}
        resolved = ResolvedSecondaries(
            armor_base=0,
            bonus_type=None,
            bonus_value=0.0,
            fraction_type="evade_pct",
            fraction_value=0.01,
            fraction_awakened=False,
        )

        with (
            patch("waifu_bot.services.enchanting.get_game_config_map", AsyncMock(return_value=cfg)),
            patch("waifu_bot.services.enchanting._resolve_for_inv", AsyncMock(return_value=resolved)),
        ):
            preview = await build_enchant_preview(session, 101, 1)

        assert preview.get("max_reached") is True
        assert "error" not in preview
        assert preview.get("current_level") == 10
        assert preview.get("target_level") == 10
        assert preview.get("chance") is None
        assert preview.get("enchant_cost_gold") is None

    asyncio.run(_run())

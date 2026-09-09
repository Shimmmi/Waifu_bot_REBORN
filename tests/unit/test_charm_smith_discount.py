"""Charm (ОБА) gold discount for forge services and gamble."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.enchanting import apply_enchant_cost_bonus, enchant_cost_gold
from waifu_bot.services.passive_skills import (
    apply_charm_smith_discount,
    effective_main_waifu_charm,
)
from waifu_bot.services.reforge import gold_cost as reforge_gold_cost


def test_apply_charm_smith_discount_scale_and_cap():
    assert apply_charm_smith_discount(1000, 0) == 1000
    assert apply_charm_smith_discount(1000, 250) == 750
    assert apply_charm_smith_discount(1000, 400) == 600
    assert apply_charm_smith_discount(1000, 500) == 500
    assert apply_charm_smith_discount(1000, 9999) == 500
    assert apply_charm_smith_discount(361000, 400) == 216600


def test_gamble_list_and_buy_share_same_live_price():
    stored = 10_000
    charm = 400
    listed = apply_charm_smith_discount(stored, charm)
    charged = apply_charm_smith_discount(stored, charm)
    assert listed == charged == 6000


def test_enchant_stack_is_charm_then_hidden_skill():
    base = 10_000
    after_charm = apply_charm_smith_discount(base, 250)
    assert after_charm == 7500
    after_hs = apply_enchant_cost_bonus(after_charm, -10.0)
    assert after_hs == 6750
    # Both percents are multiplicative, so order does not change the gold.
    assert apply_charm_smith_discount(apply_enchant_cost_bonus(base, -10.0), 250) == after_hs


def test_legendary_plus_one_ilvl1000_with_paragon_charm():
    cfg = {
        "enchant.cost_ratio": "0.1",
        "enchant.rarity_cost_mult_5": "1.72",
        "enchant.item_level_cost_base": "1.0",
        "enchant.item_level_cost_per": "0.02",
    }
    base_value = 20 * 1000 * 5
    raw = enchant_cost_gold(base_value, 0, cfg, item_rarity=5, item_level=1000)
    assert raw == 360856
    discounted = apply_charm_smith_discount(raw, 400)
    assert discounted == apply_charm_smith_discount(360856, 400)


def test_reforge_gold_then_charm():
    inv = SimpleNamespace(total_level=200, level=200)
    raw = reforge_gold_cost(inv, {"reforge.gold_per_ilvl": "400"})
    assert raw == 80_000
    assert apply_charm_smith_discount(raw, 250) == 60_000


def test_enchant_preview_gold_uses_effective_charm_not_allocated():
    async def _run():
        from waifu_bot.services.enchanting import _enchant_gold_after_discounts

        session = AsyncMock()
        with patch(
            "waifu_bot.services.passive_skills.effective_main_waifu_charm",
            new_callable=AsyncMock,
            return_value=400,
        ), patch(
            "waifu_bot.services.enchanting.get_hidden_skill_bonuses",
            new_callable=AsyncMock,
            return_value={},
        ):
            cost, _hs = await _enchant_gold_after_discounts(session, 1, 10_000)
        assert cost == 6000

    asyncio.run(_run())


def test_effective_charm_includes_gear_transcend_and_paragon():
    async def _run():
        waifu = SimpleNamespace(charm=14)
        gear = SimpleNamespace(
            base_stat="charm",
            base_stat_value=10,
            affixes=[],
        )
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=waifu)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [gear]
        session.execute = AsyncMock(return_value=result)

        with patch(
            "waifu_bot.services.passive_skills.get_passive_skill_bonuses",
            new_callable=AsyncMock,
            return_value={"main_stats_flat": 5},
        ), patch(
            "waifu_bot.services.perfection.load_perfection_totals",
            new_callable=AsyncMock,
            return_value={"chm_flat": 235.0},
        ), patch(
            "waifu_bot.api.routes.calculate_item_bonuses",
            return_value={"charm": 10},
        ):
            ch = await effective_main_waifu_charm(session, 42)

        assert ch == 14 + 10 + 5 + 235

    asyncio.run(_run())

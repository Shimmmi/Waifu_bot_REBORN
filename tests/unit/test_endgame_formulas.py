"""Endgame economy formula unit tests (temper dust, ember ladder, GS, 2H gate, RAID)."""
from __future__ import annotations

import math
from types import SimpleNamespace

from waifu_bot.services.armory_service import compute_gear_score
from waifu_bot.services.challenge import average_ilvl_from_equipped
from waifu_bot.services.dismantle import calculate_dismantle_dust
from waifu_bot.services.reforge import _forbid as reforge_forbid
from waifu_bot.services.reforge import ember_cost
from waifu_bot.services.refine import _forbid as refine_forbid
from waifu_bot.services.temper import _raid_or_legendary
from waifu_bot.services.temper import temper_costs


_CFG = {
    "dismantle.dust_base": "5",
    "dismantle.rarity_mult_3": "1.0",
    "dismantle.rarity_mult_4": "1.6",
    "dismantle.tier_mult": "1.20",
    "temper.salvage_mult_3": "4.0",
    "temper.salvage_mult_4": "3.5",
    "temper.gold_base": "80",
    "temper.act_mult_1": "1.00",
    "temper.act_mult_2": "1.00",
    "temper.cost_growth_cap": "8",
}


def test_ember_int_ladder():
    assert ember_cost(0) == 1
    assert ember_cost(2) == 1
    assert ember_cost(3) == 2
    assert ember_cost(5) == 2
    assert ember_cost(6) == 3
    assert ember_cost(8) == 3


def test_temper_dust_grows_gold_does_not():
    inv0 = SimpleNamespace(rarity=3, tier=5, temper_reroll_count=0, total_level=20, level=20, requirements={})
    inv8 = SimpleNamespace(rarity=3, tier=5, temper_reroll_count=8, total_level=20, level=20, requirements={})
    d0, g0 = temper_costs(inv0, _CFG)
    d8, g8 = temper_costs(inv8, _CFG)
    base = calculate_dismantle_dust(rarity=3, tier=5, cfg=_CFG)
    assert d0 == int(math.floor(base * 4.0 * 1.0))
    assert d8 == int(math.floor(base * 4.0 * (1.0 + 8 * 0.15)))
    assert g0 == g8
    assert g0 == 80 * 20 * 1


def test_gear_score_adds_three_per_grade():
    inv = SimpleNamespace(tier=1, rarity=1, affixes=[], refined_grade=2)
    assert compute_gear_score([inv]) == (10 + 5) + 6


def test_avg_equipped_ilvl_2h_copies_slot2():
    two_hand = SimpleNamespace(slot_type="weapon_2h", total_level=40, level=40, equipment_slot=1)
    avg = average_ilvl_from_equipped([two_hand])
    assert avg == 40 * 2 / 6.0
    one_hand = SimpleNamespace(slot_type="weapon_1h", total_level=40, level=40, equipment_slot=1)
    avg_1h = average_ilvl_from_equipped([one_hand])
    assert avg_1h == 40 / 6.0


def test_raid_forbidden_on_smith_ops():
    raid = SimpleNamespace(rarity=6, refined_grade=0)
    assert _raid_or_legendary(raid) == "raid_forbidden"
    assert refine_forbid(raid) == "raid_forbidden"
    assert reforge_forbid(raid) == "raid_forbidden"


def test_respec_cost_base_times_level():
    from waifu_bot.services.perfection import _respec_cost

    player = SimpleNamespace(perfection_level=10)
    assert _respec_cost(player, {"perfection.respec_base_gold": "6000"}) == 60000


def test_respec_roll_permanent_only():
    import random

    from waifu_bot.services.perfection import _roll_three_bonuses

    rng = random.Random(7)
    opts = _roll_three_bonuses(
        5, {}, rng=rng, kinds={"permanent"}, exclude_ids={"gold_instant", "dust_instant"}
    )
    assert len(opts) == 3
    assert all(o["kind"] == "permanent" for o in opts)
    assert "gold_instant" not in {o["bonus_id"] for o in opts}

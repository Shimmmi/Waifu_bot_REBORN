"""Unit tests for dismantle dust formula."""

import math

from waifu_bot.services.dismantle import calculate_dismantle_dust

_DEFAULT_CFG = {
    "dismantle.dust_base": "5",
    "dismantle.rarity_mult_1": "1.0",
    "dismantle.rarity_mult_2": "1.78",
    "dismantle.rarity_mult_3": "3.16",
    "dismantle.rarity_mult_4": "5.62",
    "dismantle.rarity_mult_5": "10.0",
    "dismantle.tier_mult": "1.20",
}


def test_legendary_t1_base_dust() -> None:
    assert calculate_dismantle_dust(rarity=5, tier=1, cfg=_DEFAULT_CFG) == 50


def test_legendary_t10_dust() -> None:
    tier_factor = 1.2 ** 9
    expected = int(math.floor(5 * 10.0 * tier_factor))
    assert expected == 257
    assert calculate_dismantle_dust(rarity=5, tier=10, cfg=_DEFAULT_CFG) == 257


def test_common_t1_dust() -> None:
    assert calculate_dismantle_dust(rarity=1, tier=1, cfg=_DEFAULT_CFG) == 5


def test_enchant_level_not_in_signature() -> None:
    """Enchant must not affect dust; only rarity and tier matter."""
    assert calculate_dismantle_dust(rarity=5, tier=1, cfg=_DEFAULT_CFG) == 50


def test_rarity_geometric_progression_t1() -> None:
    dusts = [calculate_dismantle_dust(rarity=r, tier=1, cfg=_DEFAULT_CFG) for r in range(1, 6)]
    assert dusts == [5, 8, 15, 28, 50]
    assert dusts == sorted(dusts)
    for r in range(1, 6):
        mult = float(_DEFAULT_CFG[f"dismantle.rarity_mult_{r}"])
        assert dusts[r - 1] == int(math.floor(5 * mult))


def test_minimum_one_dust() -> None:
    assert calculate_dismantle_dust(rarity=1, tier=1, cfg={"dismantle.dust_base": "0.1"}) == 1

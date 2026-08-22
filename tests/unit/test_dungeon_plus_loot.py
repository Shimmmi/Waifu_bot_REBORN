"""Unit tests for Dungeon+ completion loot formulas (floor, rolls, ilvl, +31)."""

from __future__ import annotations

from types import SimpleNamespace

from waifu_bot.game.dungeon_plus_scaling import (
    apply_completion_rarity_floor,
    dungeon_plus_completion_item_level,
    dungeon_plus_completion_item_rolls,
    dungeon_plus_difficulty_params,
    dungeon_plus_drop_effective_act,
    dungeon_plus_drop_power_rank,
    dungeon_plus_extra_monsters,
    dungeon_plus_hp_target,
    dungeon_plus_rarity_floor_index,
    dungeon_plus_reward_mult,
)
from waifu_bot.services.solo_completion_loot import (
    cap_plus_item_equip_level,
    parse_drop_rule_weights,
    pick_weighted_rarity,
)


def test_rarity_floor_index_matches_params() -> None:
    assert dungeon_plus_rarity_floor_index(0) == 1
    assert dungeon_plus_rarity_floor_index(1) == 1
    assert dungeon_plus_rarity_floor_index(2) == 2
    assert dungeon_plus_rarity_floor_index(4) == 3
    assert dungeon_plus_rarity_floor_index(6) == 4
    assert dungeon_plus_rarity_floor_index(8) == 5
    assert dungeon_plus_rarity_floor_index(10) == 5
    assert dungeon_plus_difficulty_params(8)["rarity_floor"] == "legendary"


def test_apply_completion_rarity_floor_main_plus8_is_legendary() -> None:
    assert apply_completion_rarity_floor(1, 8, is_main=True) == 5
    assert apply_completion_rarity_floor(4, 8, is_main=True) == 5
    assert apply_completion_rarity_floor(5, 8, is_main=True) == 5


def test_apply_completion_rarity_floor_skips_extra_rolls_and_plus0() -> None:
    assert apply_completion_rarity_floor(1, 8, is_main=False) == 1
    assert apply_completion_rarity_floor(2, 0, is_main=True) == 2
    assert apply_completion_rarity_floor(3, 1, is_main=True) == 3


def test_completion_item_rolls_vs_extra_monsters() -> None:
    assert dungeon_plus_completion_item_rolls(0) == 1
    assert dungeon_plus_completion_item_rolls(7) == 1
    assert dungeon_plus_extra_monsters(8) == 1
    assert dungeon_plus_completion_item_rolls(8) == 2
    assert dungeon_plus_completion_item_rolls(11) == 2
    assert dungeon_plus_completion_item_rolls(12) == 3
    assert dungeon_plus_completion_item_rolls(20) == 5
    assert dungeon_plus_completion_item_rolls(24) == 5
    assert dungeon_plus_completion_item_rolls(30) == 5
    assert dungeon_plus_difficulty_params(10)["completion_item_rolls"] == 2


def test_drop_effective_act_raises_with_plus() -> None:
    assert dungeon_plus_drop_effective_act(1, 0) == 1
    assert dungeon_plus_drop_effective_act(1, 5) == 1
    assert dungeon_plus_drop_effective_act(1, 8) == 2
    assert dungeon_plus_drop_effective_act(1, 24) == 5
    assert dungeon_plus_drop_effective_act(5, 1) == 5
    assert dungeon_plus_drop_effective_act(3, 18) == 4


def test_item_level_plus10_exceeds_60() -> None:
    lvl = dungeon_plus_completion_item_level(10, 12, drop_power_rank=150, jitter=0)
    assert lvl == 150
    assert lvl > 60
    capped_base = dungeon_plus_completion_item_level(0, 55, jitter=4)
    assert capped_base <= 60


def test_item_level_uses_formula_when_rank_missing() -> None:
    assert dungeon_plus_drop_power_rank(10) == 150
    assert dungeon_plus_completion_item_level(10, 1, drop_power_rank=0, jitter=2) == 152


def test_plus_31_scales_past_30() -> None:
    assert dungeon_plus_hp_target(31) > dungeon_plus_hp_target(30)
    assert dungeon_plus_reward_mult(31) > dungeon_plus_reward_mult(30)
    assert dungeon_plus_extra_monsters(31) >= dungeon_plus_extra_monsters(30)
    assert dungeon_plus_drop_power_rank(31) > dungeon_plus_drop_power_rank(30)
    params = dungeon_plus_difficulty_params(31)
    assert params["completion_item_rolls"] == 5
    assert params["rarity_floor"] == "legendary"


def test_parse_drop_rule_weights_and_pick() -> None:
    opts = parse_drop_rule_weights({"1": 70, "2": 25, "3": 5})
    assert opts == [(1, 70), (2, 25), (3, 5)]
    assert parse_drop_rule_weights({})[0][0] == 1
    class _Rng:
        def randint(self, a: int, b: int) -> int:
            return 1

    assert pick_weighted_rarity([(1, 70), (5, 30)], rng=_Rng()) == 1


def test_dungeons_js_has_plus_stepper_for_high_unlock() -> None:
    from pathlib import Path

    src = Path("/opt/waifu-bot-REBORN/src/waifu_bot/webapp/pages/dungeons.js").read_text(
        encoding="utf-8"
    )
    assert "PLUS_LIST_STEPPER_THRESHOLD = 20" in src
    assert "appendPlusStepper" in src
    assert "Сюжетные боссы до +30" in src
    item = SimpleNamespace(required_level=148)
    inv = SimpleNamespace(requirements={"level": 148, "strength": 20}, item=item)
    cap_plus_item_equip_level(inv)
    assert inv.requirements["level"] == 60
    assert inv.requirements["strength"] == 20
    assert item.required_level == 60

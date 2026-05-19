"""Unit tests for elite affix combat helpers."""

from __future__ import annotations

import pytest

from waifu_bot.db.models.dungeon import DungeonRunMonster, MonsterAffix
from waifu_bot.game.constants import MediaType
from waifu_bot.services.combat_damage_trace import DamageTrace
from waifu_bot.services.elite_affix_combat import (
    aggregate_anti_crit,
    apply_curse_to_damage,
    apply_media_block,
    apply_regen_after_hit,
    apply_stone_skin_to_damage,
    buff_next_multipliers_for_new_monster,
    effective_crit_chance_after_anti_crit,
    stone_skin_reduction,
)


def test_stone_skin_reduction_scales_with_hp() -> None:
    assert stone_skin_reduction(0.5, 100, 100) == pytest.approx(0.5)
    assert stone_skin_reduction(0.5, 50, 100) == pytest.approx(0.25)
    assert stone_skin_reduction(0.7, 0, 100) == pytest.approx(0.0)


def test_anti_crit_effective_chance() -> None:
    assert effective_crit_chance_after_anti_crit(0.5, 0.3) == pytest.approx(0.35)
    assert effective_crit_chance_after_anti_crit(1.0, 0.15) == pytest.approx(0.85)


def test_aggregate_anti_crit() -> None:
    a1 = MonsterAffix(
        id=1,
        name="x",
        affix_group="ac1",
        tier=1,
        type="suffix",
        category="debuff",
        behavior_flag="ANTI_CRIT",
        behavior_params={"crit_reduction": 0.15},
    )
    a2 = MonsterAffix(
        id=2,
        name="y",
        affix_group="ac2",
        tier=1,
        type="suffix",
        category="debuff",
        behavior_flag="ANTI_CRIT",
        behavior_params={"crit_reduction": 0.10},
    )
    assert aggregate_anti_crit([a1, a2]) == pytest.approx(0.25)


def test_curse_persists_in_elite_state() -> None:
    m = DungeonRunMonster(
        run_id=1,
        position=1,
        name="t",
        level=1,
        difficulty=1,
        max_hp=100,
        current_hp=100,
        damage=1,
    )
    curse = MonsterAffix(
        id=10,
        name="c",
        affix_group="curse",
        tier=1,
        type="suffix",
        category="debuff",
        behavior_flag="CURSE",
        behavior_params={"dmg_reduction": 0.25},
    )
    tr = DamageTrace()
    d1 = apply_curse_to_damage(m, [curse], 100, tr)
    assert d1 == 75
    assert m.elite_state and float(m.elite_state["curse_player_dmg_mult"]) == pytest.approx(0.75)
    d2 = apply_curse_to_damage(m, [curse], 40, tr)
    assert d2 == 30


def test_stone_skin_trace() -> None:
    m = DungeonRunMonster(
        run_id=1,
        position=1,
        name="t",
        level=1,
        difficulty=1,
        max_hp=100,
        current_hp=100,
        damage=1,
    )
    sk = MonsterAffix(
        id=20,
        name="s",
        affix_group="stone_skin",
        tier=1,
        type="prefix",
        category="stat",
        behavior_flag="STONE_SKIN",
        behavior_params={"max_reduction": 0.5},
    )
    tr = DamageTrace()
    out = apply_stone_skin_to_damage(m, [sk], 100, tr)
    assert out == 50


def test_media_block_every_n() -> None:
    m = DungeonRunMonster(
        run_id=1,
        position=1,
        name="t",
        level=1,
        difficulty=1,
        max_hp=100,
        current_hp=100,
        damage=1,
        media_messages_on_monster=0,
    )
    mb = MonsterAffix(
        id=30,
        name="m",
        affix_group="mb",
        tier=1,
        type="suffix",
        category="behavior",
        behavior_flag="MEDIA_BLOCK",
        behavior_params={"every_n": 3},
    )
    tr = DamageTrace()
    d, blocked = apply_media_block(m, [mb], MediaType.PHOTO, 10, tr)
    assert d == 10 and not blocked
    d, blocked = apply_media_block(m, [mb], MediaType.PHOTO, 10, tr)
    assert d == 10 and not blocked
    d, blocked = apply_media_block(m, [mb], MediaType.PHOTO, 10, tr)
    assert d == 0 and blocked


def test_regen_every_n() -> None:
    m = DungeonRunMonster(
        run_id=1,
        position=1,
        name="t",
        level=1,
        difficulty=1,
        max_hp=100,
        current_hp=50,
        damage=1,
    )
    rg = MonsterAffix(
        id=40,
        name="r",
        affix_group="regen",
        tier=1,
        type="suffix",
        category="behavior",
        behavior_flag="REGEN",
        behavior_params={"regen_pct": 10, "every_n": 2},
    )
    apply_regen_after_hit(m, [rg], messages_after_hit=1, damage_dealt=5)
    assert m.current_hp == 50
    apply_regen_after_hit(m, [rg], messages_after_hit=2, damage_dealt=5)
    assert m.current_hp == 60


def test_buff_next_from_earlier_elite() -> None:
    e1 = DungeonRunMonster(
        run_id=1,
        position=1,
        name="e",
        level=1,
        difficulty=1,
        max_hp=100,
        current_hp=100,
        damage=10,
        is_elite=True,
        applied_affix_ids=[99],
    )
    aff = MonsterAffix(
        id=99,
        name="b",
        affix_group="buff_next",
        tier=1,
        type="suffix",
        category="behavior",
        behavior_flag="BUFF_NEXT",
        behavior_params={"hp_mult": 1.2, "dmg_mult": 1.1},
    )
    hp_m, dmg_m = buff_next_multipliers_for_new_monster([e1], {99: aff}, 2)
    assert hp_m == pytest.approx(1.2)
    assert dmg_m == pytest.approx(1.1)

    e1.current_hp = 0
    hp_m2, _ = buff_next_multipliers_for_new_monster([e1], {99: aff}, 2)
    assert hp_m2 == pytest.approx(1.0)

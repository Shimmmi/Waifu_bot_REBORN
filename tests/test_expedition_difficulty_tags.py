"""Тесты модели тегов сложности экспедиций v1.4/v1.5 (perk-only tag coverage)."""
from __future__ import annotations

from types import SimpleNamespace

from waifu_bot.db.models.waifu import WaifuClass, WaifuRace
from waifu_bot.game.expedition_difficulty_tags import (
    TAG_DARK_MAGIC,
    TAG_MONSTERS,
    TAG_UNDEAD,
    TAG_MULT_FLOOR,
    calc_perk_affix_effectiveness,
    calc_tag_coverage_ratio,
    calc_tag_effectiveness_mult,
    calc_tick_challenge_adj,
    squad_covered_tags,
    tags_for_db_affix_row,
    union_affix_tags,
    unit_coverage_detail,
    unit_covered_tags,
)
from waifu_bot.game.expedition_redesign import calc_event_damage_v14


def test_calc_tag_effectiveness_mult_empty_active():
    assert calc_tag_effectiveness_mult(frozenset(), frozenset({TAG_MONSTERS})) == 1.0


def test_calc_tag_effectiveness_mult_n3_two_covered():
    active = frozenset({TAG_MONSTERS, TAG_UNDEAD, TAG_DARK_MAGIC})
    covered = frozenset({TAG_MONSTERS, TAG_UNDEAD})
    mult = calc_tag_effectiveness_mult(active, covered)
    # Линейный бленд: 1 - 0.95 × (2/3)
    assert abs(mult - (1 - 0.95 * (2 / 3))) < 1e-9


def test_calc_tag_effectiveness_mult_n4_one_covered():
    active = frozenset({"a", "b", "c", "d"})
    covered = frozenset({"a"})
    # 1 - 0.95 × (1/4) = 0.7625
    assert abs(calc_tag_effectiveness_mult(active, covered) - 0.7625) < 1e-9


def test_calc_tag_effectiveness_mult_full_perk_coverage_hits_floor():
    active = frozenset({TAG_MONSTERS, TAG_UNDEAD})
    covered = frozenset({TAG_MONSTERS, TAG_UNDEAD})
    mult = calc_tag_effectiveness_mult(active, covered)
    assert abs(mult - TAG_MULT_FLOOR) < 1e-9


def test_dark_and_undead_suffix_tags():
    row_dark = SimpleNamespace(name="Тёмная", category="cursed", difficulty_tags=None)
    row_undead = SimpleNamespace(name="с нежитью", category="enemy", difficulty_tags=None)
    tags = union_affix_tags([row_dark, row_undead])
    assert TAG_DARK_MAGIC in tags
    assert TAG_UNDEAD in tags
    assert TAG_MONSTERS in tags


def test_angel_healer_without_priest_no_perk_tag_coverage():
    squad = [
        SimpleNamespace(race=int(WaifuRace.ANGEL), class_=int(WaifuClass.HEALER), perks=[], perk_levels={}),
    ]
    from waifu_bot.game.expedition_difficulty_tags import TAG_CURSES

    active = frozenset({TAG_DARK_MAGIC, TAG_CURSES, TAG_MONSTERS, TAG_UNDEAD})
    covered = squad_covered_tags(squad) & active
    assert covered == frozenset()
    mult = calc_tag_effectiveness_mult(active, covered, squad=squad, affix_level=1)
    assert mult == 1.0


def test_angel_healer_priest_covers_only_undead_via_perk():
    squad = [
        SimpleNamespace(
            race=int(WaifuRace.ANGEL),
            class_=int(WaifuClass.HEALER),
            perks=["priest"],
            perk_levels={"priest": 5},
        ),
    ]
    from waifu_bot.game.expedition_difficulty_tags import TAG_CURSES

    active = frozenset({TAG_DARK_MAGIC, TAG_CURSES, TAG_MONSTERS, TAG_UNDEAD})
    covered = squad_covered_tags(squad) & active
    assert TAG_UNDEAD in covered
    assert TAG_DARK_MAGIC not in covered
    mult = calc_tag_effectiveness_mult(active, covered, squad=squad, affix_level=1)
    # 1 of 4 covered at eff=1.0 → 1 - 0.95 × 0.25 = 0.7625
    assert abs(mult - 0.7625) < 1e-9


def test_calc_tag_coverage_ratio_weighted():
    active = frozenset({TAG_UNDEAD, TAG_MONSTERS})
    covered = frozenset({TAG_UNDEAD})
    squad = [
        SimpleNamespace(
            race=int(WaifuRace.HUMAN),
            class_=int(WaifuClass.WARRIOR),
            perks=["priest"],
            perk_levels={"priest": 3},
        ),
    ]
    ratio = calc_tag_coverage_ratio(active, covered, squad=squad, affix_level=5)
    # priest lv3 vs affix V on undead only: eff=0.6, 1 tag of 2 → 0.3
    assert abs(ratio - 0.3) < 1e-9


def test_calc_tick_challenge_adj_counter_minus_10():
    squad = [
        SimpleNamespace(race=int(WaifuRace.ANGEL), class_=int(WaifuClass.HEALER), perks=[], perk_levels={}),
    ]
    assert calc_tick_challenge_adj("cursed", squad, frozenset({"cursed"})) == -0.10


def test_calc_tick_challenge_adj_primary_no_counter_plus_10():
    squad = [
        SimpleNamespace(race=int(WaifuRace.HUMAN), class_=int(WaifuClass.MERCHANT), perks=[], perk_levels={}),
    ]
    assert calc_tick_challenge_adj("enemy", squad, frozenset({"enemy"})) == 0.10


def test_calc_perk_affix_effectiveness_priest_lv3_vs_affix_v():
    assert abs(calc_perk_affix_effectiveness(3, 5) - 0.6) < 1e-9
    assert calc_perk_affix_effectiveness(5, 3) == 1.0
    assert calc_perk_affix_effectiveness(0, 5) == 0.0


def test_calc_tick_challenge_adj_perk_scaled_by_affix_level():
    squad = [
        SimpleNamespace(
            race=int(WaifuRace.HUMAN),
            class_=int(WaifuClass.MERCHANT),
            perks=["priest"],
            perk_levels={"priest": 3},
        ),
    ]
    assert calc_tick_challenge_adj("enemy", squad, frozenset({"enemy"}), affix_level=5) == -0.06


def test_calc_tag_effectiveness_mult_perk_scaled():
    active = frozenset({TAG_UNDEAD, TAG_MONSTERS})
    covered = frozenset({TAG_UNDEAD})
    squad = [
        SimpleNamespace(
            race=int(WaifuRace.HUMAN),
            class_=int(WaifuClass.WARRIOR),
            perks=["priest"],
            perk_levels={"priest": 3},
        ),
    ]
    mult_full = calc_tag_effectiveness_mult(active, covered, squad=squad, affix_level=3)
    mult_weak = calc_tag_effectiveness_mult(active, covered, squad=squad, affix_level=5)
    assert mult_full < mult_weak
    # N=2, 1 covered, eff=1.0 (priest lv3/affix3) → 1 - 0.95×0.5 = 0.525
    assert abs(mult_full - 0.525) < 1e-9


def test_calc_event_damage_v14_with_tags():
    squad = [
        SimpleNamespace(
            race=int(WaifuRace.ANGEL),
            class_=int(WaifuClass.HEALER),
            perks=["priest"],
            perk_levels={"priest": 3},
        ),
    ]
    active = frozenset({TAG_DARK_MAGIC, TAG_UNDEAD, TAG_MONSTERS})
    covered = squad_covered_tags(squad) & active
    dmg = calc_event_damage_v14(
        base_hp_pct=0.15,
        squad_hp_total=300,
        active_tags=active,
        covered_tags=covered,
        challenge_cat="cursed",
        squad=squad,
        primary_categories=frozenset({"cursed", "enemy"}),
        affix_level=1,
        rand_variance=1.0,
    )
    tag_mult = calc_tag_effectiveness_mult(active, covered, squad=squad, affix_level=1)
    expected = max(1, round(300 * 0.15 * tag_mult * 0.9))
    assert dmg == expected


def test_monster_slayer_alias():
    from waifu_bot.game.expedition_difficulty_tags import PERK_TAG_COVERAGE

    assert TAG_MONSTERS in PERK_TAG_COVERAGE["monster_slayer"]


def test_unit_coverage_priest_covers_undead():
    unit = SimpleNamespace(race=int(WaifuRace.HUMAN), class_=int(WaifuClass.WARRIOR), perks=["priest"])
    detail = unit_coverage_detail(unit)
    assert TAG_UNDEAD in detail["covered_tags"]
    assert "priest" in detail["perk_tags"]
    assert TAG_UNDEAD in detail["perk_tags"]["priest"]
    assert unit_covered_tags(unit) == squad_covered_tags([unit])


def test_unit_coverage_angel_race_dark_magic_not_in_covered_tags():
    unit = SimpleNamespace(race=int(WaifuRace.ANGEL), class_=int(WaifuClass.MERCHANT), perks=[])
    detail = unit_coverage_detail(unit)
    assert TAG_DARK_MAGIC in detail["race_tags"]
    assert TAG_DARK_MAGIC not in detail["covered_tags"]
    assert detail["perk_tags"] == {}


def test_unit_coverage_knight_priest_only_perk_tags_in_covered():
    unit = SimpleNamespace(race=int(WaifuRace.HUMAN), class_=int(WaifuClass.KNIGHT), perks=["priest"])
    detail = unit_coverage_detail(unit)
    assert TAG_MONSTERS in detail["class_tags"]
    assert TAG_UNDEAD in detail["covered_tags"]
    assert TAG_MONSTERS not in detail["covered_tags"]


def test_knight_without_combat_perk_no_monsters_coverage():
    unit = SimpleNamespace(race=int(WaifuRace.HUMAN), class_=int(WaifuClass.KNIGHT), perks=[])
    assert TAG_MONSTERS not in unit_covered_tags(unit)

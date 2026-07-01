"""Юнит-тесты: эффективные статы соло-боя (game/effective_stats.py)."""

from types import SimpleNamespace

import pytest

from waifu_bot.game.effective_stats import (
    accumulate_primary_four_from_gear,
    apply_combined_stat_mult_to_four,
    apply_main_stats_flat_to_four,
    infer_weapon_attack_type,
    resolve_equipped_weapon_for_profile,
    roll_weapon_damage_and_meta,
    stat_multipliers_from_passive_hidden,
)


def test_stat_multipliers_passive_fraction_and_hidden_percent_points() -> None:
    ps = {"all_stats_pct": 0.1}
    hs = {"all_stats_pct": 5}
    pm, hm, cm = stat_multipliers_from_passive_hidden(ps, hs)
    assert pm == pytest.approx(1.1)
    assert hm == pytest.approx(1.05)
    assert cm == pytest.approx(1.155)


def test_stat_multipliers_zero_when_missing() -> None:
    pm, hm, cm = stat_multipliers_from_passive_hidden({}, {})
    assert pm == 1.0 and hm == 1.0 and cm == 1.0


def test_apply_combined_stat_mult_identity_when_one() -> None:
    out = apply_combined_stat_mult_to_four(10, 20, 30, 40, 1.0)
    assert out == (10, 20, 30, 40)


def test_apply_combined_stat_mult_rounds() -> None:
    s, a, i, l = apply_combined_stat_mult_to_four(10, 10, 10, 10, 1.2)
    assert (s, a, i, l) == (12, 12, 12, 12)


def test_apply_main_stats_flat_to_four() -> None:
    assert apply_main_stats_flat_to_four(1, 2, 3, 4, 0) == (1, 2, 3, 4)
    assert apply_main_stats_flat_to_four(1, 2, 3, 4, 100) == (101, 102, 103, 104)


def test_accumulate_primary_four_from_gear_affix() -> None:
    w = SimpleNamespace(strength=10, agility=10, intelligence=10, luck=10)
    aff = SimpleNamespace(stat="strength", value=7)
    inv = SimpleNamespace(base_stat=None, base_stat_value=None, affixes=[aff])
    s, a, i, l, bonuses = accumulate_primary_four_from_gear(w, [inv])
    assert s == 17 and a == 10 and i == 10 and l == 10
    assert bonuses == {}


def test_roll_weapon_damage_unarmed() -> None:
    out = roll_weapon_damage_and_meta([])
    assert out["weapon_damage"] == 1
    assert out["min_chars"] == 1
    assert out["attack_type"] == "melee"
    # No weapon => no breakdown components.
    assert out["weapon_damage_main"] is None
    assert out["weapon_damage_offhand"] is None


def _weapon(slot: int, dmg: int, *, slot_type: str = "weapon_1h", attack_type: str = "melee"):
    return SimpleNamespace(
        equipment_slot=slot,
        slot_type=slot_type,
        attack_type=attack_type,
        weapon_type=attack_type,
        attack_speed=1,
        damage_min=dmg,
        damage_max=dmg,
        enchant_level=0,
        is_broken=False,
        enchant_dmg_step=0,
        enchant_arm_step=0,
        enchant_sec_step=0.0,
    )


def test_roll_weapon_damage_offhand_sole_no_double_count() -> None:
    # Off-hand weapon_1h as the SOLE weapon: full roll, no +off//2 bonus on top.
    out = roll_weapon_damage_and_meta([_weapon(2, 20)])
    assert out["weapon_damage"] == 20
    assert out["weapon_damage_main"] == 0
    assert out["weapon_damage_offhand"] == 20


def test_roll_weapon_damage_mainhand_only() -> None:
    out = roll_weapon_damage_and_meta([_weapon(1, 30)])
    assert out["weapon_damage"] == 30
    assert out["weapon_damage_main"] == 30
    assert out["weapon_damage_offhand"] == 0


def test_roll_weapon_damage_dual_wield_adds_half_offhand() -> None:
    # MH 30 + OH 20 (weapon_1h) => 30 + 20//2 = 40, components 30MH + 10OH.
    out = roll_weapon_damage_and_meta([_weapon(1, 30), _weapon(2, 20)])
    assert out["weapon_damage"] == 40
    assert out["weapon_damage_main"] == 30
    assert out["weapon_damage_offhand"] == 10


def _detail_item(slot: int, dmg: int, *, slot_type: str = "weapon_1h", attack_type: str = "melee"):
    return SimpleNamespace(
        equipment_slot=slot,
        slot_type=slot_type,
        attack_type=attack_type,
        weapon_type=attack_type,
        damage_min=dmg,
        damage_max=dmg,
        base_stat=None,
        base_stat_value=None,
        affixes=[],
        enchant_level=0,
        is_broken=False,
        enchant_dmg_step=0,
        enchant_arm_step=0,
        enchant_sec_step=0.0,
    )


def _detail_item_range(
    slot: int,
    dmin: int,
    dmax: int,
    *,
    slot_type: str = "weapon_2h",
    weapon_type: str = "axe",
    attack_type: str | None = None,
    base_stat: str | None = None,
    base_stat_value: int | None = None,
    affixes: list | None = None,
):
    return SimpleNamespace(
        equipment_slot=slot,
        slot_type=slot_type,
        attack_type=attack_type,
        weapon_type=weapon_type,
        damage_min=dmin,
        damage_max=dmax,
        base_stat=base_stat,
        base_stat_value=base_stat_value,
        affixes=affixes or [],
        enchant_level=0,
        is_broken=False,
        enchant_dmg_step=0,
        enchant_arm_step=0,
        enchant_sec_step=0.0,
    )


def test_infer_weapon_attack_type_axe_is_melee() -> None:
    inv = SimpleNamespace(attack_type=None, weapon_type="axe", slot_type="weapon_2h")
    assert infer_weapon_attack_type(inv) == "melee"


def test_resolve_equipped_weapon_for_profile_2h_axe() -> None:
    axe = _detail_item_range(1, 25, 32, slot_type="weapon_2h", weapon_type="axe")
    prof = resolve_equipped_weapon_for_profile([axe])
    assert prof.attack_type == "melee"
    assert prof.damage_min == 25
    assert prof.damage_max == 32


def test_resolve_equipped_weapon_for_profile_dual_wield() -> None:
    mh = _detail_item_range(1, 30, 30, slot_type="weapon_1h", weapon_type="sword")
    oh = _detail_item_range(2, 20, 20, slot_type="weapon_1h", weapon_type="dagger")
    prof = resolve_equipped_weapon_for_profile([mh, oh])
    assert prof.damage_min == 40
    assert prof.damage_max == 40


def test_compute_details_axe_25_32_with_str_bonus() -> None:
    """STR 14 +7 from axe, weapon 25-32 → core(10, STR 21)=31 + weapon 25-32 → 56-63."""
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=14, agility=10, intelligence=11, endurance=74, charm=10, luck=12,
        level=1, current_hp=100,
    )
    axe = _detail_item_range(
        1, 25, 32, slot_type="weapon_2h", weapon_type="axe", base_stat="strength", base_stat_value=7
    )
    details = _compute_details(waifu, [axe])
    assert details["melee_damage_min"] == 56
    assert details["melee_damage_max"] == 63
    assert details["melee_damage"] == 59


def test_compute_details_hammer_melee_flat_excludes_construct() -> None:
    """War hammer 15-31, +2 STR, +65 melee flat; construct +51 must not affect general melee."""
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=14, agility=10, intelligence=11, endurance=74, charm=10, luck=12,
        level=1, current_hp=100,
    )
    affixes = [
        SimpleNamespace(stat="melee_damage_flat", value=65, is_percent=False),
        SimpleNamespace(stat="damage_vs_monster_type_flat:construct", value=51, is_percent=False),
    ]
    hammer = _detail_item_range(
        1,
        15,
        31,
        slot_type="weapon_2h",
        weapon_type="hammer",
        base_stat="strength",
        base_stat_value=2,
        affixes=affixes,
    )
    details = _compute_details(waifu, [hammer])
    assert details["melee_damage_min"] == 106
    assert details["melee_damage_max"] == 122
    assert details["melee_damage"] == 114


def test_compute_details_unarmed_str_14() -> None:
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=14, agility=10, intelligence=11, endurance=74, charm=10, luck=12,
        level=1, current_hp=100,
    )
    details = _compute_details(waifu, [])
    # BASE_SKILL_DAMAGE 10 + STR 14
    assert details["melee_damage_min"] == 24
    assert details["melee_damage_max"] == 24


def test_compute_details_reflects_equipped_weapon_damage() -> None:
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=10, agility=10, intelligence=10, endurance=10, charm=10, luck=10,
        level=1, current_hp=100,
    )
    # Melee weapon 20-30 (avg 25) should lift "Урон ближний" above the unarmed estimate,
    # while ranged/magic stay at the skill base.
    unarmed = _compute_details(waifu, [])
    mace = _detail_item(1, 25, attack_type="melee")  # avg of 25-25 = 25
    armed = _compute_details(waifu, [mace])

    assert armed["melee_damage"] > unarmed["melee_damage"]
    assert armed["melee_damage_min"] > unarmed["melee_damage_min"]
    assert armed["magic_damage"] == unarmed["magic_damage"]
    assert armed["ranged_damage"] == unarmed["ranged_damage"]


def test_compute_details_offhand_sole_weapon_reflected() -> None:
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=10, agility=10, intelligence=10, endurance=10, charm=10, luck=10,
        level=1, current_hp=100,
    )
    unarmed = _compute_details(waifu, [])
    # Sole off-hand magic weapon should lift magic damage only.
    off = _detail_item(2, 30, attack_type="magic")
    armed = _compute_details(waifu, [off])
    assert armed["magic_damage"] > unarmed["magic_damage"]
    assert armed["melee_damage"] == unarmed["melee_damage"]


def test_compute_details_magic_staff_additive() -> None:
    """INT 20 → magic 30-30; staff 3-6 +1 INT → core(10, INT 21)=31 + weapon 3-6 → 34-37."""
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=10, agility=10, intelligence=20, endurance=10, charm=10, luck=10,
        level=1, current_hp=100,
    )
    unarmed = _compute_details(waifu, [])
    assert unarmed["magic_damage_min"] == 30
    assert unarmed["magic_damage_max"] == 30

    staff = _detail_item_range(
        1,
        3,
        6,
        slot_type="weapon_2h",
        weapon_type="staff",
        attack_type="magic",
        base_stat="intelligence",
        base_stat_value=1,
    )
    armed = _compute_details(waifu, [staff])
    assert armed["magic_damage_min"] == 34
    assert armed["magic_damage_max"] == 37
    assert armed["magic_damage"] == 35
    assert armed["melee_damage_min"] == unarmed["melee_damage_min"]
    assert armed["ranged_damage_min"] == unarmed["ranged_damage_min"]


def test_compute_details_weapon_type_only_affects_matching_line() -> None:
    from waifu_bot.api.routes import _compute_details

    waifu = SimpleNamespace(
        strength=10, agility=10, intelligence=10, endurance=10, charm=10, luck=10,
        level=1, current_hp=100,
    )
    unarmed = _compute_details(waifu, [])

    melee_w = _detail_item(1, 15, attack_type="melee")
    melee_d = _compute_details(waifu, [melee_w])
    assert melee_d["melee_damage_min"] > unarmed["melee_damage_min"]
    assert melee_d["ranged_damage_min"] == unarmed["ranged_damage_min"]
    assert melee_d["magic_damage_min"] == unarmed["magic_damage_min"]

    bow = _detail_item_range(1, 12, 18, slot_type="weapon_2h", weapon_type="bow", attack_type="ranged")
    ranged_d = _compute_details(waifu, [bow])
    assert ranged_d["ranged_damage_min"] > unarmed["ranged_damage_min"]
    assert ranged_d["melee_damage_min"] == unarmed["melee_damage_min"]
    assert ranged_d["magic_damage_min"] == unarmed["magic_damage_min"]


def test_merge_passive_skips_duplicate_asp_when_flag() -> None:
    from waifu_bot.services.passive_skills import merge_passive_into_profile_details

    base = {
        "melee_damage": 100,
        "ranged_damage": 100,
        "magic_damage": 100,
        "armor": 10,
        "hp_max": 100,
        "crit_chance": 5.0,
        "dodge_chance": 5.0,
        "damage_reduction": 0.0,
        "exp_bonus": 0.0,
        "merchant_discount": 0.0,
    }
    ps = {"all_stats_pct": 0.2, "melee_dmg_pct": 0.0}
    with_asp = merge_passive_into_profile_details(dict(base), ps, skip_all_stats_pct_on_damage=False)
    assert with_asp["melee_damage"] == 120
    skip = merge_passive_into_profile_details(dict(base), ps, skip_all_stats_pct_on_damage=True)
    assert skip["melee_damage"] == 100


def test_merge_passive_full_evade_chance_in_profile() -> None:
    from waifu_bot.services.passive_skills import merge_passive_into_profile_details

    base = {"dodge_chance": 10.0}
    ps = {"full_evade_chance": 0.5}
    out = merge_passive_into_profile_details(dict(base), ps)
    assert out["full_evade_chance"] == 50.0
    assert out["dodge_chance"] == 10.0


def test_merge_passive_armor_flat_before_armor_pct() -> None:
    from waifu_bot.services.passive_skills import merge_passive_into_profile_details

    base = {"armor": 100}
    ps = {"armor_flat": 80, "armor_pct": 0.15}
    out = merge_passive_into_profile_details(dict(base), ps)
    # (100 + 80) * 1.15 = 207
    assert out["armor"] == 207

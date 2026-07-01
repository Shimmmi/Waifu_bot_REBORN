"""Unit tests for enchantment system v2 (fraction secondaries, awaken, sec_step)."""

from types import SimpleNamespace

import pytest

from waifu_bot.game.item_secondary import (
    effective_fraction_for_enchant,
    is_passive_secondary_type,
    resolve_item_secondaries,
    should_awaken_fraction_on_plus_one,
    snapshot_secondaries_from_template,
    template_row_from_mapping,
)
from waifu_bot.services.enchanting import (
    apply_enchant_chance_bonus,
    apply_enchant_cost_bonus,
    calculate_enchant_steps,
    get_effective_params,
    roll_awakened_fraction,
    secondary_bonus_value_for_enchant_step,
)


def test_enchant_sec_step_from_fraction_not_passive() -> None:
    passive_val = secondary_bonus_value_for_enchant_step("passive_node_level_add:s_shadow", 2.0)
    assert passive_val == 0.0
    steps = calculate_enchant_steps(None, None, 0, 0.01, cfg={"enchant.sec_ratio": "0.20"})
    assert steps["enchant_sec_step"] == pytest.approx(0.002)


def test_awaken_on_plus_one_sets_fraction() -> None:
    inv = SimpleNamespace(
        slot_type="ring",
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
        secondary_awakened=False,
        tier=5,
    )
    resolved = resolve_item_secondaries(inv, None)
    assert should_awaken_fraction_on_plus_one(inv, resolved) is True
    typ, val = roll_awakened_fraction(inv, {})
    assert typ
    assert val > 0


def test_awaken_does_not_remove_passive() -> None:
    inv = SimpleNamespace(
        slot_type="ring",
        secondary_bonus_type="passive_node_level_add:s_shadow",
        secondary_bonus_value=1.0,
        secondary_fraction_type="evade_pct",
        secondary_fraction_value=0.008,
        secondary_awakened=True,
        tier=5,
    )
    resolved = resolve_item_secondaries(inv, None)
    assert resolved.bonus_type == "passive_node_level_add:s_shadow"
    assert resolved.bonus_value == 1.0
    assert resolved.fraction_type == "evade_pct"
    assert resolved.fraction_value == pytest.approx(0.008)


def test_get_effective_params_stacks_fraction_enchant() -> None:
    inv = SimpleNamespace(
        enchant_level=3,
        is_broken=False,
        damage_min=None,
        damage_max=None,
        enchant_dmg_step=0,
        enchant_arm_step=0,
        enchant_sec_step=0.001,
    )
    eff = get_effective_params(inv, armor_base=0, secondary_bonus_value=0.01)
    assert eff["secondary"] == pytest.approx(0.013)


def test_resolve_template_fraction_to_fraction_channel() -> None:
    inv = SimpleNamespace(
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
        secondary_awakened=False,
    )
    template = template_row_from_mapping(
        {"armor_base": 0, "secondary_bonus_type": "crit_chance_pct", "secondary_bonus_value": 0.012}
    )
    resolved = resolve_item_secondaries(inv, template)
    assert resolved.fraction_type == "crit_chance_pct"
    assert resolved.fraction_value == pytest.approx(0.012)
    assert resolved.bonus_type is None


def test_snapshot_passive_vs_fraction() -> None:
    inv = SimpleNamespace(
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
    )
    snapshot_secondaries_from_template(
        inv,
        template_row_from_mapping(
            {"secondary_bonus_type": "passive_node_level_add:s_fire", "secondary_bonus_value": 2.0}
        ),
    )
    assert inv.secondary_bonus_type == "passive_node_level_add:s_fire"
    assert inv.secondary_fraction_type is None

    inv2 = SimpleNamespace(
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
    )
    snapshot_secondaries_from_template(
        inv2,
        template_row_from_mapping(
            {"secondary_bonus_type": "evade_pct", "secondary_bonus_value": 0.01}
        ),
    )
    assert inv2.secondary_fraction_type == "evade_pct"
    assert is_passive_secondary_type(getattr(inv2, "secondary_bonus_type", None)) is False


def test_effective_fraction_for_enchant_uses_fraction_only() -> None:
    inv = SimpleNamespace(
        secondary_bonus_type="passive_node_level_add:s_shadow",
        secondary_bonus_value=1.0,
        secondary_fraction_type="evade_pct",
        secondary_fraction_value=0.008,
        secondary_awakened=True,
    )
    resolved = resolve_item_secondaries(inv, None)
    typ, val = effective_fraction_for_enchant(inv, resolved)
    assert typ == "evade_pct"
    assert val == pytest.approx(0.008)


def test_apply_enchant_chance_bonus_negative_increases_chance() -> None:
    assert apply_enchant_chance_bonus(0.70, -18) == pytest.approx(0.88)


def test_apply_enchant_chance_bonus_zero_unchanged() -> None:
    assert apply_enchant_chance_bonus(0.70, 0) == pytest.approx(0.70)


def test_apply_enchant_chance_bonus_positive_decreases_chance() -> None:
    assert apply_enchant_chance_bonus(0.70, 10) == pytest.approx(0.60)


def test_apply_enchant_chance_bonus_clamped() -> None:
    assert apply_enchant_chance_bonus(0.95, -50) == pytest.approx(0.99)
    assert apply_enchant_chance_bonus(0.05, 50) == pytest.approx(0.01)


def test_apply_enchant_cost_bonus_negative_reduces_cost() -> None:
    assert apply_enchant_cost_bonus(1000, -18) == 820


def test_apply_enchant_cost_bonus_zero_unchanged() -> None:
    assert apply_enchant_cost_bonus(1000, 0) == 1000

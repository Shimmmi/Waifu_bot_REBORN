"""Unit tests for unified outgoing damage bonus pool."""

from waifu_bot.game.constants import MediaType
from waifu_bot.game.outgoing_damage_pool import (
    OutgoingDamageBonusInput,
    apply_outgoing_bonus_pool,
    collect_outgoing_bonus_pool,
    compute_crit_multiplier,
    legendary_crit_add,
    legendary_pool_add,
)


def test_additive_melee_passives_not_multiplicative() -> None:
    rows = [
        {"node_id": "w_bash", "name": "Удар", "effect_type": "melee_dmg_pct", "level": 3, "value": 0.06},
        {"node_id": "x", "name": "Бонус", "effect_type": "melee_dmg_pct", "level": 2, "value": 0.20},
    ]
    inp = OutgoingDamageBonusInput(
        attack_type="melee",
        media_type=MediaType.TEXT,
        passive_rows=rows,
    )
    pool, _ = collect_outgoing_bonus_pool(inp)
    assert abs(pool - 0.26) < 1e-9
    assert apply_outgoing_bonus_pool(100, pool) == 126


def test_hp_loss_additive_steps() -> None:
    inp = OutgoingDamageBonusInput(
        attack_type="melee",
        media_type=MediaType.TEXT,
        passive_bonuses={"hp_loss_dmg_pct": 0.40},
        cur_hp=50,
        max_hp=100,
    )
    pool, contribs = collect_outgoing_bonus_pool(inp)
    assert abs(pool - 2.0) < 1e-9
    assert apply_outgoing_bonus_pool(1000, pool) == 3000
    assert any(c.source == "passive_hp_loss" for c in contribs)


def test_wrath_additive_to_crit_mult_not_multiplicative() -> None:
    mult = compute_crit_multiplier(
        50,
        crit_mult_add=1.1,
        crit_dmg_melee_pct=0.75,
        attack_type="melee",
        crit_roll=2.0,
    )
    assert abs(mult - 3.85) < 1e-9
    old_style = (2.0 + 1.1) * (1.0 + 0.75)
    assert mult < old_style


def test_legendary_pool_and_crit_add() -> None:
    assert abs(legendary_pool_add(3.0, max_total_mult=10.0) - 2.0) < 1e-9
    assert abs(legendary_pool_add(12.0, max_total_mult=10.0) - 9.0) < 1e-9
    assert abs(legendary_pool_add(0.7) - (-0.3)) < 1e-9
    assert legendary_crit_add(1.5) - 0.5 < 1e-9
    assert legendary_crit_add(1.0) == 0.0


def test_debuff_pool_reduces_damage() -> None:
    assert apply_outgoing_bonus_pool(1000, -0.3) == 700


def test_pool_cap_at_max() -> None:
    from waifu_bot.game.outgoing_damage_pool import cap_bonus_pool

    assert cap_bonus_pool(15.0) == 9.0
    assert cap_bonus_pool(-2.0) == -0.9


def test_icefear_like_warrior_crit_no_longer_120k() -> None:
    """Regression: stacked warrior crit should stay well below old ~120k spikes."""
    base = 2500
    rows = [
        {"node_id": "w_bash", "name": "Удар", "effect_type": "melee_dmg_pct", "level": 3, "value": 0.22},
        {"node_id": "w_blood", "name": "Кров. ярость", "effect_type": "low_hp_dmg_pct", "level": 4, "value": 0.38},
    ]
    inp = OutgoingDamageBonusInput(
        attack_type="melee",
        media_type=MediaType.TEXT,
        passive_rows=rows,
        passive_bonuses={"hp_loss_dmg_pct": 0.40},
        hidden_bonuses={"dmg_text_pct": 15.0},
        equipment_bonuses={"media_damage_text_percent": 30},
        bestiary_dmg_pct=0.15,
        legendary_damage_pool_add=legendary_pool_add(2.5),
        cur_hp=50,
        max_hp=100,
        stun_proc=True,
    )
    pool, _ = collect_outgoing_bonus_pool(inp)
    pre_crit = apply_outgoing_bonus_pool(base, pool)
    crit_mult = compute_crit_multiplier(
        50,
        crit_mult_add=1.1,
        crit_dmg_melee_pct=0.75,
        leg_crit_add=0.5,
        attack_type="melee",
        crit_roll=2.0,
    )
    final = int(pre_crit * crit_mult)
    assert final < 75000
    assert final > 8000


def test_regression_target_crit_damage_range() -> None:
    base = 2000
    pool = 1.5
    pre_crit = apply_outgoing_bonus_pool(base, pool)
    crit_mult = compute_crit_multiplier(
        50,
        crit_mult_add=1.1,
        crit_dmg_melee_pct=0.75,
        attack_type="melee",
        crit_roll=2.0,
    )
    final = int(pre_crit * crit_mult)
    assert pre_crit == 5000
    assert abs(crit_mult - 3.85) < 1e-9
    assert 18000 <= final <= 20000

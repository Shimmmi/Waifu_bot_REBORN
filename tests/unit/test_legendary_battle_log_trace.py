"""Battle log trace for per-legendary contributions."""

from waifu_bot.game.legendary_bonuses.engine import LegendaryBonusContrib
from waifu_bot.game.outgoing_damage_pool import (
    OutgoingDamageBonusInput,
    collect_outgoing_bonus_pool,
    legendary_pool_add,
)
from waifu_bot.services.combat_damage_trace import (
    DamageTrace,
    append_legendary_post_crit_trace,
    append_unified_bonus_pool_trace,
)


def test_two_legendaries_pool_contrib_and_mult() -> None:
    contribs = [
        LegendaryBonusContrib("WRATH", 101, "Гнев", pool_pct_add=0.5),
        LegendaryBonusContrib("STACK", 102, "Стак", pool_pct_add=1.0),
    ]
    leg_pool = legendary_pool_add(1.5 * 2.0)
    inp = OutgoingDamageBonusInput(
        legendary_damage_pool_add=leg_pool,
        legendary_contribs=contribs,
    )
    pool, rows = collect_outgoing_bonus_pool(inp)
    assert abs(pool - 2.0) < 1e-9
    assert len(rows) == 2
    assert rows[0].source == "legendary:WRATH:101"
    assert rows[1].source == "legendary:STACK:102"

    trace = DamageTrace()
    append_unified_bonus_pool_trace(trace, rows, pool, 1000, 3000)
    kinds = [s["kind"] for s in trace.as_list()]
    assert kinds.count("contrib") == 2
    assert "mult" in kinds
    assert trace.as_list()[-1]["source"] == "outgoing_bonus_pool"


def test_post_crit_flat_and_extra_hits_trace() -> None:
    contribs = [
        LegendaryBonusContrib(
            "FLAT_BONUS",
            55,
            "Клинок",
            flat_add=100,
            extra_hits=[0.25],
        ),
    ]
    trace = DamageTrace()
    append_legendary_post_crit_trace(trace, 1000, 1350, contribs)
    steps = trace.as_list()
    assert len(steps) == 2
    assert steps[0]["source"] == "legendary:FLAT_BONUS:55:flat"
    assert steps[0]["delta"] == 100
    assert steps[1]["delta"] == 250

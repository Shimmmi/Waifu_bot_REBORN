"""Атрибуция источников снижения урона и входящего журнала."""

import pytest

from waifu_bot.game.constants import END_DAMAGE_REDUCTION_CAP
from waifu_bot.services.combat_contributions import (
    apply_total_reduce_cap,
    collect_endurance_dmg_reduce_contrib,
)
from waifu_bot.services.combat_damage_trace import (
    DamageTrace,
    append_passive_pool_trace,
    build_incoming_damage_breakdown_ru,
)


class _Waifu:
    def __init__(self, endurance: int) -> None:
        self.endurance = endurance


@pytest.mark.asyncio
async def test_endurance_contrib_capped_at_35_percent():
    w = _Waifu(500)
    row = await collect_endurance_dmg_reduce_contrib(w, 0)
    assert row["kind"] == "contrib"
    assert row["source"] == "stat:endurance"
    assert float(row["pct_add"]) == END_DAMAGE_REDUCTION_CAP


def test_append_passive_pool_trace_one_line_per_node():
    trace = DamageTrace()
    rows = [
        {"node_id": "w_bash", "name": "Удар", "effect_type": "melee_dmg_pct", "level": 3, "value": 0.06},
        {"node_id": "w_wrath", "name": "Гнев", "effect_type": "melee_dmg_pct", "level": 2, "value": 0.20},
    ]
    out = append_passive_pool_trace(trace, rows, "melee_dmg_pct", "ближний", "pool", 100)
    assert out == 126
    contribs = [s for s in trace.as_list() if s["kind"] == "contrib"]
    assert len(contribs) == 2
    assert contribs[0]["source"] == "passive:w_bash:melee_dmg_pct"


def test_apply_total_reduce_cap_emits_cap_step():
    contribs = [
        {"kind": "contrib", "source": "stat:endurance", "pct_add": 0.35},
        {"kind": "contrib", "source": "passive:w_iron", "pct_add": 0.08},
        {"kind": "contrib", "source": "passive:m_rune", "pct_add": 0.12},
        {"kind": "contrib", "source": "gear:ring:x", "pct_add": 0.40},
    ]
    applied, extra = apply_total_reduce_cap(contribs)
    assert applied == 0.90
    assert len(extra) == 1
    assert extra[0]["kind"] == "cap"


def test_incoming_breakdown_lists_all_dmg_reduce_sources():
    dr_contribs = [
        {"kind": "contrib", "source": "stat:endurance", "label_ru": "ВЫН", "pct_add": 0.35},
        {"kind": "contrib", "source": "passive:w_iron", "label_ru": "Железная кожа", "pct_add": 0.08},
        {"kind": "contrib", "source": "passive:m_rune", "label_ru": "Рун. броня", "pct_add": 0.12},
        {"kind": "contrib", "source": "affix:1", "label_ru": "Аффикс", "pct_add": 0.40},
    ]
    steps = build_incoming_damage_breakdown_ru(
        raw_monster_damage=100,
        armor_total=0,
        armor_dr=0.0,
        waifu_level=30,
        total_reduce=0.90,
        damage_after_mitigation=10,
        final_armor_pct=0.0,
        damage_after_final_armor=10,
        secondary_evade_triggered=False,
        full_evade_triggered=False,
        final_damage_taken=10,
        dmg_reduce_contribs=dr_contribs,
    )
    contrib_sources = [s["source"] for s in steps if s.get("kind") == "contrib"]
    assert len(contrib_sources) == 4
    assert "stat:endurance" in contrib_sources
    assert "passive:w_iron" in contrib_sources
    cap_steps = [s for s in steps if s.get("kind") == "cap"]
    assert len(cap_steps) == 1
    mit = [s for s in steps if s.get("source") == "mitigation_apply"]
    assert len(mit) == 1

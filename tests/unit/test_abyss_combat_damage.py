"""Unit tests: Abyss outgoing damage uses the same bonus pool as solo combat."""
from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import apply_equipment_damage_flats, calculate_damage_reduction
from waifu_bot.game.outgoing_damage_pool import (
    OutgoingDamageBonusInput,
    apply_outgoing_bonus_pool,
    collect_outgoing_bonus_pool,
)
from waifu_bot.services.outgoing_message_damage import (
    apply_outgoing_crit_bonuses,
    apply_outgoing_flats_and_bonus_pool,
)


def _waifu(*, hp: int = 100, max_hp: int = 100, endurance: int = 10, level: int = 50) -> SimpleNamespace:
    return SimpleNamespace(current_hp=hp, max_hp=max_hp, endurance=endurance, level=level)


def test_abyss_applies_outgoing_bonus_pool(monkeypatch) -> None:
    """Passive melee_dmg_pct must inflate abyss damage the same way as solo pool."""
    base = 1000
    ps = {"melee_dmg_pct": 0.0}
    hs: dict = {}
    eff_bonuses: dict = {}

    async def fake_passive_rows(_session, _player_id):
        return [
            {
                "node_id": "w_bash",
                "name": "Удар",
                "effect_type": "melee_dmg_pct",
                "level": 3,
                "value": 0.22,
            }
        ]

    monkeypatch.setattr(
        "waifu_bot.services.outgoing_message_damage.get_passive_contributions_for_log",
        fake_passive_rows,
    )
    monkeypatch.setattr(
        "waifu_bot.services.outgoing_message_damage.try_first_hit_hour_damage_bonus",
        AsyncMock(return_value=1.0),
    )

    session = MagicMock()

    async def run():
        return await apply_outgoing_flats_and_bonus_pool(
            session,
            player_id=1,
            damage=base,
            attack_type="melee",
            media_type=MediaType.TEXT,
            eff_bonuses=eff_bonuses,
            ps=ps,
            hs=hs,
            waifu=_waifu(),
            msg_n=0,
            monster_family=None,
            has_monster_debuff=False,
            is_group_chat=True,
            log_context="abyss",
        )

    result = asyncio.run(run())

    solo_pool, _ = collect_outgoing_bonus_pool(
        OutgoingDamageBonusInput(
            attack_type="melee",
            media_type=MediaType.TEXT,
            passive_rows=asyncio.run(fake_passive_rows(session, 1)),
            is_group_chat=True,
        )
    )
    expected = apply_outgoing_bonus_pool(base, solo_pool)
    assert result.damage == expected
    assert result.damage > base


def test_abyss_crit_uses_passive_crit_bonuses() -> None:
    """crit_mult_add and crit_dmg_melee_pct must affect abyss crit damage."""
    base = 2000
    ps = {"crit_mult_add": 1.1, "crit_dmg_melee_pct": 0.75}
    hs: dict = {}

    rng = random.Random(42)
    # Force crit via nth_hit_crit on message 2 (msg_n=1 -> 2nd hit)
    ps["nth_hit_crit"] = 2

    result = apply_outgoing_crit_bonuses(
        base,
        attack_type="melee",
        eff_strength=50,
        eff_agility=30,
        eff_luck=20,
        ps=ps,
        hs=hs,
        msg_n=1,
        rng=rng,
    )

    assert result.is_crit is True
    assert result.damage > base * 2


def test_equipment_flats_before_pool_matches_solo_order() -> None:
    """Flats then pool ordering must match solo (equipment damage_percent applies)."""
    base = 500
    bonuses = {"damage_percent": 20}
    after_flats, _ = apply_equipment_damage_flats(
        base,
        attack_type="melee",
        media_type=MediaType.TEXT,
        bonuses=bonuses,
    )
    assert after_flats == 600

    pool, _ = collect_outgoing_bonus_pool(
        OutgoingDamageBonusInput(
            attack_type="melee",
            media_type=MediaType.TEXT,
            passive_rows=[
                {
                    "node_id": "w_bash",
                    "name": "Удар",
                    "effect_type": "melee_dmg_pct",
                    "level": 1,
                    "value": 0.10,
                }
            ],
            is_group_chat=True,
        )
    )
    final = apply_outgoing_bonus_pool(after_flats, pool)
    assert final == 660


def test_abyss_retaliation_uses_main_stats_flat(monkeypatch) -> None:
    """main_stats_flat must add to endurance for incoming damage reduction."""
    from waifu_bot.services import abyss_combat as ac

    waifu = _waifu(endurance=10, level=50)
    monster = {"damage": 1000, "messages_on_monster": 5}
    eff = {"agility": 10, "luck": 10}
    ps = {"main_stats_flat": 50}
    hs: dict = {}

    async def no_dodge(*_args, **_kwargs):
        return 0.0

    async def fake_sec(*_args, **_kwargs):
        return {"armor_total": 0.0, "dmg_reduce_pct": 0.0, "evade_pct": 0.0}

    monkeypatch.setattr(ac._combat, "_dodge_fraction_for_retaliation", no_dodge)
    monkeypatch.setattr(ac._combat, "_get_waifu_armor_and_secondary", fake_sec)

    session = MagicMock()

    async def run():
        return await ac._monster_retaliation(
            session,
            player_id=1,
            waifu=waifu,
            monster=monster,
            eff=eff,
            grace=None,
            rng=random.Random(1),
            ps=ps,
            hs=hs,
        )

    dmg = asyncio.run(run())

    end_no_msf = calculate_damage_reduction(10)
    end_with_msf = calculate_damage_reduction(60)
    raw = 1000
    expected = max(1, round(raw * (1.0 - end_with_msf)))
    assert end_with_msf > end_no_msf
    assert dmg == expected

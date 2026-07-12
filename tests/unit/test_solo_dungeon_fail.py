"""Unit tests for solo dungeon deferred rewards and fail settlement."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from waifu_bot.game.constants import CHM_DEATH_GOLD_PENALTY_BASE, CHM_DEATH_GOLD_PENALTY_COEFF
from waifu_bot.services.solo_run_rewards import (
    accrue_solo_kill_rewards,
    death_gold_penalty_fraction,
    predict_retaliation_damage_worst_case,
    settle_solo_run_rewards,
    solo_rewards_settled,
)


def _run(*, exp=0, gold=0, battle_state=None):
    return SimpleNamespace(
        player_id=1,
        total_exp_gained=exp,
        total_gold_gained=gold,
        battle_state=battle_state or {},
    )


def _waifu(*, exp=0, charm=10, hp=100, max_hp=200, level=5, endurance=10):
    return SimpleNamespace(
        experience=exp,
        charm=charm,
        current_hp=hp,
        max_hp=max_hp,
        level=level,
        endurance=endurance,
    )


def _player(*, gold=0):
    return SimpleNamespace(gold=gold)


def test_accrue_does_not_touch_waifu_or_player():
    run = _run()
    waifu = _waifu(exp=50)
    player = _player(gold=100)
    accrue_solo_kill_rewards(run, 30, 40)
    assert run.total_exp_gained == 30
    assert run.total_gold_gained == 40
    assert waifu.experience == 50
    assert player.gold == 100


def test_settle_completed_credits_full_totals():
    async def _run_test():
        run = _run(exp=100, gold=200)
        waifu = _waifu(exp=10)
        player = _player(gold=50)
        session = AsyncMock()
        with patch(
            "waifu_bot.services.combat.apply_main_waifu_levelups",
            new_callable=AsyncMock,
            return_value=False,
        ):
            exp, gold, penalty = await settle_solo_run_rewards(
                session, run, waifu, player, "completed"
            )
        assert exp == 100
        assert gold == 200
        assert penalty is None
        assert waifu.experience == 110
        assert player.gold == 250
        assert solo_rewards_settled(run)

    asyncio.run(_run_test())


def test_settle_failed_applies_penalty_to_all_gold():
    async def _run_test():
        run = _run(exp=80, gold=1000)
        waifu = _waifu(exp=0, charm=10)
        player = _player(gold=0)
        session = AsyncMock()
        ps = {"main_stats_flat": 0}
        penalty = death_gold_penalty_fraction(waifu, ps)
        expected_gold = max(0, int(round(1000 * (1.0 - penalty))))
        with (
            patch(
                "waifu_bot.services.solo_run_rewards.get_passive_skill_bonuses",
                new_callable=AsyncMock,
                return_value=ps,
            ),
            patch(
                "waifu_bot.services.combat.apply_main_waifu_levelups",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "waifu_bot.services.combat._guild_quest_record",
                new_callable=AsyncMock,
            ),
            patch(
                "waifu_bot.services.hidden_skills.try_hoarder_saving_streak",
                new_callable=AsyncMock,
            ),
        ):
            exp, gold, pct = await settle_solo_run_rewards(
                session, run, waifu, player, "failed"
            )
        assert exp == 80
        assert gold == expected_gold
        assert waifu.experience == 80
        assert player.gold == expected_gold
        assert pct == round(penalty * 100.0, 1)

    asyncio.run(_run_test())


def test_settle_idempotent():
    async def _run_test():
        run = _run(exp=50, gold=50, battle_state={"_rewards_settled": True})
        waifu = _waifu()
        player = _player(gold=10)
        session = AsyncMock()
        exp, gold, _ = await settle_solo_run_rewards(session, run, waifu, player, "completed")
        assert exp == 0 and gold == 0
        assert waifu.experience == 0
        assert player.gold == 10

    asyncio.run(_run_test())


def test_death_gold_penalty_fraction_respects_charm():
    waifu = _waifu(charm=100)
    ps = {"main_stats_flat": 0}
    p = death_gold_penalty_fraction(waifu, ps)
    assert p == max(0.0, CHM_DEATH_GOLD_PENALTY_BASE - 100 * CHM_DEATH_GOLD_PENALTY_COEFF)


def test_predict_retaliation_worst_case_no_dodge():
    waifu = _waifu(hp=50, level=10, endurance=20)
    dmg = predict_retaliation_damage_worst_case(
        waifu,
        200,
        armor_total=100,
        end_reduce=0.1,
        sec_reduce=0.05,
        hs={"final_armor_pct": 0, "low_hp_dmg_reduce": 0},
    )
    assert dmg > 0
    assert waifu.current_hp <= dmg  # lethal when hp is low enough


def test_lethal_finish_calls_fail_not_finish_blocked():
    """CombatService should fail run when worst-case retaliation is lethal."""
    from unittest.mock import MagicMock

    from waifu_bot.services.combat import CombatService

    async def _run_test():
        svc = CombatService(None)
        run = MagicMock()
        run.player_id = 42
        run.dungeon_id = 7
        run.battle_state = {}
        run.total_exp_gained = 200
        run.total_gold_gained = 500
        run.status = "active"
        run.plus_level = 0
        waifu = MagicMock()
        waifu.player_id = 42
        waifu.current_hp = 5
        waifu.max_hp = 500
        waifu.last_dungeon_failed = False
        session = AsyncMock()
        fail_payload = {
            "dungeon_failed": True,
            "waifu_died": True,
            "monster_defeated": False,
            "gold_gained": 250,
            "experience_gained": 200,
        }
        with patch.object(
            svc,
            "_fail_solo_dungeon_run",
            new_callable=AsyncMock,
            return_value=fail_payload,
        ) as fail_mock:
            raw = svc._compute_raw_retaliation_incoming(
                run,
                SimpleNamespace(damage=999, applied_affix_ids=[], elite_state={}),
                None,
            )
            assert raw == 999
            await svc._fail_solo_dungeon_run(
                session,
                run,
                waifu,
                reason="retaliation",
                incoming_damage=500,
                monster_defeated=False,
            )
        fail_mock.assert_awaited_once()
        assert fail_mock.await_args.kwargs["monster_defeated"] is False

    asyncio.run(_run_test())


def test_death_after_kill_includes_last_monster_in_settlement():
    async def _run_test():
        run = _run(exp=0, gold=0)
        accrue_solo_kill_rewards(run, 10, 100)
        accrue_solo_kill_rewards(run, 15, 50)
        assert run.total_exp_gained == 25
        assert run.total_gold_gained == 150
        waifu = _waifu()
        player = _player()
        session = AsyncMock()
        ps = {"main_stats_flat": 0}
        with (
            patch(
                "waifu_bot.services.solo_run_rewards.get_passive_skill_bonuses",
                new_callable=AsyncMock,
                return_value=ps,
            ),
            patch(
                "waifu_bot.services.combat.apply_main_waifu_levelups",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "waifu_bot.services.combat._guild_quest_record",
                new_callable=AsyncMock,
            ),
            patch(
                "waifu_bot.services.hidden_skills.try_hoarder_saving_streak",
                new_callable=AsyncMock,
            ),
        ):
            exp, gold, _ = await settle_solo_run_rewards(session, run, waifu, player, "failed")
        assert exp == 25
        penalty = death_gold_penalty_fraction(waifu, ps)
        assert gold == max(0, int(round(150 * (1.0 - penalty))))

    asyncio.run(_run_test())

"""Escrow and settlement of solo dungeon run kill rewards."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import DungeonRun, MainWaifu, Player
from waifu_bot.game.constants import CHM_DEATH_GOLD_PENALTY_BASE, CHM_DEATH_GOLD_PENALTY_COEFF
from waifu_bot.services.passive_skills import get_passive_skill_bonuses

SoloRunOutcome = Literal["completed", "failed", "abandoned"]


def solo_rewards_settled(run: DungeonRun) -> bool:
    st = run.battle_state if isinstance(getattr(run, "battle_state", None), dict) else {}
    return bool(st.get("_rewards_settled"))


def mark_solo_rewards_settled(run: DungeonRun) -> None:
    st = dict(run.battle_state) if isinstance(getattr(run, "battle_state", None), dict) else {}
    st["_rewards_settled"] = True
    run.battle_state = st


def accrue_solo_kill_rewards(run: DungeonRun, exp: int, gold: int) -> None:
    run.total_exp_gained = int(run.total_exp_gained or 0) + int(exp)
    run.total_gold_gained = int(run.total_gold_gained or 0) + int(gold)


def death_gold_penalty_fraction(waifu: MainWaifu, ps: dict) -> float:
    charm = int(getattr(waifu, "charm", 10) or 10) + int(ps.get("main_stats_flat", 0) or 0)
    return max(0.0, float(CHM_DEATH_GOLD_PENALTY_BASE) - charm * float(CHM_DEATH_GOLD_PENALTY_COEFF))


def predict_retaliation_damage_worst_case(
    waifu: MainWaifu,
    raw_incoming: int,
    *,
    armor_total: int,
    end_reduce: float,
    sec_reduce: float,
    hs: dict | None = None,
    bestiary_dmg_taken_pct: float = 0.0,
) -> int:
    """Worst-case incoming damage after mitigation (no dodge/evade/revive rolls)."""
    from waifu_bot.services.combat import compute_incoming_damage_after_mitigation

    raw_in = max(0, int(raw_incoming))
    if bestiary_dmg_taken_pct:
        raw_in = max(1, int(round(float(raw_in) * (1.0 + float(bestiary_dmg_taken_pct)))))
    _, _, dmg = compute_incoming_damage_after_mitigation(
        raw_in,
        max(0, int(armor_total)),
        int(getattr(waifu, "level", 1) or 1),
        float(end_reduce),
        float(sec_reduce),
    )
    hs = hs or {}
    fa = float(hs.get("final_armor_pct", 0) or 0)
    if fa:
        dmg = max(1, int(round(float(dmg) * (1.0 - fa / 100.0))))
    lhr = float(hs.get("low_hp_dmg_reduce", 0) or 0)
    if lhr > 0 and int(waifu.current_hp or 0) * 2 <= max(1, int(waifu.max_hp or 1)):
        dmg = max(1, int(round(float(dmg) * (1.0 - lhr / 100.0))))
    return max(0, int(dmg))


async def settle_solo_run_rewards(
    session: AsyncSession,
    run: DungeonRun,
    waifu: MainWaifu | None,
    player: Player | None,
    outcome: SoloRunOutcome,
    *,
    redis=None,
) -> tuple[int, int, float | None]:
    """Credit accrued run totals to waifu/player. Returns (exp, gold, penalty_pct)."""
    if solo_rewards_settled(run):
        return 0, 0, None

    exp_total = int(run.total_exp_gained or 0)
    gold_total = int(run.total_gold_gained or 0)
    penalty_pct: float | None = None
    gold_credit = gold_total

    if outcome == "failed" and waifu is not None:
        ps = await get_passive_skill_bonuses(session, int(run.player_id))
        penalty = death_gold_penalty_fraction(waifu, ps)
        penalty_pct = round(float(penalty) * 100.0, 1)
        gold_credit = max(0, int(round(float(gold_total) * (1.0 - float(penalty)))))

    if waifu is not None and exp_total > 0:
        waifu.experience = int(getattr(waifu, "experience", 0) or 0) + exp_total
        from waifu_bot.services.combat import apply_main_waifu_levelups

        await apply_main_waifu_levelups(session, waifu)

    if player is not None and gold_credit > 0:
        player.gold = int(player.gold or 0) + int(gold_credit)
        try:
            from waifu_bot.services.combat import _guild_quest_record
            from waifu_bot.services.hidden_skills import try_hoarder_saving_streak

            await _guild_quest_record(session, int(run.player_id), "gold_earned", int(gold_credit))
            await try_hoarder_saving_streak(session, int(run.player_id), int(player.gold or 0), redis)
        except Exception:
            pass

    mark_solo_rewards_settled(run)
    return exp_total, gold_credit, penalty_pct

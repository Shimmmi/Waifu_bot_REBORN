"""Guild wars: declare, accept/decline, phase ticks, finale rewards."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Guild, GuildLevelThreshold, GuildMember, GuildWar
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map
from waifu_bot.services.guild_progress import add_gxp

logger = logging.getLogger(__name__)


def _is_leader(m: GuildMember) -> bool:
    return bool(m.is_leader)


async def search_war_targets(session: AsyncSession, player_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem or not _is_leader(mem):
        return {"error": "forbidden"}
    g = await session.get(Guild, mem.guild_id)
    if not g:
        return {"error": "no_guild"}
    thr = await session.get(GuildLevelThreshold, g.level)
    if not thr or not thr.wars_unlocked:
        return {"error": "wars_locked"}
    lo, hi = max(1, g.level - 3), min(20, g.level + 3)
    rows = (
        await session.execute(
            select(Guild).where(Guild.level.between(lo, hi), Guild.id != g.id).limit(30)
        )
    ).scalars().all()
    return {
        "targets": [{"id": x.id, "name": x.name, "tag": x.tag, "level": x.level} for x in rows],
    }


async def declare_war(
    session: AsyncSession,
    attacker_player_id: int,
    target_guild_id: int,
    stake_gold: int = 0,
) -> dict:
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == attacker_player_id))
    ).scalar_one_or_none()
    if not mem or not _is_leader(mem):
        return {"error": "forbidden"}
    atk = await session.get(Guild, mem.guild_id)
    if not atk:
        return {"error": "no_guild"}
    if atk.active_war_id:
        return {"error": "already_at_war"}
    thr = await session.get(GuildLevelThreshold, atk.level)
    if not thr or not thr.wars_unlocked:
        return {"error": "wars_locked"}
    def_g = await session.get(Guild, target_guild_id)
    if not def_g or def_g.id == atk.id:
        return {"error": "bad_target"}
    if abs(int(atk.level) - int(def_g.level)) > 3:
        return {"error": "level_range"}
    if def_g.war_decline_cooldown_until and def_g.war_decline_cooldown_until > datetime.now(timezone.utc):
        return {"error": "target_on_cooldown"}
    cfg = await get_game_config_map(session)
    rh = cfg_int(cfg, "guild_war.response_hours", 24)
    now = datetime.now(timezone.utc)
    war = GuildWar(
        guild_a_id=atk.id,
        guild_b_id=def_g.id,
        status="pending",
        stake_gold=max(0, int(stake_gold)),
        declared_at=now,
        response_deadline_at=now + timedelta(hours=rh),
    )
    session.add(war)
    await session.flush()
    atk.active_war_id = war.id
    atk.war_status = "pending"
    atk.war_opponent_id = def_g.id
    def_g.war_opponent_id = atk.id
    await session.commit()
    return {"success": True, "war_id": war.id}


async def respond_war(session: AsyncSession, player_id: int, war_id: int, accept: bool) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem or not _is_leader(mem):
        return {"error": "forbidden"}
    g = await session.get(Guild, mem.guild_id)
    war = await session.get(GuildWar, war_id)
    if not war or war.status != "pending" or war.guild_b_id != g.id:
        return {"error": "not_found"}
    now = datetime.now(timezone.utc)
    cfg = await get_game_config_map(session)
    prep_h = cfg_int(cfg, "guild_war.preparation_hours", 24)
    act_h = cfg_int(cfg, "guild_war.active_hours", 72)
    decl_h = cfg_int(cfg, "guild_war.decline_cooldown_hours", 48)
    atk = await session.get(Guild, war.guild_a_id)
    def_g = g
    if not accept:
        war.status = "ended"
        war.winner_guild_id = None
        if atk:
            atk.active_war_id = None
            atk.war_status = "none"
            atk.war_opponent_id = None
        def_g.war_decline_cooldown_until = now + timedelta(hours=decl_h)
        def_g.active_war_id = None
        def_g.war_status = "none"
        def_g.war_opponent_id = None
        await session.commit()
        return {"success": True, "accepted": False}
    war.status = "preparation"
    war.preparation_ends_at = now + timedelta(hours=prep_h)
    war.active_from = war.preparation_ends_at
    war.ends_at = war.preparation_ends_at + timedelta(hours=act_h)
    if atk:
        atk.war_status = "preparation"
        atk.war_ends_at = war.ends_at
    def_g.active_war_id = war.id
    def_g.war_status = "preparation"
    def_g.war_ends_at = war.ends_at
    await session.commit()
    return {"success": True, "accepted": True}


async def tick_war_phases(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    cfg = await get_game_config_map(session)
    q = await session.execute(select(GuildWar).where(GuildWar.status.in_(("pending", "preparation", "active"))))
    for war in q.scalars():
        a = await session.get(Guild, war.guild_a_id)
        b = await session.get(Guild, war.guild_b_id)
        if war.status == "active" and a and b:
            a.war_score = int(war.guild_a_score or 0)
            a.war_score_enemy = int(war.guild_b_score or 0)
            b.war_score = int(war.guild_b_score or 0)
            b.war_score_enemy = int(war.guild_a_score or 0)
        if war.status == "pending" and war.response_deadline_at and now >= war.response_deadline_at:
            war.status = "ended"
            if a:
                a.active_war_id = None
                a.war_status = "none"
                a.war_opponent_id = None
            if b:
                b.active_war_id = None
                b.war_status = "none"
                b.war_opponent_id = None
        elif war.status == "preparation" and war.preparation_ends_at and now >= war.preparation_ends_at:
            war.status = "active"
            if a:
                a.war_status = "active"
            if b:
                b.war_status = "active"
        elif war.status == "active" and war.ends_at and now >= war.ends_at:
            war.status = "ended"
            wa, wb = int(war.guild_a_score or 0), int(war.guild_b_score or 0)
            if wa > wb:
                war.winner_guild_id = war.guild_a_id
            elif wb > wa:
                war.winner_guild_id = war.guild_b_id
            else:
                war.winner_guild_id = None
            win_id = war.winner_guild_id
            lose_a = win_id == war.guild_b_id
            mult_w = cfg_int(cfg, "guild_war.win_gxp_mult", 200)
            mult_l = cfg_int(cfg, "guild_war.lose_gxp_mult", 50)
            if win_id:
                wg = await session.get(Guild, win_id)
                lg = await session.get(Guild, war.guild_b_id if win_id == war.guild_a_id else war.guild_a_id)
                if wg:
                    og = int(lg.level) if lg else 1
                    await add_gxp(session, wg.id, max(1, mult_w * og // 100), reason="war_win")
                    wg.trophies_count = int(wg.trophies_count or 0) + 1
                if lg:
                    await add_gxp(session, lg.id, max(1, mult_l * int(lg.level) // 100), reason="war_lose")
            if a:
                a.active_war_id = None
                a.war_status = "ended"
                a.war_opponent_id = None
                a.war_score = 0
                a.war_score_enemy = 0
            if b:
                b.active_war_id = None
                b.war_status = "ended"
                b.war_opponent_id = None
                b.war_score = 0
                b.war_score_enemy = 0
    await session.commit()


async def war_state_for_player(session: AsyncSession, player_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem:
        return {"in_guild": False}
    g = await session.get(Guild, mem.guild_id)
    if not g:
        return {"in_guild": True, "war": None}
    war = None
    if g.active_war_id:
        war = await session.get(GuildWar, g.active_war_id)
    if not war:
        q = await session.execute(
            select(GuildWar).where(GuildWar.guild_b_id == g.id, GuildWar.status == "pending").limit(1)
        )
        war = q.scalar_one_or_none()
    if not war:
        return {"in_guild": True, "war": None}
    opp_id = g.war_opponent_id or (
        war.guild_a_id if war.guild_b_id == g.id else war.guild_b_id
    )
    opp = await session.get(Guild, opp_id) if opp_id else None
    return {
        "in_guild": True,
        "war": {
            "id": war.id,
            "status": war.status,
            "our_score": g.war_score,
            "enemy_score": g.war_score_enemy,
            "opponent": {"name": opp.name, "tag": opp.tag, "level": opp.level} if opp else None,
            "ends_at": war.ends_at.isoformat() if war.ends_at else None,
            "response_deadline_at": war.response_deadline_at.isoformat()
            if war.response_deadline_at
            else None,
        },
    }


async def generate_war_narrative_batch(session: AsyncSession) -> list[tuple[int, str]]:
    """Returns (player_id, text) for DMs. Uses LLM when configured."""
    from waifu_bot.core.config import settings
    from waifu_bot.services.llm_client import has_llm_configured, post_chat_completions

    if not has_llm_configured():
        return []
    cfg = await get_game_config_map(session)
    interval_h = cfg_int(cfg, "guild_war.narrative_interval_hours", 6)
    now = datetime.now(timezone.utc)
    q = await session.execute(select(GuildWar).where(GuildWar.status == "active"))
    out: list[tuple[int, str]] = []
    for war in q.scalars():
        if war.last_narrative_at and (now - war.last_narrative_at).total_seconds() < interval_h * 3600:
            continue
        ga = await session.get(Guild, war.guild_a_id)
        gb = await session.get(Guild, war.guild_b_id)
        if not ga or not gb:
            continue
        brief = (
            f"Война {ga.name} vs {gb.name}. Счёт примерно {war.guild_a_score} — {war.guild_b_score}. "
            "Напиши 2–3 предложения хроники битвы на русском, без прямых чисел."
        )
        try:
            import httpx

            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await post_chat_completions(
                    client,
                    {
                        "model": settings.openrouter_model,
                        "messages": [
                            {"role": "system", "content": "Ты летописец гильдейской войны. Кратко, ярко."},
                            {"role": "user", "content": brief},
                        ],
                    },
                    caller="guild war narrative",
                )
                if not r.is_success:
                    text = ""
                else:
                    data = r.json()
                    text = (
                        (data.get("choices") or [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
        except Exception:
            logger.exception("war narrative failed")
            text = ""
        if text:
            war.last_narrative_at = now
            seen_pid: set[int] = set()
            for gid in (war.guild_a_id, war.guild_b_id):
                mids = (
                    await session.execute(select(GuildMember.player_id).where(GuildMember.guild_id == gid))
                ).scalars().all()
                for pid in mids:
                    pid_i = int(pid)
                    if pid_i in seen_pid:
                        continue
                    seen_pid.add(pid_i)
                    out.append((pid_i, text))
    await session.commit()
    return out

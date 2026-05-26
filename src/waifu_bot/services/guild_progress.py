"""Guild GXP, level-ups, OPG, War Score, daily caps."""
from __future__ import annotations

import copy
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    Guild,
    GuildMember,
    GuildLevelThreshold,
    GuildGxpBankDaily,
    GuildWarScoreBankDaily,
    GuildWar,
    Player,
)
from waifu_bot.services.game_config_service import get_game_config_map, cfg_int

logger = logging.getLogger(__name__)

ActivityKind = Literal[
    "gd_chat_text",
    "gd_chat_media",
    "war_chat_text",
    "war_chat_media",
]


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


async def get_player_guild_id(session: AsyncSession, player_id: int) -> int | None:
    row = await session.execute(select(GuildMember.guild_id).where(GuildMember.player_id == player_id))
    return row.scalar_one_or_none()


async def _guild_ids_for_cycle_registrations(session: AsyncSession, user_ids: list[int]) -> list[int | None]:
    out: list[int | None] = []
    for uid in user_ids:
        gid = await get_player_guild_id(session, uid)
        out.append(gid)
    return out


def _same_guild_all(guild_ids: list[int | None]) -> int | None:
    clean = [g for g in guild_ids if g is not None]
    if not clean or len(clean) != len(guild_ids):
        return None
    first = clean[0]
    if all(g == first for g in clean):
        return first
    return None


def _opg_for_reaching_level(new_level: int) -> int:
    if 2 <= new_level <= 5:
        return 1
    if 6 <= new_level <= 10:
        return 2
    if 11 <= new_level <= 15:
        return 3
    if 16 <= new_level <= 20:
        return 4
    return 0


async def _apply_levelups(session: AsyncSession, guild: Guild) -> None:
    while guild.level < 20:
        nxt = await session.get(GuildLevelThreshold, guild.level + 1)
        if not nxt:
            break
        if guild.experience < nxt.gxp_required:
            break
        guild.level += 1
        add = _opg_for_reaching_level(guild.level)
        if add:
            guild.skill_points_total += add
        logger.info("Guild %s leveled up to %s (+OPG %s)", guild.id, guild.level, add)
        try:
            from waifu_bot.services.guild_activity import log_guild_level_up

            await log_guild_level_up(session, guild.id, guild.level)
        except Exception:
            pass


async def add_gxp(session: AsyncSession, guild_id: int, amount: int, *, reason: str = "") -> None:
    if amount <= 0:
        return
    guild = await session.get(Guild, guild_id)
    if not guild:
        return
    guild.experience += amount
    await _apply_levelups(session, guild)
    logger.debug("GXP +%s guild=%s reason=%s total=%s", amount, guild_id, reason, guild.experience)


async def apply_solo_dungeon_complete_gxp(session: AsyncSession, player_id: int) -> None:
    cfg = await get_game_config_map(session)
    amt = cfg_int(cfg, "guild_gxp.solo_dungeon_complete", 10)
    gid = await get_player_guild_id(session, player_id)
    if gid and amt:
        await add_gxp(session, gid, amt, reason="solo_dungeon")
        from waifu_bot.services.guild_contribution import add_member_contribution

        await add_member_contribution(session, gid, player_id, amt, reason="solo_dungeon")


async def add_gxp_from_bank_deposit(
    session: AsyncSession,
    guild_id: int,
    gold_amount: int,
    *,
    player_id: int | None = None,
) -> None:
    cfg = await get_game_config_map(session)
    step = max(1, cfg_int(cfg, "guild_gxp.bank_gold_step", 100))
    per = cfg_int(cfg, "guild_gxp.bank_gxp_per_step", 1)
    cap = cfg_int(cfg, "guild_gxp.bank_daily_cap", 50)
    units = gold_amount // step
    if units <= 0:
        return
    day = _today_utc()
    row = (
        await session.execute(
            select(GuildGxpBankDaily).where(
                GuildGxpBankDaily.guild_id == guild_id,
                GuildGxpBankDaily.day == day,
            )
        )
    ).scalar_one_or_none()
    if not row:
        row = GuildGxpBankDaily(guild_id=guild_id, day=day, gxp_from_deposits=0)
        session.add(row)
        await session.flush()
    room = max(0, cap - row.gxp_from_deposits)
    grant = min(units * per, room)
    if grant <= 0:
        return
    row.gxp_from_deposits += grant
    await add_gxp(session, guild_id, grant, reason="bank_deposit")
    if player_id:
        from waifu_bot.services.guild_contribution import add_member_contribution

        await add_member_contribution(session, guild_id, player_id, grant, reason="bank_deposit")


async def apply_gd_chat_gxp(
    session: AsyncSession,
    player_id: int,
    *,
    text_delta: int,
    media_kinds: list[str] | None,
) -> None:
    cfg = await get_game_config_map(session)
    gid = await get_player_guild_id(session, player_id)
    if not gid:
        return
    total = 0
    if text_delta > 0:
        total += cfg_int(cfg, "guild_gxp.chat_text", 1)
    if media_kinds:
        total += cfg_int(cfg, "guild_gxp.chat_media", 2) * len(media_kinds)
    if total:
        await add_gxp(session, gid, total, reason="gd_chat")
        from waifu_bot.services.guild_contribution import add_member_contribution

        await add_member_contribution(session, gid, player_id, total, reason="gd_chat")


def _monster_xp_for_transition(
    pre_m: list[dict[str, Any]],
    post_m: list[dict[str, Any]],
    kill_gxp: int,
    boss_gxp: int,
) -> int:
    def alive_hp(m: dict[str, Any]) -> int:
        return int(m.get("hp") or 0)

    pre_map = {int(m.get("id", 0)): m for m in pre_m if int(m.get("id", 0))}
    post_map = {int(m.get("id", 0)): m for m in post_m if int(m.get("id", 0))}
    total = 0
    for mid, a in pre_map.items():
        if alive_hp(a) <= 0:
            continue
        b = post_map.get(mid)
        if b is None or alive_hp(b) <= 0:
            total += boss_gxp if bool(a.get("is_boss")) else kill_gxp
    return total


async def apply_gd_monster_kill_gxp(
    session: AsyncSession,
    registrations_user_ids: list[int],
    pre_battle_state: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Award GXP when monsters transition to dead; all registrants must share one guild."""
    cfg = await get_game_config_map(session)
    gids = await _guild_ids_for_cycle_registrations(session, registrations_user_ids)
    guild_id = _same_guild_all(gids)
    if not guild_id:
        return
    pre_m = list((pre_battle_state or {}).get("monsters") or [])
    post_m = list((result.get("monsters_json") or []))
    kill_gxp = cfg_int(cfg, "guild_gxp.gd_kill", 5)
    boss_gxp = cfg_int(cfg, "guild_gxp.gd_boss", 20)
    total = _monster_xp_for_transition(pre_m, post_m, kill_gxp, boss_gxp)
    if total:
        await add_gxp(session, guild_id, total, reason="gd_kills")


def _collect_registration_user_ids(cycle: Any) -> list[int]:
    regs = getattr(cycle, "registrations", None) or []
    return [int(r.user_id) for r in regs]


async def apply_gd_round_guild_hooks(
    session: AsyncSession,
    cycle: Any,
    pre_battle_state: dict[str, Any],
    result: dict[str, Any],
) -> None:
    await session.refresh(cycle, ["registrations"])
    uids = _collect_registration_user_ids(cycle)
    await apply_gd_monster_kill_gxp(session, uids, pre_battle_state, result)
    await apply_war_gd_kills(session, uids, pre_battle_state, result)


# --- War score ---


async def _active_war_for_guild(session: AsyncSession, guild_id: int) -> GuildWar | None:
    g = await session.get(Guild, guild_id)
    if not g or not g.active_war_id:
        return None
    w = await session.get(GuildWar, g.active_war_id)
    if not w or w.status != "active":
        return None
    return w


async def add_war_score_to_guild(session: AsyncSession, guild_id: int, amount: int) -> None:
    if amount <= 0:
        return
    war = await _active_war_for_guild(session, guild_id)
    if not war:
        return
    g = await session.get(Guild, guild_id)
    if not g:
        return
    if war.guild_a_id == guild_id:
        war.guild_a_score += amount
        g.war_score = war.guild_a_score
        other = await session.get(Guild, war.guild_b_id)
        if other:
            other.war_score_enemy = war.guild_a_score
            g.war_score_enemy = war.guild_b_score
    elif war.guild_b_id == guild_id:
        war.guild_b_score += amount
        g.war_score = war.guild_b_score
        other = await session.get(Guild, war.guild_a_id)
        if other:
            other.war_score_enemy = war.guild_b_score
            g.war_score_enemy = war.guild_a_score
    else:
        return


async def apply_war_bank_deposit(session: AsyncSession, player_id: int, gold_amount: int) -> None:
    """War score from guild bank deposit (daily cap), only if player guild in active war."""
    gid = await get_player_guild_id(session, player_id)
    if not gid:
        return
    war = await _active_war_for_guild(session, gid)
    if not war:
        return
    cfg = await get_game_config_map(session)
    step = max(1, cfg_int(cfg, "guild_war.ws_bank_gold_step", 500))
    cap = cfg_int(cfg, "guild_war.ws_bank_daily_cap", 20)
    units = gold_amount // step
    if units <= 0:
        return
    day = _today_utc()
    row = (
        await session.execute(
            select(GuildWarScoreBankDaily).where(
                GuildWarScoreBankDaily.guild_id == gid,
                GuildWarScoreBankDaily.day == day,
            )
        )
    ).scalar_one_or_none()
    if not row:
        row = GuildWarScoreBankDaily(guild_id=gid, day=day, ws_from_deposits=0)
        session.add(row)
        await session.flush()
    room = max(0, cap - row.ws_from_deposits)
    grant = min(units, room)
    if grant:
        row.ws_from_deposits += grant
        await add_war_score_to_guild(session, gid, grant)


async def apply_expedition_success_guild(session: AsyncSession, player_id: int) -> None:
    cfg = await get_game_config_map(session)
    amt = cfg_int(cfg, "guild_gxp.expedition_success", 30)
    gid = await get_player_guild_id(session, player_id)
    if gid and amt:
        await add_gxp(session, gid, amt, reason="expedition")
        from waifu_bot.services.guild_contribution import add_member_contribution

        await add_member_contribution(session, gid, player_id, amt, reason="expedition")
    await apply_war_activity(session, player_id, "expedition_success")


async def apply_war_activity(
    session: AsyncSession,
    player_id: int,
    kind: str,
    *,
    media_kinds: list[str] | None = None,
    gold_deposit: int = 0,
) -> None:
    cfg = await get_game_config_map(session)
    gid = await get_player_guild_id(session, player_id)
    if not gid:
        return
    war = await _active_war_for_guild(session, gid)
    if not war:
        return
    pts = 0
    if kind == "chat_text":
        pts = cfg_int(cfg, "guild_war.ws_chat_text", 1)
    elif kind == "chat_media" and media_kinds:
        pts = cfg_int(cfg, "guild_war.ws_chat_media", 2) * len(media_kinds)
    elif kind == "gd_kill":
        pts = cfg_int(cfg, "guild_war.ws_kill", 3)
    elif kind == "gd_boss":
        pts = cfg_int(cfg, "guild_war.ws_boss", 15)
    elif kind == "expedition_success":
        pts = cfg_int(cfg, "guild_war.ws_expedition_success", 25)
    if pts:
        await add_war_score_to_guild(session, gid, pts)
    if gold_deposit > 0:
        await apply_war_bank_deposit(session, player_id, gold_deposit)


async def apply_war_gd_kills(
    session: AsyncSession,
    registrations_user_ids: list[int],
    pre_battle_state: dict[str, Any],
    result: dict[str, Any],
) -> None:
    cfg = await get_game_config_map(session)
    gids = await _guild_ids_for_cycle_registrations(session, registrations_user_ids)
    guild_id = _same_guild_all(gids)
    if not guild_id:
        return
    pre_m = list((pre_battle_state or {}).get("monsters") or [])
    post_m = list((result.get("monsters_json") or []))
    kill_ws = cfg_int(cfg, "guild_war.ws_kill", 3)
    boss_ws = cfg_int(cfg, "guild_war.ws_boss", 15)
    pre_map = {int(m.get("id", 0)): m for m in pre_m if int(m.get("id", 0))}
    post_map = {int(m.get("id", 0)): m for m in post_m if int(m.get("id", 0))}
    total = 0
    for mid, a in pre_map.items():
        if int(a.get("hp") or 0) <= 0:
            continue
        b = post_map.get(mid)
        if b is None or int(b.get("hp") or 0) <= 0:
            total += boss_ws if bool(a.get("is_boss")) else kill_ws
    if total:
        await add_war_score_to_guild(session, guild_id, total)


async def hourly_war_online_bonus(session: AsyncSession) -> None:
    cfg = await get_game_config_map(session)
    per = cfg_int(cfg, "guild_war.ws_online_per_member", 5)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    q = await session.execute(select(GuildWar).where(GuildWar.status == "active"))
    for war in q.scalars():
        for guild_id in (war.guild_a_id, war.guild_b_id):
            mids = (
                await session.execute(select(GuildMember.player_id).where(GuildMember.guild_id == guild_id))
            ).scalars().all()
            cnt = 0
            for pid in mids:
                pl = await session.get(Player, pid)
                if pl and pl.last_active and pl.last_active >= cutoff:
                    cnt += 1
            if cnt and per:
                await add_war_score_to_guild(session, guild_id, cnt * per)


async def snapshot_battle_monsters(cycle: Any) -> dict[str, Any]:
    st = copy.deepcopy(cycle.battle_state_json or {})
    return {"monsters": copy.deepcopy(st.get("monsters") or [])}

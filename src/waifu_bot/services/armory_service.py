"""Armory data aggregation service."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.db.inventory_load_options import inventory_item_load_options
from waifu_bot.game.constants import WAIFU_CLASS_LABEL_RU, WAIFU_RACE_LABEL_RU
from waifu_bot.game.effective_stats import resolve_solo_combat_primary_four
from waifu_bot.game.main_waifu_base_stats import compute_main_waifu_base_stats
from waifu_bot.db.models.armory import PlayerBan, PlayerEventLog
from waifu_bot.db.models.guild_extended import GuildRaidStatus, GuildWarRowStatus
from waifu_bot.services.armory_access import PUBLIC_EVENT_TYPES, armory_access_level
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.passive_skills import get_passive_skill_bonuses
from waifu_bot.services.perfection import perfection_totals_dict, summarize_totals
from waifu_bot.services.player_ban import is_player_banned
from waifu_bot.services.inventory_payload import build_inventory_payloads
from waifu_bot.services.paperdoll_quota import paperdoll_generations_remaining


from waifu_bot.services.waifu_media_service import resolve_main_waifu_portrait_url

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
# Unicode "control pictures" (U+2400–U+243F) and other format/control chars
_CONTROL_PICTURES_RE = re.compile(r"[\u2400-\u243f]")

LEADERBOARD_KINDS = frozenset({
    "level",
    "gold",
    "gear_score",
    "dungeon_plus",
    "guild",
    "abyss",
    "merc_arena",
    "merc_collection",
})


def sanitize_display_name(
    name: str | None,
    *,
    username: str | None = None,
    player_id: int | None = None,
) -> str:
    """Strip control chars / control-pictures; fall back to username or player id."""
    raw = name or ""
    cleaned_chars: list[str] = []
    for ch in raw:
        cat = unicodedata.category(ch)
        if cat in ("Cc", "Cf", "Cs", "Co"):
            continue
        cleaned_chars.append(ch)
    cleaned = _CONTROL_PICTURES_RE.sub("", "".join(cleaned_chars))
    cleaned = _CTRL_RE.sub("", cleaned).strip()
    if cleaned:
        return cleaned
    un = (username or "").strip()
    if un:
        return un
    if player_id is not None:
        return f"Игрок #{player_id}"
    return "—"


def _waifu_portrait_url(waifu: m.MainWaifu) -> str | None:
    return resolve_main_waifu_portrait_url(waifu, int(waifu.player_id))


def _waifu_paperdoll_url(waifu: m.MainWaifu) -> str | None:
    from waifu_bot.api.main_waifu_media import main_waifu_profile_paperdoll_url

    return main_waifu_profile_paperdoll_url(waifu, int(waifu.player_id))


def compute_gear_score(equipped_items: list[m.InventoryItem]) -> int:
    score = 0
    for inv in equipped_items:
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 1)
        rarity = int(getattr(inv, "rarity", None) or getattr(getattr(inv, "item", None), "rarity", None) or 1)
        score += tier * 10 + rarity * 5
        affixes = getattr(inv, "affixes", None) or []
        score += len(affixes) * 2
    return score


async def recompute_and_store_gear_score(session: AsyncSession, player_id: int) -> int:
    """Recompute equipped gear score and persist on players.gear_score."""
    equipped_q = await session.execute(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.affixes), selectinload(m.InventoryItem.item))
        .where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.equipment_slot > 0,
        )
    )
    equipped = list(equipped_q.scalars().all())
    score = compute_gear_score(equipped)
    player = await session.get(m.Player, player_id)
    if player is not None:
        player.gear_score = int(score)
    return int(score)


async def recompute_all_gear_scores(session: AsyncSession, *, batch_size: int = 200) -> dict[str, int]:
    """Admin batch: recompute gear_score for all players with equipped items."""
    updated = 0
    offset = 0
    while True:
        rows = (
            await session.execute(
                select(m.Player.id).order_by(m.Player.id).offset(offset).limit(batch_size)
            )
        ).all()
        if not rows:
            break
        for (pid,) in rows:
            await recompute_and_store_gear_score(session, int(pid))
            updated += 1
        offset += batch_size
        await session.flush()
    return {"updated": updated}


def _gear_score_subquery():
    """SQL aggregate matching compute_gear_score for equipped items."""
    affix_cnt = (
        select(
            m.InventoryAffix.inventory_item_id.label("inv_id"),
            func.count().label("cnt"),
        )
        .group_by(m.InventoryAffix.inventory_item_id)
        .subquery()
    )
    item_score = (
        func.coalesce(m.InventoryItem.tier, 1) * 10
        + func.coalesce(m.InventoryItem.rarity, 1) * 5
        + func.coalesce(affix_cnt.c.cnt, 0) * 2
    )
    return (
        select(
            m.InventoryItem.player_id.label("player_id"),
            func.sum(item_score).label("gear_score"),
        )
        .outerjoin(affix_cnt, affix_cnt.c.inv_id == m.InventoryItem.id)
        .where(m.InventoryItem.equipment_slot > 0)
        .group_by(m.InventoryItem.player_id)
        .subquery()
    )


def _static_url(path: str | None) -> str | None:
    if not path:
        return None
    p = path.strip()
    if not p:
        return None
    if p.startswith("/"):
        return p
    return f"/static/{p}"



async def load_player_bundle(session: AsyncSession, tg_id: int) -> tuple[m.Player | None, m.MainWaifu | None]:
    result = await session.execute(
        select(m.Player)
        .options(
            selectinload(m.Player.main_waifu),
            selectinload(m.Player.guild_membership).selectinload(m.GuildMember.guild),
        )
        .where(m.Player.id == tg_id)
    )
    player = result.scalar_one_or_none()
    waifu = player.main_waifu if player else None
    return player, waifu


async def build_public_summary(
    session: AsyncSession,
    tg_id: int,
    viewer_tg_id: int | None,
) -> dict[str, Any] | None:
    player, waifu = await load_player_bundle(session, tg_id)
    if not player:
        return None

    access = armory_access_level(viewer_tg_id, tg_id)
    banned = await is_player_banned(session, tg_id)

    equipped_q = await session.execute(
        select(m.InventoryItem)
        .options(*inventory_item_load_options())
        .where(
            m.InventoryItem.player_id == tg_id,
            m.InventoryItem.equipment_slot > 0,
        )
    )
    equipped = list(equipped_q.scalars().all())
    live_gs = compute_gear_score(equipped)
    stored_gs = int(getattr(player, "gear_score", 0) or 0)
    gear_score = live_gs if live_gs else stored_gs

    guild_info = None
    if player.guild_membership and player.guild_membership.guild:
        g = player.guild_membership.guild
        guild_info = {
            "id": g.id,
            "name": g.name,
            "tag": g.tag,
            "level": g.level,
            "is_leader": player.guild_membership.is_leader,
            "is_officer": player.guild_membership.is_officer,
        }

    recent_runs_q = await session.execute(
        select(m.DungeonRun, m.Dungeon.name)
        .join(m.Dungeon, m.Dungeon.id == m.DungeonRun.dungeon_id)
        .where(m.DungeonRun.player_id == tg_id, m.DungeonRun.status.in_(("completed", "failed")))
        .order_by(m.DungeonRun.ended_at.desc().nullslast(), m.DungeonRun.started_at.desc())
        .limit(5)
    )
    recent_dungeons = [
        {
            "dungeon_name": name,
            "status": run.status,
            "plus_level": run.plus_level,
            "finished_at": (run.ended_at or run.started_at).isoformat() if (run.ended_at or run.started_at) else None,
        }
        for run, name in recent_runs_q.all()
    ]

    perfection_level = int(getattr(player, "perfection_level", 0) or 0)
    out: dict[str, Any] = {
        "telegram_id": tg_id,
        "username": player.username,
        "first_name": player.first_name,
        "viewer_access_level": access,
        "banned": banned,
        "created_at": player.created_at.isoformat() if player.created_at else None,
        "last_active": player.last_active.isoformat() if player.last_active else None,
        "current_act": player.current_act,
        "max_act": player.max_act,
        "gold": player.gold,
        "gear_score": gear_score,
        "guild": guild_info,
        "recent_dungeons": recent_dungeons,
        "has_character": waifu is not None,
        "perfection_level": perfection_level,
        "perfection_bonuses_summary": (
            summarize_totals(perfection_totals_dict(player)) if perfection_level > 0 else []
        ),
    }

    if waifu:
        out["character"] = {
            "name": waifu.name,
            "race": waifu.race,
            "race_label": WAIFU_RACE_LABEL_RU.get(waifu.race, str(waifu.race)),
            "class": waifu.class_,
            "class_label": WAIFU_CLASS_LABEL_RU.get(waifu.class_, str(waifu.class_)),
            "level": waifu.level,
            "max_hp": waifu.max_hp,
        }
        portrait_url = _waifu_portrait_url(waifu)
        if portrait_url:
            out["character"]["portrait_url"] = portrait_url
        paperdoll_url = _waifu_paperdoll_url(waifu)
        if paperdoll_url:
            out["character"]["paperdoll_url"] = paperdoll_url
        if access in ("owner", "admin"):
            out["character"]["current_hp"] = waifu.current_hp
            out["character"]["experience"] = waifu.experience
            out["character"]["energy"] = waifu.energy
            out["character"]["max_energy"] = waifu.max_energy
        if access == "admin":
            out["character"]["paperdoll_bonus_generations"] = int(
                waifu.paperdoll_bonus_generations or 0
            )
            out["character"]["paperdoll_generations_remaining"] = paperdoll_generations_remaining(
                waifu
            )

        equipped_payloads = await build_inventory_payloads(session, equipped)
        out["equipped_items"] = equipped_payloads

        stats_detail = await build_stats_detail(session, tg_id)
        if stats_detail and stats_detail.get("effective"):
            out["stats_effective"] = stats_detail["effective"]

    return out


async def build_stats_detail(session: AsyncSession, tg_id: int) -> dict[str, Any] | None:
    player, waifu = await load_player_bundle(session, tg_id)
    if not player or not waifu:
        return None

    base = compute_main_waifu_base_stats(waifu.race, waifu.class_)
    passive = await get_passive_skill_bonuses(session, tg_id)
    hidden = await get_hidden_skill_bonuses(session, tg_id)
    eff = await resolve_solo_combat_primary_four(session, tg_id, waifu)

    total_bonuses = {
        "strength": int(passive.get("strength", 0) + hidden.get("strength", 0)),
        "agility": int(passive.get("agility", 0) + hidden.get("agility", 0)),
        "intelligence": int(passive.get("intelligence", 0) + hidden.get("intelligence", 0)),
        "endurance": int(passive.get("endurance", 0) + hidden.get("endurance", 0)),
        "charm": int(passive.get("charm", 0) + hidden.get("charm", 0)),
        "luck": int(passive.get("luck", 0) + hidden.get("luck", 0)),
    }

    return {
        "base": {
            "strength": int(waifu.strength),
            "agility": int(waifu.agility),
            "intelligence": int(waifu.intelligence),
            "endurance": int(waifu.endurance),
            "charm": int(waifu.charm),
            "luck": int(waifu.luck),
        },
        "race_class_base": base,
        "effective": {
            "strength": eff.strength,
            "agility": eff.agility,
            "intelligence": eff.intelligence,
            "endurance": int(waifu.endurance) + total_bonuses["endurance"],
            "charm": int(waifu.charm) + total_bonuses["charm"],
            "luck": eff.luck,
        },
        "bonuses": total_bonuses,
        "max_hp": waifu.max_hp,
        "current_hp": waifu.current_hp,
    }


async def build_inventory_list(session: AsyncSession, tg_id: int) -> list[dict[str, Any]]:
    result = await session.execute(
        select(m.InventoryItem)
        .options(*inventory_item_load_options())
        .where(m.InventoryItem.player_id == tg_id)
        .order_by(m.InventoryItem.equipment_slot.desc(), m.InventoryItem.id)
    )
    items = list(result.scalars().all())
    return await build_inventory_payloads(session, items)


async def build_dungeon_history(
    session: AsyncSession,
    tg_id: int,
    *,
    detailed: bool,
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = (
        select(m.DungeonRun, m.Dungeon.name)
        .join(m.Dungeon, m.Dungeon.id == m.DungeonRun.dungeon_id)
        .where(m.DungeonRun.player_id == tg_id)
        .order_by(m.DungeonRun.ended_at.desc().nullslast(), m.DungeonRun.started_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    result = []
    for run, dungeon_name in rows:
        entry: dict[str, Any] = {
            "run_id": run.id,
            "dungeon_name": dungeon_name,
            "status": run.status,
            "plus_level": run.plus_level,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": (run.ended_at or run.started_at).isoformat() if (run.ended_at or run.started_at) else None,
        }
        if detailed:
            entry.update({
                "total_damage_dealt": run.total_damage_dealt,
                "total_gold_gained": run.total_gold_gained,
                "total_exp_gained": run.total_exp_gained,
                "waifu_hp_lost": run.waifu_hp_lost,
            })
        result.append(entry)
    return result


async def build_player_achievements(session: AsyncSession, tg_id: int) -> list[dict[str, Any]]:
    achievements: list[dict[str, Any]] = []

    hs_rows = (
        await session.execute(
            select(m.PlayerHiddenSkill, m.HiddenSkillDefinition)
            .join(
                m.HiddenSkillDefinition,
                m.HiddenSkillDefinition.id == m.PlayerHiddenSkill.skill_id,
            )
            .where(
                m.PlayerHiddenSkill.player_id == tg_id,
                m.PlayerHiddenSkill.level >= 1,
            )
            .order_by(m.PlayerHiddenSkill.unlocked_at.desc().nullslast())
        )
    ).all()
    for row, defn in hs_rows:
        achievements.append({
            "kind": "hidden_skill",
            "id": defn.id,
            "name": defn.name,
            "icon": defn.icon,
            "level": int(row.level),
            "max_level": 5,
            "category": defn.category,
            "earned_at": row.unlocked_at.isoformat() if row.unlocked_at else None,
        })

    sb_rows = (
        await session.execute(
            select(m.PlayerStoryBossFirstKill, m.StoryBossDefinition)
            .join(
                m.StoryBossDefinition,
                m.StoryBossDefinition.id == m.PlayerStoryBossFirstKill.story_boss_definition_id,
            )
            .where(m.PlayerStoryBossFirstKill.player_id == tg_id)
            .order_by(m.PlayerStoryBossFirstKill.killed_at.desc())
        )
    ).all()
    for fk, defn in sb_rows:
        achievements.append({
            "kind": "story_boss",
            "id": str(defn.id),
            "name": defn.name,
            "act": defn.act,
            "plus_tier": defn.plus_tier,
            "earned_at": fk.killed_at.isoformat() if fk.killed_at else None,
        })

    player = await session.get(m.Player, tg_id)
    if player:
        if player.secret_echo_boss_defeated:
            achievements.append({
                "kind": "secret_echo",
                "id": "defeated",
                "name": "Победа над эхом",
            })
        elif player.secret_echo_boss_unlocked:
            achievements.append({
                "kind": "secret_echo",
                "id": "unlocked",
                "name": "Эхо пробуждено",
            })

    return achievements


async def build_event_feed(
    session: AsyncSession,
    tg_id: int,
    *,
    public_only: bool,
    cursor: int | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    q = (
        select(PlayerEventLog)
        .where(PlayerEventLog.player_id == tg_id)
        .order_by(PlayerEventLog.id.desc())
        .limit(limit + 1)
    )
    if public_only:
        q = q.where(PlayerEventLog.event_type.in_(PUBLIC_EVENT_TYPES))
    if cursor:
        q = q.where(PlayerEventLog.id < cursor)

    rows = list((await session.execute(q)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = rows[-1].id if has_more and rows else None
    achievements = await build_player_achievements(session, tg_id)
    return {
        "achievements": achievements,
        "items": [
            {
                "id": r.id,
                "event_type": r.event_type,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
    }


async def search_players(session: AsyncSession, query: str, limit: int = 20) -> list[dict[str, Any]]:
    q = query.strip()
    if not q:
        return []

    stmt = (
        select(m.Player, m.MainWaifu)
        .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
        .limit(limit)
    )
    if q.isdigit():
        stmt = stmt.where(or_(m.Player.id == int(q), m.Player.username.ilike(f"%{q}%")))
    else:
        clean = q.lstrip("@")
        stmt = stmt.where(
            or_(
                m.Player.username.ilike(f"%{clean}%"),
                m.Player.first_name.ilike(f"%{q}%"),
            )
        )

    rows = (await session.execute(stmt)).all()
    return [
        {
            "telegram_id": p.id,
            "username": p.username,
            "first_name": p.first_name,
            "character_name": sanitize_display_name(
                w.name if w else None, username=p.username, player_id=p.id
            ),
            "level": w.level if w else None,
        }
        for p, w in rows
    ]


def _player_lb_row(
    tid: int,
    username: str | None,
    name: str | None,
    value: int,
    *,
    level: int | None = None,
) -> dict[str, Any]:
    return {
        "telegram_id": tid,
        "username": username,
        "character_name": sanitize_display_name(name, username=username, player_id=tid),
        "level": level,
        "value": int(value or 0),
    }


async def build_leaderboard(session: AsyncSession, kind: str, limit: int = 50) -> list[dict[str, Any]]:
    if kind == "level":
        q = (
            select(m.Player.id, m.Player.username, m.MainWaifu.name, m.MainWaifu.level)
            .join(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .order_by(m.MainWaifu.level.desc(), m.MainWaifu.experience.desc(), m.Player.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            _player_lb_row(tid, un, name, lvl, level=lvl)
            for tid, un, name, lvl in rows
        ]

    if kind == "gold":
        q = (
            select(m.Player.id, m.Player.username, m.MainWaifu.name, m.MainWaifu.level, m.Player.gold)
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .order_by(m.Player.gold.desc(), m.Player.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            _player_lb_row(tid, un, name, gold, level=lvl)
            for tid, un, name, lvl, gold in rows
        ]

    if kind == "gear_score":
        q = (
            select(
                m.Player.id,
                m.Player.username,
                m.MainWaifu.name,
                m.MainWaifu.level,
                m.Player.gear_score,
            )
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .where(m.Player.gear_score > 0)
            .order_by(m.Player.gear_score.desc(), m.Player.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            _player_lb_row(tid, un, name, int(gs or 0), level=lvl)
            for tid, un, name, lvl, gs in rows
        ]

    if kind == "abyss":
        from waifu_bot.services.abyss_service import week_start_msk

        ws = week_start_msk()
        q = (
            select(
                m.Player.id,
                m.Player.username,
                m.MainWaifu.name,
                m.MainWaifu.level,
                m.AbyssWeeklyLeaderboard.max_floor,
            )
            .join(
                m.AbyssWeeklyLeaderboard,
                m.AbyssWeeklyLeaderboard.player_id == m.Player.id,
            )
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .where(m.AbyssWeeklyLeaderboard.week_start == ws)
            .order_by(
                m.AbyssWeeklyLeaderboard.max_floor.desc(),
                m.Player.id.asc(),
            )
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            _player_lb_row(tid, un, name, int(floor or 0), level=lvl)
            for tid, un, name, lvl, floor in rows
        ]

    if kind == "dungeon_plus":
        max_best = func.max(m.PlayerDungeonPlus.best_completed_plus_level)
        max_unlocked = func.max(m.PlayerDungeonPlus.unlocked_plus_level)
        q = (
            select(
                m.Player.id,
                m.Player.username,
                m.MainWaifu.name,
                m.MainWaifu.level,
                max_best.label("max_plus"),
            )
            .join(m.PlayerDungeonPlus, m.PlayerDungeonPlus.player_id == m.Player.id)
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .group_by(m.Player.id, m.Player.username, m.MainWaifu.name, m.MainWaifu.level)
            .order_by(max_best.desc(), max_unlocked.desc(), m.Player.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            _player_lb_row(tid, un, name, int(mp or 0), level=lvl)
            for tid, un, name, lvl, mp in rows
        ]

    if kind == "guild":
        member_count = (
            select(m.GuildMember.guild_id.label("guild_id"), func.count().label("cnt"))
            .group_by(m.GuildMember.guild_id)
            .subquery()
        )
        q = (
            select(
                m.Guild.id,
                m.Guild.name,
                m.Guild.tag,
                m.Guild.level,
                m.Guild.experience,
                m.Guild.trophies_count,
                func.coalesce(member_count.c.cnt, 0).label("member_count"),
            )
            .outerjoin(member_count, member_count.c.guild_id == m.Guild.id)
            .order_by(m.Guild.level.desc(), m.Guild.experience.desc(), m.Guild.id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            {
                "guild_id": gid,
                "name": name,
                "tag": tag,
                "level": lvl,
                "experience": xp,
                "trophies": int(trophies or 0),
                "member_count": int(mc or 0),
                "value": lvl,
            }
            for gid, name, tag, lvl, xp, trophies, mc in rows
        ]

    if kind == "merc_arena":
        from waifu_bot.db.models.tavern import TavernState

        q = (
            select(
                TavernState.player_id,
                TavernState.arena_rating,
                m.Player.username,
                m.Player.first_name,
            )
            .join(m.Player, m.Player.id == TavernState.player_id)
            .order_by(TavernState.arena_rating.desc(), TavernState.player_id.asc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            {
                "player_id": pid,
                "username": un,
                "name": name,
                "value": int(rating or 1000),
                "arena_rating": int(rating or 1000),
            }
            for pid, rating, un, name in rows
        ]

    if kind == "merc_collection":
        from waifu_bot.db.models.tavern import TavernState
        from sqlalchemy import cast, Integer
        from sqlalchemy.sql import func as sqfunc

        # Rank by number of unlocked legendary codex ids (JSON array length best-effort)
        q = (
            select(
                TavernState.player_id,
                TavernState.codex_legendary_ids,
                m.Player.username,
                m.Player.first_name,
            )
            .join(m.Player, m.Player.id == TavernState.player_id)
            .limit(limit * 3)
        )
        rows = (await session.execute(q)).all()
        scored = []
        for pid, codex, un, name in rows:
            n = len(codex or []) if isinstance(codex, list) else 0
            scored.append((n, pid, un, name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [
            {
                "player_id": pid,
                "username": un,
                "name": name,
                "value": n,
                "codex_count": n,
            }
            for n, pid, un, name in scored[:limit]
        ]

    return []


async def build_guild_summary(session: AsyncSession, guild_id: int) -> dict[str, Any] | None:
    guild = await session.get(m.Guild, guild_id)
    if not guild:
        return None

    member_count = await session.scalar(
        select(func.count()).select_from(m.GuildMember).where(m.GuildMember.guild_id == guild_id)
    ) or 0

    raid_wins = await session.scalar(
        select(func.count())
        .select_from(m.GuildRaid)
        .where(m.GuildRaid.guild_id == guild_id, m.GuildRaid.status == GuildRaidStatus.VICTORY.value)
    ) or 0
    raid_losses = await session.scalar(
        select(func.count())
        .select_from(m.GuildRaid)
        .where(m.GuildRaid.guild_id == guild_id, m.GuildRaid.status == GuildRaidStatus.DEFEAT.value)
    ) or 0

    war_wins = await session.scalar(
        select(func.count())
        .select_from(m.GuildWar)
        .where(
            m.GuildWar.winner_guild_id == guild_id,
            m.GuildWar.status == GuildWarRowStatus.ENDED.value,
        )
    ) or 0
    war_losses = await session.scalar(
        select(func.count())
        .select_from(m.GuildWar)
        .where(
            or_(m.GuildWar.guild_a_id == guild_id, m.GuildWar.guild_b_id == guild_id),
            m.GuildWar.status == GuildWarRowStatus.ENDED.value,
            m.GuildWar.winner_guild_id.is_not(None),
            m.GuildWar.winner_guild_id != guild_id,
        )
    ) or 0

    active_war = None
    if guild.active_war_id or (guild.war_status and guild.war_status != "none"):
        opponent = None
        if guild.war_opponent_id:
            opp = await session.get(m.Guild, guild.war_opponent_id)
            if opp:
                opponent = {"guild_id": opp.id, "name": opp.name, "tag": opp.tag}
        active_war = {
            "status": guild.war_status,
            "score": guild.war_score,
            "enemy_score": guild.war_score_enemy,
            "ends_at": guild.war_ends_at.isoformat() if guild.war_ends_at else None,
            "opponent": opponent,
        }

    active_raid = None
    if guild.raid_active_id:
        raid = await session.get(m.GuildRaid, guild.raid_active_id)
        if raid:
            template = await session.get(m.GuildRaidTemplate, raid.template_id)
            active_raid = {
                "raid_id": raid.id,
                "status": raid.status,
                "current_stage": raid.current_stage,
                "stages_count": template.stages_count if template else None,
                "name": template.name if template else None,
                "tier": template.tier if template else None,
                "started_at": raid.started_at.isoformat() if raid.started_at else None,
                "ends_at": raid.ends_at.isoformat() if raid.ends_at else None,
            }

    return {
        "guild_id": guild.id,
        "name": guild.name,
        "tag": guild.tag,
        "description": guild.description,
        "level": guild.level,
        "experience": guild.experience,
        "trophies": int(guild.trophies_count or 0),
        "member_count": int(member_count),
        "is_recruiting": bool(guild.is_recruiting),
        "min_level_requirement": guild.min_level_requirement,
        "icon_url": _static_url(guild.icon_path),
        "banner_url": _static_url(guild.banner_path),
        "title_badge": guild.title_badge_text,
        "title_badge_until": guild.title_badge_until.isoformat() if guild.title_badge_until else None,
        "war_status": guild.war_status,
        "active_war": active_war,
        "active_raid": active_raid,
        "raid_wins": int(raid_wins),
        "raid_losses": int(raid_losses),
        "war_wins": int(war_wins),
        "war_losses": int(war_losses),
    }


async def build_guild_members(session: AsyncSession, guild_id: int) -> list[dict[str, Any]] | None:
    guild = await session.get(m.Guild, guild_id)
    if not guild:
        return None

    role_order = case(
        (m.GuildMember.is_leader.is_(True), 0),
        (m.GuildMember.is_officer.is_(True), 1),
        else_=2,
    )
    q = (
        select(m.GuildMember, m.Player, m.MainWaifu)
        .join(m.Player, m.Player.id == m.GuildMember.player_id)
        .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
        .where(m.GuildMember.guild_id == guild_id)
        .order_by(role_order.asc(), m.MainWaifu.level.desc().nullslast(), m.Player.id.asc())
    )
    rows = (await session.execute(q)).all()
    out: list[dict[str, Any]] = []
    for member, player, waifu in rows:
        if member.is_leader:
            role = "leader"
        elif member.is_officer:
            role = "officer"
        else:
            role = "member"
        out.append(
            {
                "telegram_id": player.id,
                "username": player.username,
                "character_name": sanitize_display_name(
                    waifu.name if waifu else None, username=player.username, player_id=player.id
                ),
                "level": waifu.level if waifu else None,
                "role": role,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            }
        )
    return out


async def build_guild_raids(session: AsyncSession, guild_id: int, limit: int = 30) -> dict[str, Any] | None:
    guild = await session.get(m.Guild, guild_id)
    if not guild:
        return None

    wins = await session.scalar(
        select(func.count())
        .select_from(m.GuildRaid)
        .where(m.GuildRaid.guild_id == guild_id, m.GuildRaid.status == GuildRaidStatus.VICTORY.value)
    ) or 0
    losses = await session.scalar(
        select(func.count())
        .select_from(m.GuildRaid)
        .where(m.GuildRaid.guild_id == guild_id, m.GuildRaid.status == GuildRaidStatus.DEFEAT.value)
    ) or 0
    total_decided = int(wins) + int(losses)
    winrate = round(100.0 * int(wins) / total_decided, 1) if total_decided else 0.0

    active = None
    if guild.raid_active_id:
        raid = await session.execute(
            select(m.GuildRaid)
            .options(selectinload(m.GuildRaid.template), selectinload(m.GuildRaid.participants))
            .where(m.GuildRaid.id == guild.raid_active_id)
        )
        raid_row = raid.scalar_one_or_none()
        if raid_row:
            active = await _serialize_guild_raid(session, raid_row, include_top=False)

    finished_q = (
        select(m.GuildRaid)
        .options(selectinload(m.GuildRaid.template), selectinload(m.GuildRaid.participants))
        .where(
            m.GuildRaid.guild_id == guild_id,
            m.GuildRaid.status.in_((GuildRaidStatus.VICTORY.value, GuildRaidStatus.DEFEAT.value)),
        )
        .order_by(m.GuildRaid.ends_at.desc().nullslast(), m.GuildRaid.id.desc())
        .limit(limit)
    )
    finished_rows = (await session.execute(finished_q)).scalars().all()
    items = [await _serialize_guild_raid(session, r, include_top=True) for r in finished_rows]

    return {
        "wins": int(wins),
        "losses": int(losses),
        "winrate": winrate,
        "active": active,
        "items": items,
    }


async def _serialize_guild_raid(
    session: AsyncSession,
    raid: m.GuildRaid,
    *,
    include_top: bool,
) -> dict[str, Any]:
    template = raid.template
    top: list[dict[str, Any]] = []
    if include_top and raid.participants:
        ranked = sorted(raid.participants, key=lambda p: int(p.damage_dealt or 0), reverse=True)[:3]
        player_ids = [p.player_id for p in ranked]
        if player_ids:
            players = (
                await session.execute(
                    select(m.Player, m.MainWaifu)
                    .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
                    .where(m.Player.id.in_(player_ids))
                )
            ).all()
            by_id = {p.id: (p, w) for p, w in players}
            for part in ranked:
                p, w = by_id.get(part.player_id, (None, None))
                top.append(
                    {
                        "telegram_id": part.player_id,
                        "character_name": sanitize_display_name(
                            w.name if w else None,
                            username=p.username if p else None,
                            player_id=part.player_id,
                        ),
                        "damage_dealt": int(part.damage_dealt or 0),
                    }
                )

    return {
        "raid_id": raid.id,
        "name": template.name if template else None,
        "tier": template.tier if template else None,
        "status": raid.status,
        "current_stage": raid.current_stage,
        "stages_count": template.stages_count if template else None,
        "gxp_reward": raid.gxp_reward,
        "started_at": raid.started_at.isoformat() if raid.started_at else None,
        "ends_at": raid.ends_at.isoformat() if raid.ends_at else None,
        "top_participants": top,
    }


async def build_guild_wars(session: AsyncSession, guild_id: int, limit: int = 30) -> dict[str, Any] | None:
    guild = await session.get(m.Guild, guild_id)
    if not guild:
        return None

    wins = await session.scalar(
        select(func.count())
        .select_from(m.GuildWar)
        .where(
            m.GuildWar.winner_guild_id == guild_id,
            m.GuildWar.status == GuildWarRowStatus.ENDED.value,
        )
    ) or 0
    losses = await session.scalar(
        select(func.count())
        .select_from(m.GuildWar)
        .where(
            or_(m.GuildWar.guild_a_id == guild_id, m.GuildWar.guild_b_id == guild_id),
            m.GuildWar.status == GuildWarRowStatus.ENDED.value,
            m.GuildWar.winner_guild_id.is_not(None),
            m.GuildWar.winner_guild_id != guild_id,
        )
    ) or 0

    active = None
    if guild.active_war_id or (guild.war_status and guild.war_status != "none"):
        opponent = None
        if guild.war_opponent_id:
            opp = await session.get(m.Guild, guild.war_opponent_id)
            if opp:
                opponent = {"guild_id": opp.id, "name": opp.name, "tag": opp.tag}
        active = {
            "status": guild.war_status,
            "score": guild.war_score,
            "enemy_score": guild.war_score_enemy,
            "ends_at": guild.war_ends_at.isoformat() if guild.war_ends_at else None,
            "opponent": opponent,
        }

    wars_q = (
        select(m.GuildWar)
        .where(or_(m.GuildWar.guild_a_id == guild_id, m.GuildWar.guild_b_id == guild_id))
        .order_by(m.GuildWar.declared_at.desc())
        .limit(limit)
    )
    wars = (await session.execute(wars_q)).scalars().all()
    opponent_ids = set()
    for w in wars:
        opponent_ids.add(w.guild_a_id if w.guild_b_id == guild_id else w.guild_b_id)
        if w.winner_guild_id:
            opponent_ids.add(w.winner_guild_id)
    guilds_by_id: dict[int, m.Guild] = {}
    if opponent_ids:
        g_rows = (
            await session.execute(select(m.Guild).where(m.Guild.id.in_(opponent_ids)))
        ).scalars().all()
        guilds_by_id = {g.id: g for g in g_rows}

    items: list[dict[str, Any]] = []
    for w in wars:
        opp_id = w.guild_b_id if w.guild_a_id == guild_id else w.guild_a_id
        opp = guilds_by_id.get(opp_id)
        our_score = w.guild_a_score if w.guild_a_id == guild_id else w.guild_b_score
        their_score = w.guild_b_score if w.guild_a_id == guild_id else w.guild_a_score
        items.append(
            {
                "war_id": w.id,
                "status": w.status,
                "our_score": our_score,
                "their_score": their_score,
                "stake_gold": w.stake_gold,
                "winner_guild_id": w.winner_guild_id,
                "we_won": w.winner_guild_id == guild_id if w.winner_guild_id else None,
                "opponent": (
                    {"guild_id": opp.id, "name": opp.name, "tag": opp.tag} if opp else {"guild_id": opp_id}
                ),
                "declared_at": w.declared_at.isoformat() if w.declared_at else None,
                "ends_at": w.ends_at.isoformat() if w.ends_at else None,
            }
        )

    return {
        "wins": int(wins),
        "losses": int(losses),
        "trophies": int(guild.trophies_count or 0),
        "active": active,
        "items": items,
    }


async def build_guild_achievements(session: AsyncSession, guild_id: int) -> list[dict[str, Any]] | None:
    guild = await session.get(m.Guild, guild_id)
    if not guild:
        return None

    achievements: list[dict[str, Any]] = []

    trophies = int(guild.trophies_count or 0)
    achievements.append(
        {
            "id": "war_trophies",
            "kind": "trophy",
            "name": "Трофеи войн",
            "value": trophies,
            "earned": trophies > 0,
        }
    )

    raid_wins = await session.scalar(
        select(func.count())
        .select_from(m.GuildRaid)
        .where(m.GuildRaid.guild_id == guild_id, m.GuildRaid.status == GuildRaidStatus.VICTORY.value)
    ) or 0
    for threshold in (1, 5, 10):
        achievements.append(
            {
                "id": f"raid_wins_{threshold}",
                "kind": "raid",
                "name": f"Побед в рейдах: {threshold}",
                "value": int(raid_wins),
                "threshold": threshold,
                "earned": int(raid_wins) >= threshold,
            }
        )

    for threshold in (5, 10, 15, 20):
        achievements.append(
            {
                "id": f"guild_level_{threshold}",
                "kind": "level",
                "name": f"Уровень гильдии {threshold}",
                "value": guild.level,
                "threshold": threshold,
                "earned": guild.level >= threshold,
            }
        )

    now = datetime.now(timezone.utc)
    badge_until = guild.title_badge_until
    if badge_until is not None and badge_until.tzinfo is None:
        badge_until = badge_until.replace(tzinfo=timezone.utc)
    badge_active = bool(
        guild.title_badge_text
        and (badge_until is None or badge_until > now)
    )
    if guild.title_badge_text:
        achievements.append(
            {
                "id": "title_badge",
                "kind": "title",
                "name": guild.title_badge_text,
                "earned": badge_active,
                "until": guild.title_badge_until.isoformat() if guild.title_badge_until else None,
            }
        )

    skill_q = (
        select(m.GuildSkillLevelRow, m.GuildSkillDefinition)
        .join(
            m.GuildSkillDefinition,
            m.GuildSkillDefinition.id == m.GuildSkillLevelRow.skill_definition_id,
        )
        .where(
            m.GuildSkillLevelRow.guild_id == guild_id,
            m.GuildSkillLevelRow.current_level > 0,
        )
        .order_by(m.GuildSkillDefinition.sort_order.asc(), m.GuildSkillDefinition.id.asc())
    )
    skill_rows = (await session.execute(skill_q)).all()
    for row, definition in skill_rows:
        achievements.append(
            {
                "id": f"skill_{definition.id}",
                "kind": "skill",
                "name": definition.name,
                "tier": definition.tier,
                "level": row.current_level,
                "earned": True,
            }
        )

    return achievements


async def build_guild_bank(
    session: AsyncSession,
    guild_id: int,
    *,
    viewer_tg_id: int | None,
    viewer_is_admin: bool = False,
) -> dict[str, Any] | None:
    guild = await session.get(m.Guild, guild_id)
    if not guild:
        return None

    item_count = await session.scalar(
        select(func.count()).select_from(m.GuildBank).where(m.GuildBank.guild_id == guild_id)
    ) or 0

    can_view = bool(viewer_is_admin)
    if not can_view and viewer_tg_id is not None:
        mem = await session.scalar(
            select(m.GuildMember).where(
                m.GuildMember.guild_id == guild_id,
                m.GuildMember.player_id == viewer_tg_id,
            )
        )
        can_view = mem is not None

    out: dict[str, Any] = {
        "gold": int(guild.gold or 0),
        "item_count": int(item_count),
        "max_items": int(guild.max_bank_items or 0),
        "can_view_items": can_view,
        "items": [],
    }
    if not can_view:
        return out

    from waifu_bot.services.inventory_payload import (
        enrich_inventory_items_with_template_stats,
        serialize_inventory_item,
    )
    from waifu_bot.services.item_art import derive_image_key, derive_item_art_key

    stmt = (
        select(m.GuildBank)
        .where(m.GuildBank.guild_id == guild_id)
        .options(
            selectinload(m.GuildBank.item),
            selectinload(m.GuildBank.inventory_item).selectinload(m.InventoryItem.item),
            selectinload(m.GuildBank.inventory_item).selectinload(m.InventoryItem.affixes),
        )
        .order_by(m.GuildBank.id.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    parked = [r.inventory_item for r in rows if r.inventory_item is not None]
    if parked:
        await enrich_inventory_items_with_template_stats(session, parked)

    items: list[dict[str, Any]] = []
    for row in rows:
        if row.inventory_item is not None:
            serialized = serialize_inventory_item(row.inventory_item)
            serialized["bank_item_id"] = row.id
            items.append(serialized)
            continue
        item = row.item
        if not item:
            continue
        slot_type = getattr(item, "slot_type", None) or "costume"
        display_name = str(item.name or "Предмет")
        items.append(
            {
                "bank_item_id": row.id,
                "id": -int(row.id),
                "name": display_name,
                "display_name": display_name,
                "rarity": 1,
                "tier": int(item.tier or 1),
                "level": int(getattr(item, "level", None) or 1),
                "art_key": derive_item_art_key(slot_type, item.weapon_type, display_name),
                "image_key": derive_image_key(slot_type, item.weapon_type, display_name),
                "equipment_slot": None,
            }
        )
    out["items"] = items
    return out


async def admin_stats(session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    day_ago = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_players = await session.scalar(select(func.count()).select_from(m.Player)) or 0
    with_waifu = await session.scalar(
        select(func.count()).select_from(m.MainWaifu)
    ) or 0
    dau = await session.scalar(
        select(func.count()).select_from(m.Player).where(m.Player.last_active >= day_ago)
    ) or 0
    banned = await session.scalar(select(func.count()).select_from(m.PlayerBan)) or 0

    act_rows = (
        await session.execute(
            select(m.Player.current_act, func.count())
            .group_by(m.Player.current_act)
            .order_by(m.Player.current_act)
        )
    ).all()

    avg_gs = await session.scalar(select(func.avg(m.Player.gear_score))) or 0
    median_gs = 0
    try:
        median_row = await session.execute(
            select(m.Player.gear_score)
            .where(m.Player.gear_score > 0)
            .order_by(m.Player.gear_score)
            .offset(
                max(
                    0,
                    int(
                        (
                            await session.scalar(
                                select(func.count()).select_from(m.Player).where(m.Player.gear_score > 0)
                            )
                            or 0
                        )
                        // 2
                    ),
                )
            )
            .limit(1)
        )
        median_gs = int(median_row.scalar_one_or_none() or 0)
    except Exception:
        median_gs = 0

    from waifu_bot.services.abyss_service import week_start_msk

    ws = week_start_msk()
    abyss_top = (
        await session.execute(
            select(m.Player.id, m.Player.username, m.MainWaifu.name, m.AbyssWeeklyLeaderboard.max_floor)
            .join(m.AbyssWeeklyLeaderboard, m.AbyssWeeklyLeaderboard.player_id == m.Player.id)
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .where(m.AbyssWeeklyLeaderboard.week_start == ws)
            .order_by(m.AbyssWeeklyLeaderboard.max_floor.desc())
            .limit(5)
        )
    ).all()

    bank_heavy = await session.scalar(
        select(func.count())
        .select_from(m.Guild)
        .where(
            m.Guild.id.in_(
                select(m.GuildBank.guild_id)
                .group_by(m.GuildBank.guild_id)
                .having(func.count() > 5)
            )
        )
    ) or 0

    return {
        "total_players": total_players,
        "with_character": with_waifu,
        "dau_today": dau,
        "banned_count": banned,
        "by_act": {int(act): int(cnt) for act, cnt in act_rows},
        "avg_gear_score": round(float(avg_gs), 1),
        "median_gear_score": median_gs,
        "guilds_bank_over_5": int(bank_heavy),
        "abyss_week_start": ws.isoformat(),
        "abyss_top": [
            {
                "telegram_id": tid,
                "character_name": sanitize_display_name(name, username=un, player_id=tid),
                "max_floor": int(floor or 0),
            }
            for tid, un, name, floor in abyss_top
        ],
    }

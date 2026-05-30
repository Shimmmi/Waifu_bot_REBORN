"""Armory data aggregation service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.constants import WAIFU_CLASS_LABEL_RU, WAIFU_RACE_LABEL_RU
from waifu_bot.game.effective_stats import resolve_solo_combat_primary_four
from waifu_bot.game.main_waifu_base_stats import compute_main_waifu_base_stats
from waifu_bot.db.models.armory import PlayerBan, PlayerEventLog
from waifu_bot.services.armory_access import PUBLIC_EVENT_TYPES, armory_access_level
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.passive_skills import get_passive_skill_bonuses
from waifu_bot.services.player_ban import is_player_banned
from waifu_bot.services.inventory_payload import build_inventory_payloads


def _waifu_portrait_url(waifu: m.MainWaifu) -> str | None:
    if getattr(waifu, "image_data", None):
        mime = getattr(waifu, "image_mime", None) or "image/webp"
        return f"data:{mime};base64,{waifu.image_data}"
    return None


def _waifu_paperdoll_url(waifu: m.MainWaifu) -> str | None:
    if getattr(waifu, "paperdoll_image_data", None):
        mime = getattr(waifu, "paperdoll_image_mime", None) or "image/png"
        return f"data:{mime};base64,{waifu.paperdoll_image_data}"
    return None


def compute_gear_score(equipped_items: list[m.InventoryItem]) -> int:
    score = 0
    for inv in equipped_items:
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 1)
        rarity = int(getattr(inv, "rarity", None) or getattr(getattr(inv, "item", None), "rarity", None) or 1)
        score += tier * 10 + rarity * 5
        affixes = getattr(inv, "affixes", None) or []
        score += len(affixes) * 2
    return score


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
        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
        .where(
            m.InventoryItem.player_id == tg_id,
            m.InventoryItem.equipment_slot > 0,
        )
    )
    equipped = list(equipped_q.scalars().all())
    gear_score = compute_gear_score(equipped)

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
        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
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
            "character_name": w.name if w else None,
            "level": w.level if w else None,
        }
        for p, w in rows
    ]


async def build_leaderboard(session: AsyncSession, kind: str, limit: int = 50) -> list[dict[str, Any]]:
    if kind == "level":
        q = (
            select(m.Player.id, m.Player.username, m.MainWaifu.name, m.MainWaifu.level)
            .join(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .order_by(m.MainWaifu.level.desc(), m.MainWaifu.experience.desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            {"telegram_id": tid, "username": un, "character_name": name, "value": lvl}
            for tid, un, name, lvl in rows
        ]
    if kind == "gold":
        q = (
            select(m.Player.id, m.Player.username, m.MainWaifu.name, m.Player.gold)
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .order_by(m.Player.gold.desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            {"telegram_id": tid, "username": un, "character_name": name, "value": gold}
            for tid, un, name, gold in rows
        ]
    if kind == "dungeon_plus":
        q = (
            select(
                m.Player.id,
                m.Player.username,
                m.MainWaifu.name,
                func.max(m.PlayerDungeonPlus.plus_level).label("max_plus"),
            )
            .join(m.PlayerDungeonPlus, m.PlayerDungeonPlus.player_id == m.Player.id)
            .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
            .group_by(m.Player.id, m.Player.username, m.MainWaifu.name)
            .order_by(func.max(m.PlayerDungeonPlus.plus_level).desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            {"telegram_id": tid, "username": un, "character_name": name, "value": mp or 0}
            for tid, un, name, mp in rows
        ]
    if kind == "guild":
        q = (
            select(m.Guild.id, m.Guild.name, m.Guild.tag, m.Guild.level, m.Guild.experience)
            .order_by(m.Guild.level.desc(), m.Guild.experience.desc())
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [
            {"guild_id": gid, "name": name, "tag": tag, "level": lvl, "experience": xp}
            for gid, name, tag, lvl, xp in rows
        ]
    return []


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

    return {
        "total_players": total_players,
        "with_character": with_waifu,
        "dau_today": dau,
        "banned_count": banned,
        "by_act": {int(act): int(cnt) for act, cnt in act_rows},
    }

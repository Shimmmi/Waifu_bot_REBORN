"""Guild raids: start, progress, message damage (idle Telegram)."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import (
    Guild,
    GuildLevelThreshold,
    GuildMember,
    GuildRaid,
    GuildRaidParticipant,
    GuildRaidTemplate,
    InventoryItem,
    MainWaifu,
    Player,
)
from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import calculate_message_damage
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map
from waifu_bot.services.guild_progress import add_gxp
from waifu_bot.services.gd_round_engine import _attack_type_for_class, _weapon_dmg_from_level

logger = logging.getLogger(__name__)


def _can_manage_raid(member: GuildMember) -> bool:
    return bool(member.is_leader or member.is_officer)


async def _participant(session: AsyncSession, raid_id: int, player_id: int) -> GuildRaidParticipant | None:
    q = await session.execute(
        select(GuildRaidParticipant).where(
            GuildRaidParticipant.raid_id == raid_id,
            GuildRaidParticipant.player_id == player_id,
        )
    )
    return q.scalar_one_or_none()


async def start_raid(
    session: AsyncSession,
    player_id: int,
    template_id: int,
    participant_ids: list[int],
    chat_id: int,
) -> dict:
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))
    ).scalar_one_or_none()
    if not mem or not _can_manage_raid(mem):
        return {"error": "forbidden"}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"error": "no_guild"}
    if guild.raid_active_id:
        return {"error": "raid_already_active"}
    tpl = await session.get(GuildRaidTemplate, template_id)
    if not tpl:
        return {"error": "template_not_found"}
    if guild.level < int(tpl.min_guild_level):
        return {"error": "guild_level_too_low"}
    thr = await session.get(GuildLevelThreshold, guild.level)
    max_slots = int(thr.raid_party_slots) if thr else 5
    pids = [int(x) for x in participant_ids if int(x) == int(x)]
    pids = list(dict.fromkeys(pids))[:max_slots]
    if len(pids) < 2:
        return {"error": "need_participants", "min": 2}
    for pid in pids:
        gm = await session.execute(
            select(GuildMember).where(
                GuildMember.player_id == pid, GuildMember.guild_id == guild.id
            )
        )
        if gm.scalar_one_or_none() is None:
            return {"error": "not_all_guild_members", "player_id": pid}

    cfg = await get_game_config_map(session)
    scale = cfg_float(cfg, "guild_raid.base_scale", 10.0)
    per_p = cfg_float(cfg, "guild_raid.scale_per_participant", 1.0)
    stages = list(tpl.stages_json or [])
    if not stages:
        return {"error": "bad_template"}
    first = stages[0]
    base_hp = int(first.get("base_hp") or 1000)
    hp_max = max(1, int(base_hp * scale * (1 + len(pids) * per_p)))

    raid = GuildRaid(
        guild_id=guild.id,
        template_id=tpl.id,
        status="active",
        current_stage=1,
        phase="fight",
        stage_monster_hp_current=hp_max,
        stage_monster_hp_max=hp_max,
        started_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc) + timedelta(days=int(tpl.duration_days)),
        stage_ends_at=datetime.now(timezone.utc) + timedelta(hours=int(tpl.stage_duration_hours)),
        gxp_reward=int(tpl.gxp_reward),
        chat_id=int(chat_id),
    )
    session.add(raid)
    await session.flush()
    for pid in pids:
        session.add(GuildRaidParticipant(raid_id=raid.id, player_id=pid))
    guild.raid_active_id = raid.id
    guild.telegram_chat_id = int(chat_id)
    await session.commit()
    await session.refresh(raid)
    return {"success": True, "raid_id": raid.id}


async def leave_raid(session: AsyncSession, player_id: int) -> dict:
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))
    ).scalar_one_or_none()
    if not mem:
        return {"error": "not_in_guild"}
    guild = await session.get(Guild, mem.guild_id)
    if not guild or not guild.raid_active_id:
        return {"error": "no_active_raid"}
    part = await _participant(session, guild.raid_active_id, player_id)
    if part:
        await session.delete(part)
    await session.commit()
    return {"success": True}


async def _raid_online_member_count(session: AsyncSession, guild_id: int) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=5)
    mids = (
        await session.execute(select(GuildMember.player_id).where(GuildMember.guild_id == guild_id))
    ).scalars().all()
    cnt = 0
    for pid in mids:
        pl = await session.get(Player, pid)
        if not pl or not pl.last_active:
            continue
        la = pl.last_active
        la_utc = la.replace(tzinfo=timezone.utc) if la.tzinfo is None else la.astimezone(timezone.utc)
        if (now - la_utc) <= timedelta(minutes=5):
            cnt += 1
    return cnt


async def _current_stage_kind(session: AsyncSession, raid: GuildRaid) -> str:
    tpl = await session.get(GuildRaidTemplate, raid.template_id)
    if not tpl:
        return "trash"
    stages = list(tpl.stages_json or [])
    idx = int(raid.current_stage or 1) - 1
    if idx < 0 or idx >= len(stages):
        return "trash"
    return str(stages[idx].get("kind") or "trash")


async def apply_raid_message_damage(
    session: AsyncSession,
    chat_id: int,
    player_id: int,
    *,
    message_length: int,
    media_types: list[str] | None,
) -> dict:
    g = (
        await session.execute(select(Guild).where(Guild.telegram_chat_id == int(chat_id)))
    ).scalar_one_or_none()
    if not g or not g.raid_active_id:
        return {"ok": False, "reason": "no_raid"}
    raid = await session.get(GuildRaid, g.raid_active_id)
    if not raid or raid.status != "active" or raid.phase != "fight":
        return {"ok": False, "reason": "raid_not_fight"}
    part = await _participant(session, raid.id, player_id)
    if not part:
        return {"ok": False, "reason": "not_participant"}
    w = (
        await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))
    ).scalar_one_or_none()
    if not w:
        return {"ok": False, "reason": "no_waifu"}
    atk = _attack_type_for_class(int(w.class_ or 1))
    wd = _weapon_dmg_from_level(int(w.level or 1))
    dmg = 0
    if message_length > 0:
        dmg += calculate_message_damage(
            MediaType.TEXT,
            int(w.strength or 10),
            int(w.agility or 10),
            int(w.intelligence or 10),
            atk,
            message_length=message_length,
            weapon_damage=wd,
        )
    if media_types:
        dmg += 5 * len(media_types)
    dmg = max(1, int(dmg * random.uniform(0.9, 1.1)))
    guild_skill_lines: list[str] = []
    try:
        from waifu_bot.services.guild_skill_effects import (
            effect_values_for_guild,
            guild_skill_contributions_for_guild,
            pct_bonus_lines_ru,
        )

        gfx = await effect_values_for_guild(session, g.id)
        flat = int(gfx.get("raid_attack_flat", 0) or 0)
        if flat:
            dmg += flat
        mult = 1.0
        online_n = await _raid_online_member_count(session, g.id)
        online_pct = float(gfx.get("damage_per_online_member_pct", 0) or 0)
        if online_n > 0 and online_pct > 0:
            mult += online_pct * online_n
        stage_kind = await _current_stage_kind(session, raid)
        if stage_kind in ("miniboss", "final"):
            boss_pct = float(gfx.get("raid_boss_damage_pct", 0) or 0)
            if boss_pct > 0:
                mult += boss_pct
        dmg = max(1, int(dmg * mult))
        guild_skill_lines = pct_bonus_lines_ru(
            await guild_skill_contributions_for_guild(
                session,
                g.id,
                params={
                    "raid_attack_flat",
                    "raid_boss_damage_pct",
                    "damage_per_online_member_pct",
                },
            )
        )
    except Exception:
        logger.exception("raid guild skill bonus failed guild_id=%s player_id=%s", g.id, player_id)
    raid.stage_monster_hp_current = max(0, int(raid.stage_monster_hp_current) - dmg)
    part.message_count = int(part.message_count or 0) + 1
    part.damage_dealt = int(part.damage_dealt or 0) + dmg
    out = {"ok": True, "damage": dmg, "hp_left": raid.stage_monster_hp_current}
    if guild_skill_lines:
        out["guild_skill_lines"] = guild_skill_lines
    if raid.stage_monster_hp_current <= 0:
        await _advance_or_complete_raid(session, raid, g)
    await session.commit()
    return out


async def _advance_or_complete_raid(session: AsyncSession, raid: GuildRaid, guild: Guild) -> None:
    tpl = await session.get(GuildRaidTemplate, raid.template_id)
    if not tpl:
        return
    stages = list(tpl.stages_json or [])
    if not stages:
        return
    if raid.current_stage < len(stages):
        raid.current_stage += 1
        cfg = await get_game_config_map(session)
        scale = cfg_float(cfg, "guild_raid.base_scale", 10.0)
        per_p = cfg_float(cfg, "guild_raid.scale_per_participant", 1.0)
        n = (
            await session.execute(
                select(GuildRaidParticipant).where(GuildRaidParticipant.raid_id == raid.id)
            )
        ).scalars().all()
        np = max(1, len(n))
        st = stages[raid.current_stage - 1]
        base_hp = int(st.get("base_hp") or 1000)
        hp_max = max(1, int(base_hp * scale * (1 + np * per_p)))
        raid.stage_monster_hp_max = hp_max
        raid.stage_monster_hp_current = hp_max
        raid.stage_ends_at = datetime.now(timezone.utc) + timedelta(hours=int(tpl.stage_duration_hours))
        raid.phase = "fight"
        return
    raid.status = "victory"
    guild.raid_active_id = None
    gxp = int(raid.gxp_reward)
    try:
        from waifu_bot.services.guild_skill_effects import effect_values_for_guild

        gfx = await effect_values_for_guild(session, guild.id)
        gxp_mult = float(gfx.get("raid_gxp_multiplier", 0) or 0)
        if gxp_mult > 0:
            gxp = max(1, int(round(gxp * (1.0 + gxp_mult))))
        completion_pct = float(gfx.get("raid_completion_reward_pct", 0) or 0)
        if completion_pct > 0:
            gxp = max(1, int(round(gxp * (1.0 + completion_pct))))
    except Exception:
        logger.exception("raid completion guild bonus failed guild_id=%s", guild.id)
    await add_gxp(session, guild.id, gxp, reason="raid_win")
    await _grant_raid_victory_loot(session, raid, guild)


async def _guild_leader_player_id(session: AsyncSession, guild_id: int) -> int | None:
    q = await session.execute(
        select(GuildMember.player_id).where(GuildMember.guild_id == guild_id, GuildMember.is_leader.is_(True)).limit(1)
    )
    return q.scalar_one_or_none()


async def _grant_raid_victory_loot(session: AsyncSession, raid: GuildRaid, guild: Guild) -> None:
    """Roll raid items on victory; auto mode gives to participants, manual stashes on leader."""
    parts = (
        await session.execute(select(GuildRaidParticipant).where(GuildRaidParticipant.raid_id == raid.id))
    ).scalars().all()
    participant_ids = [int(p.player_id) for p in parts]
    if not participant_ids:
        raid.pending_loot_json = {"mode": "auto", "distributed": True, "inventory_item_ids": []}
        raid.reward_pool_json = {"item_count": 0, "mode": "auto"}
        return

    tpl = await session.get(GuildRaidTemplate, raid.template_id)
    tier = int(tpl.tier) if tpl else 1
    act = max(1, min(10, tier))
    mode = (getattr(guild, "raid_loot_mode", None) or "auto").strip().lower()
    if mode not in ("auto", "manual"):
        mode = "auto"

    num_items = max(1, min(4, len(participant_ids)))
    from waifu_bot.services.item_service import ItemService

    item_svc = ItemService()
    try:
        if mode == "manual":
            leader_id = await _guild_leader_player_id(session, guild.id)
            stash_pid = leader_id if leader_id is not None else participant_ids[0]
            inv_ids: list[int] = []
            for _ in range(num_items):
                inv = await item_svc.generate_inventory_item(
                    session, player_id=int(stash_pid), act=act, rarity=None, level=None
                )
                inv_ids.append(int(inv.id))
            raid.pending_loot_json = {
                "mode": "manual",
                "distributed": False,
                "inventory_item_ids": inv_ids,
            }
            raid.reward_pool_json = {"item_count": len(inv_ids), "mode": "manual", "raid_id": raid.id}
        else:
            for i in range(num_items):
                pid = participant_ids[i % len(participant_ids)]
                await item_svc.generate_inventory_item(
                    session, player_id=int(pid), act=act, rarity=None, level=None
                )
            raid.pending_loot_json = {"mode": "auto", "distributed": True, "inventory_item_ids": []}
            raid.reward_pool_json = {"item_count": num_items, "mode": "auto", "raid_id": raid.id}
    except Exception:
        logger.exception("raid victory loot generation failed raid_id=%s guild_id=%s", raid.id, guild.id)
        raid.pending_loot_json = {"mode": mode, "distributed": mode == "auto", "inventory_item_ids": [], "error": "loot_failed"}
        raid.reward_pool_json = {"item_count": 0, "error": "loot_failed"}


async def _undistributed_manual_raid_loot(session: AsyncSession, guild_id: int) -> GuildRaid | None:
    q = await session.execute(
        select(GuildRaid)
        .where(GuildRaid.guild_id == guild_id, GuildRaid.status == "victory")
        .order_by(GuildRaid.id.desc())
        .limit(12)
    )
    for raid in q.scalars():
        pl = raid.pending_loot_json or {}
        if pl.get("mode") == "manual" and not pl.get("distributed") and pl.get("inventory_item_ids"):
            return raid
    return None


async def get_raid_loot_state(session: AsyncSession, player_id: int) -> dict:
    """Leader: pending manual raid loot with item previews."""
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))
    ).scalar_one_or_none()
    if not mem or not mem.is_leader:
        return {"error": "forbidden"}
    raid = await _undistributed_manual_raid_loot(session, mem.guild_id)
    if not raid:
        return {"raid_id": None, "items": []}
    pl = raid.pending_loot_json or {}
    ids = [int(x) for x in (pl.get("inventory_item_ids") or [])]
    items_out: list[dict] = []
    leader_id = await _guild_leader_player_id(session, mem.guild_id)
    for iid in ids:
        inv = (
            await session.execute(
                select(InventoryItem)
                .options(selectinload(InventoryItem.item))
                .where(InventoryItem.id == iid)
            )
        ).scalar_one_or_none()
        if not inv:
            continue
        if leader_id is not None and int(inv.player_id) != int(leader_id):
            continue
        it = inv.item
        name = str(getattr(it, "name", "") or "Предмет") if it else "Предмет"
        items_out.append(
            {
                "inventory_item_id": int(inv.id),
                "name": name,
                "rarity": int(inv.rarity or 1),
                "level": int(inv.level or inv.total_level or 1),
            }
        )
    return {"raid_id": int(raid.id), "items": items_out}


async def distribute_raid_loot(
    session: AsyncSession,
    player_id: int,
    raid_id: int,
    assignments: list[dict],
) -> dict:
    """Leader assigns each pending manual loot row to a guild member."""
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))
    ).scalar_one_or_none()
    if not mem or not mem.is_leader:
        return {"error": "forbidden"}
    raid = await session.get(GuildRaid, raid_id)
    if not raid or int(raid.guild_id) != int(mem.guild_id):
        return {"error": "raid_not_found"}
    if str(raid.status) != "victory":
        return {"error": "raid_not_found"}
    pl = dict(raid.pending_loot_json or {})
    if pl.get("mode") != "manual" or pl.get("distributed"):
        return {"error": "nothing_to_distribute"}
    pending_ids = {int(x) for x in (pl.get("inventory_item_ids") or [])}
    if not pending_ids:
        return {"error": "nothing_to_distribute"}

    leader_id = await _guild_leader_player_id(session, mem.guild_id)
    if leader_id is None:
        return {"error": "no_leader"}

    by_target: dict[int, list[int]] = {}
    for raw in assignments:
        try:
            iid = int(raw["inventory_item_id"])
            tid = int(raw["player_id"])
        except (KeyError, TypeError, ValueError):
            return {"error": "bad_assignment"}
        if iid not in pending_ids:
            return {"error": "invalid_item"}
        by_target.setdefault(tid, []).append(iid)

    assigned: set[int] = set()
    for tid, iids in by_target.items():
        gm = (
            await session.execute(
                select(GuildMember).where(GuildMember.guild_id == mem.guild_id, GuildMember.player_id == tid)
            )
        ).scalar_one_or_none()
        if not gm:
            return {"error": "not_guild_member", "player_id": tid}
        for iid in iids:
            inv = await session.get(InventoryItem, iid)
            if not inv or int(inv.player_id) != int(leader_id):
                return {"error": "invalid_item", "inventory_item_id": iid}
            inv.player_id = int(tid)
            assigned.add(int(iid))

    if assigned != pending_ids:
        return {"error": "incomplete_assignments"}

    pl["distributed"] = True
    raid.pending_loot_json = pl
    await session.commit()
    return {"success": True}


async def tick_raid_stage_timeouts(session: AsyncSession) -> None:
    cfg = await get_game_config_map(session)
    enrage = cfg_float(cfg, "guild_raid.stage_enrage_hp_mult", 1.2)
    now = datetime.now(timezone.utc)
    q = await session.execute(
        select(GuildRaid).where(
            GuildRaid.status == "active",
            GuildRaid.phase == "fight",
            GuildRaid.stage_ends_at.isnot(None),
            GuildRaid.stage_ends_at < now,
        )
    )
    for raid in q.scalars():
        guild = await session.get(Guild, raid.guild_id)
        if not guild:
            continue
        raid.stage_enrage_count = int(raid.stage_enrage_count or 0) + 1
        new_max = max(1, int(raid.stage_monster_hp_max * enrage))
        raid.stage_monster_hp_max = new_max
        raid.stage_monster_hp_current = max(
            int(raid.stage_monster_hp_current), int(new_max * 0.3)
        )
        tpl = await session.get(GuildRaidTemplate, raid.template_id)
        hrs = int(tpl.stage_duration_hours) if tpl else 12
        raid.stage_ends_at = now + timedelta(hours=hrs)
        if raid.ends_at and now >= raid.ends_at:
            raid.status = "defeat"
            guild.raid_active_id = None
    await session.commit()


async def raid_state_for_player(session: AsyncSession, player_id: int) -> dict:
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))
    ).scalar_one_or_none()
    if not mem:
        return {"in_guild": False}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"in_guild": False}
    thr = await session.get(GuildLevelThreshold, guild.level)
    templates = (
        await session.execute(
            select(GuildRaidTemplate).where(GuildRaidTemplate.min_guild_level <= guild.level)
        )
    ).scalars().all()
    active = None
    if guild.raid_active_id:
        r = await session.get(
            GuildRaid,
            guild.raid_active_id,
            options=[selectinload(GuildRaid.participants)],
        )
        if r:
            active = {
                "id": r.id,
                "stage": r.current_stage,
                "phase": r.phase,
                "hp": r.stage_monster_hp_current,
                "hp_max": r.stage_monster_hp_max,
                "ends_at": r.ends_at.isoformat() if r.ends_at else None,
                "stage_ends_at": r.stage_ends_at.isoformat() if r.stage_ends_at else None,
                "participants": [
                    {"player_id": p.player_id, "messages": p.message_count, "damage": p.damage_dealt}
                    for p in r.participants
                ],
            }
    pending_manual_raid_loot = None
    if mem.is_leader:
        loot_st = await get_raid_loot_state(session, player_id)
        if loot_st.get("raid_id") and loot_st.get("items"):
            pending_manual_raid_loot = loot_st
    raid_loot_mode = str(getattr(guild, "raid_loot_mode", None) or "auto").strip().lower()
    if raid_loot_mode not in ("auto", "manual"):
        raid_loot_mode = "auto"
    return {
        "in_guild": True,
        "guild_id": guild.id,
        "is_leader": mem.is_leader,
        "is_officer": mem.is_officer,
        "guild_level": guild.level,
        "gxp": guild.experience,
        "raid_tier_unlock": int(thr.raid_tier_unlock) if thr else 0,
        "raid_party_slots": int(thr.raid_party_slots) if thr else 0,
        "templates": [
            {"id": t.id, "tier": t.tier, "name": t.name, "gxp": t.gxp_reward, "min_level": t.min_guild_level}
            for t in templates
        ],
        "active_raid": active,
        "telegram_chat_id": guild.telegram_chat_id,
        "raid_loot_mode": raid_loot_mode,
        "pending_manual_raid_loot": pending_manual_raid_loot,
    }

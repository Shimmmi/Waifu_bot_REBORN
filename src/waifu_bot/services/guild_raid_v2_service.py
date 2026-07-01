"""Guild raid v2: weekly chronicle (muster, chat log, daily MSK pipeline)."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import (
    BotGroupChat,
    Guild,
    GuildLevelThreshold,
    GuildMember,
    GuildRaid,
    GuildRaidChatEvent,
    GuildRaidDailyLog,
    GuildRaidMuster,
    GuildRaidParticipant,
    GuildRaidSlotSummary,
    GuildRaidTemplate,
    MainWaifu,
    Player,
)
from waifu_bot.api.main_waifu_media import guild_member_portrait_url
from waifu_bot.services.bot_group_chats import ACTIVE_STATUSES, build_telegram_group_url
from waifu_bot.services.player_chats import players_seen_in_group_chat, resolve_player_group_chats
from waifu_bot.services.abyss_service import msk_now, msk_today
from waifu_bot.services.guild_raid_mechanics import (
    MUSTER_HOURS,
    NEUTRAL_TACTIC,
    RAID_DAILY_COMPOSE_HOUR,
    RAID_DAILY_COMPOSE_MINUTE,
    RAID_DAILY_DELIVER_HOUR,
    RAID_DAILY_DELIVER_MINUTE,
    RAID_DAILY_RESOLVE_HOUR,
    RAID_DAILY_RESOLVE_MINUTE,
    RAID_WEEK_DAYS,
    gxp_multiplier_for_outcome,
    mechanics_for_tactic_option,
    outcome_tier,
    resolve_daily_tactic,
)
from waifu_bot.game.constants import RAID_V2_SLOT_COUNT, RAID_V2_SLOT_HOURS
from waifu_bot.services.guild_raid_narrative_ai import (
    _strip_leaked_json,
    compose_raid_daily_narrative,
    generate_raid_daily_tactics,
    generate_raid_defeat_epilogue,
    generate_raid_finale,
    generate_raid_prologue,
    generate_raid_slot_summary,
    msk_slot_label,
    pick_raid_adventure_goal,
    pick_random_raid_setting,
)
from waifu_bot.services.guild_progress import add_gxp

logger = logging.getLogger(__name__)
_MSK = ZoneInfo("Europe/Moscow")

MUSTER_STATUS_PENDING = "pending"
MUSTER_STATUS_COMPLETED = "completed"
MUSTER_STATUS_CANCELLED = "cancelled"

_RAID_CHAT_EMPTY_HINT = (
    "Напишите хотя бы одно сообщение в групповом чате с ботом — тогда чат появится в списке."
)
_GUILD_ONLINE_TTL = timedelta(minutes=5)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def raid_start_date_msk(raid: GuildRaid) -> date | None:
    if not raid.started_at:
        return None
    return raid.started_at.astimezone(_MSK).date()


def daily_compose_due_msk(raid: GuildRaid, day_index: int) -> datetime | None:
    start_date = raid_start_date_msk(raid)
    if start_date is None:
        return None
    due_date = start_date + timedelta(days=int(day_index))
    return datetime.combine(
        due_date,
        time(RAID_DAILY_COMPOSE_HOUR, RAID_DAILY_COMPOSE_MINUTE),
        tzinfo=_MSK,
    )


def daily_deliver_due_msk(raid: GuildRaid, day_index: int) -> datetime | None:
    start_date = raid_start_date_msk(raid)
    if start_date is None:
        return None
    due_date = start_date + timedelta(days=int(day_index))
    return datetime.combine(
        due_date,
        time(RAID_DAILY_DELIVER_HOUR, RAID_DAILY_DELIVER_MINUTE),
        tzinfo=_MSK,
    )


def daily_resolve_due_msk(raid: GuildRaid, day_index: int) -> datetime | None:
    start_date = raid_start_date_msk(raid)
    if start_date is None:
        return None
    due_date = start_date + timedelta(days=int(day_index))
    return datetime.combine(
        due_date,
        time(RAID_DAILY_RESOLVE_HOUR, RAID_DAILY_RESOLVE_MINUTE),
        tzinfo=_MSK,
    )


def _can_manage_raid(member: GuildMember) -> bool:
    return bool(member.is_leader or member.is_officer)


async def _guild_leader_id(session: AsyncSession, guild_id: int) -> int | None:
    q = await session.execute(
        select(GuildMember.player_id).where(
            GuildMember.guild_id == guild_id, GuildMember.is_leader.is_(True)
        ).limit(1)
    )
    return q.scalar_one_or_none()


async def _build_party_snapshot(session: AsyncSession, player_ids: list[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid in player_ids:
        w = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == pid))
        ).scalar_one_or_none()
        if not w:
            out.append({"player_id": pid, "name": f"Игрок {pid}", "class_id": 1, "race_id": 1, "level": 1})
            continue
        out.append(
            {
                "player_id": int(pid),
                "user_id": int(pid),
                "name": (w.name or f"Вайфu {pid}").strip(),
                "class_id": int(w.class_ or 1),
                "race_id": int(w.race or 1),
                "level": int(w.level or 1),
            }
        )
    return out


async def _best_template(session: AsyncSession, guild: Guild) -> GuildRaidTemplate | None:
    q = await session.execute(
        select(GuildRaidTemplate)
        .where(GuildRaidTemplate.min_guild_level <= guild.level)
        .order_by(GuildRaidTemplate.tier.desc())
        .limit(1)
    )
    return q.scalar_one_or_none()


async def get_active_muster(session: AsyncSession, guild_id: int) -> GuildRaidMuster | None:
    q = await session.execute(
        select(GuildRaidMuster)
        .where(
            GuildRaidMuster.guild_id == guild_id,
            GuildRaidMuster.status == MUSTER_STATUS_PENDING,
        )
        .order_by(GuildRaidMuster.id.desc())
        .limit(1)
    )
    return q.scalar_one_or_none()


def muster_public_state(muster: GuildRaidMuster) -> dict[str, Any]:
    pids = [int(x) for x in (muster.participant_ids_json or [])]
    responses = dict(muster.responses_json or {})
    participants = []
    for pid in pids:
        st = responses.get(str(pid)) or responses.get(pid) or "pending"
        participants.append({"player_id": pid, "status": st})
    return {
        "id": muster.id,
        "status": muster.status,
        "deadline_at": muster.deadline_at.isoformat() if muster.deadline_at else None,
        "participants": participants,
        "initiator_player_id": muster.initiator_player_id,
    }


async def _require_guild_leader(
    session: AsyncSession, player_id: int
) -> tuple[GuildMember, Guild] | dict[str, Any]:
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))
    ).scalar_one_or_none()
    if not mem or not mem.is_leader:
        return {"error": "forbidden"}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"error": "no_guild"}
    return mem, guild


async def _leader_raid_chat_ids(session: AsyncSession, leader_id: int) -> list[int]:
    leader_chats = await resolve_player_group_chats(session, int(leader_id))
    if not leader_chats:
        return []
    rows = (
        await session.execute(
            select(BotGroupChat.chat_id).where(
                BotGroupChat.chat_id.in_(leader_chats),
                BotGroupChat.status.in_(tuple(ACTIVE_STATUSES)),
            )
        )
    ).all()
    return sorted({int(r[0]) for r in rows})


async def list_raid_available_chats(session: AsyncSession, player_id: int) -> dict[str, Any]:
    ctx = await _require_guild_leader(session, player_id)
    if isinstance(ctx, dict):
        return ctx
    _mem, guild = ctx
    allowed_ids = await _leader_raid_chat_ids(session, player_id)
    if not allowed_ids:
        return {"chats": [], "hint": _RAID_CHAT_EMPTY_HINT}
    rows = (
        await session.execute(select(BotGroupChat).where(BotGroupChat.chat_id.in_(allowed_ids)))
    ).scalars().all()
    row_by_id = {int(r.chat_id): r for r in rows}
    current_chat = int(guild.telegram_chat_id) if guild.telegram_chat_id else None
    chats: list[dict[str, Any]] = []
    for cid in allowed_ids:
        row = row_by_id.get(cid)
        title = (row.title if row and row.title else None) or f"Чат {cid}"
        username = row.username if row else None
        invite_link = row.invite_link if row else None
        chats.append(
            {
                "chat_id": cid,
                "title": title,
                "username": username,
                "telegram_url": build_telegram_group_url(
                    cid, username=username, invite_link=invite_link
                ),
                "is_current": current_chat is not None and cid == current_chat,
            }
        )
    return {"chats": chats}


def _member_public_dict(
    gm: GuildMember,
    *,
    waifu_by_player: dict[int, MainWaifu],
    now_utc: datetime,
) -> dict[str, Any]:
    pl: Player | None = gm.player
    last_active_iso = None
    online = False
    telegram_username = None
    if pl is None:
        display_name = f"Игрок {gm.player_id}"
        player_id_out = int(gm.player_id)
    else:
        la = pl.last_active
        if la is not None:
            la_utc = la.replace(tzinfo=timezone.utc) if la.tzinfo is None else la.astimezone(timezone.utc)
            last_active_iso = la_utc.isoformat()
            online = (now_utc - la_utc) <= _GUILD_ONLINE_TTL
        fn = (pl.first_name or "").strip()
        un = (pl.username or "").strip()
        display_name = fn or un or str(pl.id)
        player_id_out = int(pl.id)
        telegram_username = un or None
    mw = waifu_by_player.get(int(gm.player_id))
    portrait_url = guild_member_portrait_url(mw, int(gm.player_id)) if mw else None
    if gm.is_leader:
        rank = "Глава"
    elif gm.is_officer:
        rank = "Офицер"
    else:
        rank = "Участник"
    from waifu_bot.services.guild_activity import member_power

    return {
        "player_id": player_id_out,
        "display_name": display_name,
        "telegram_username": telegram_username,
        "is_leader": bool(gm.is_leader),
        "is_officer": bool(gm.is_officer),
        "rank": rank,
        "portrait_url": portrait_url,
        "last_active": last_active_iso,
        "online": online,
        "member_power": member_power(mw),
    }


async def guild_members_for_raid_chat(
    session: AsyncSession, player_id: int, chat_id: int
) -> dict[str, Any]:
    ctx = await _require_guild_leader(session, player_id)
    if isinstance(ctx, dict):
        return ctx
    _mem, guild = ctx
    cid = int(chat_id)
    if cid >= 0:
        return {"error": "invalid_raid_chat"}
    allowed_ids = await _leader_raid_chat_ids(session, player_id)
    if cid not in allowed_ids:
        return {"error": "invalid_raid_chat"}
    seen_pids = set(await players_seen_in_group_chat(session, cid))
    gm_stmt = (
        select(GuildMember)
        .where(GuildMember.guild_id == guild.id)
        .options(selectinload(GuildMember.player))
    )
    guild_members = (await session.execute(gm_stmt)).scalars().unique().all()
    member_ids = [int(gm.player_id) for gm in guild_members if int(gm.player_id) in seen_pids]
    waifu_by_player: dict[int, MainWaifu] = {}
    if member_ids:
        waifu_rows = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id.in_(member_ids)))
        ).scalars().all()
        waifu_by_player = {int(w.player_id): w for w in waifu_rows}
    now_utc = datetime.now(timezone.utc)
    members_out: list[dict[str, Any]] = []
    for gm in guild_members:
        if int(gm.player_id) not in seen_pids:
            continue
        members_out.append(
            _member_public_dict(gm, waifu_by_player=waifu_by_player, now_utc=now_utc)
        )
    members_out.sort(
        key=lambda x: (
            -bool(x["online"]),
            -bool(x["is_leader"]),
            -bool(x["is_officer"]),
            x["display_name"].lower(),
        )
    )
    chat_row = await session.get(BotGroupChat, cid)
    chat_title = (chat_row.title if chat_row and chat_row.title else None) or f"Чат {cid}"
    return {"chat_id": cid, "chat_title": chat_title, "members": members_out}


async def send_muster_invites(session: AsyncSession, muster_id: int) -> None:
    muster = await session.get(GuildRaidMuster, muster_id)
    if not muster:
        return
    guild = await session.get(Guild, muster.guild_id)
    if not guild:
        return
    try:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ В строй", callback_data=f"raid_muster_yes:{muster_id}"),
                    InlineKeyboardButton(text="❌ Не могу", callback_data=f"raid_muster_no:{muster_id}"),
                ]
            ]
        )
        deadline = muster.deadline_at.astimezone(_MSK).strftime("%H:%M %d.%m") if muster.deadline_at else "—"
        text = (
            f"⚔️ <b>Сбор на гильдейский рейд</b>\n"
            f"Гильдия [{guild.tag}] набирает отряд. Подтвердите участие до {deadline} (МСК)."
        )
        for pid in muster.participant_ids_json or []:
            try:
                await bot.send_message(chat_id=int(pid), text=text, reply_markup=kb)
            except Exception:
                logger.warning("muster invite DM failed pid=%s muster_id=%s", pid, muster_id)
    except Exception:
        logger.exception("send_muster_invites failed muster_id=%s", muster_id)


async def create_muster(
    session: AsyncSession,
    player_id: int,
    participant_ids: list[int],
    chat_id: int,
) -> dict[str, Any]:
    ctx = await _require_guild_leader(session, player_id)
    if isinstance(ctx, dict):
        return ctx
    mem, guild = ctx
    if guild.raid_active_id:
        return {"error": "raid_already_active"}
    existing = await get_active_muster(session, guild.id)
    if existing:
        return {"error": "muster_already_active", "muster": muster_public_state(existing)}

    thr = await session.get(GuildLevelThreshold, guild.level)
    max_slots = int(thr.raid_party_slots) if thr else 5
    pids = list(dict.fromkeys(int(x) for x in participant_ids))[:max_slots]
    if len(pids) < 2:
        return {"error": "need_participants", "min": 2}

    if int(chat_id) == 0:
        return {"error": "need_guild_chat"}
    cid = int(chat_id)
    allowed_ids = await _leader_raid_chat_ids(session, player_id)
    if cid not in allowed_ids:
        return {"error": "invalid_raid_chat"}

    seen_pids = set(await players_seen_in_group_chat(session, cid))
    for pid in pids:
        gm = await session.execute(
            select(GuildMember).where(GuildMember.guild_id == guild.id, GuildMember.player_id == pid)
        )
        if gm.scalar_one_or_none() is None:
            return {"error": "not_all_guild_members", "player_id": pid}
        if int(pid) not in seen_pids:
            return {"error": "not_in_raid_chat", "player_id": pid}

    guild.telegram_chat_id = cid

    muster = GuildRaidMuster(
        guild_id=guild.id,
        initiator_player_id=int(player_id),
        participant_ids_json=pids,
        status=MUSTER_STATUS_PENDING,
        responses_json={},
        deadline_at=_utc_now() + timedelta(hours=MUSTER_HOURS),
    )
    session.add(muster)
    await session.flush()
    return {"success": True, "muster_id": muster.id, "participant_ids": pids}


async def respond_muster(
    session: AsyncSession,
    player_id: int,
    muster_id: int,
    accept: bool,
) -> dict[str, Any]:
    muster = await session.get(GuildRaidMuster, muster_id)
    if not muster or muster.status != MUSTER_STATUS_PENDING:
        return {"error": "muster_not_found"}
    pids = [int(x) for x in (muster.participant_ids_json or [])]
    if int(player_id) not in pids:
        return {"error": "not_invited"}
    responses = dict(muster.responses_json or {})
    prev = responses.get(str(player_id))
    if accept and prev == "accepted":
        if all(responses.get(str(pid)) == "accepted" for pid in pids):
            return await _complete_muster_and_start_raid(session, muster)
        return {
            "success": True,
            "status": "pending",
            "muster": muster_public_state(muster),
            "idempotent": True,
        }
    if not accept and prev == "declined":
        return {
            "success": True,
            "status": "cancelled",
            "reason": "declined",
            "player_id": player_id,
            "idempotent": True,
        }
    responses[str(player_id)] = "accepted" if accept else "declined"
    muster.responses_json = responses
    if not accept:
        muster.status = MUSTER_STATUS_CANCELLED
        await session.commit()
        return {"success": True, "status": "cancelled", "reason": "declined", "player_id": player_id}
    if all(responses.get(str(pid)) == "accepted" for pid in pids):
        return await _complete_muster_and_start_raid(session, muster)
    await session.commit()
    return {"success": True, "status": "pending", "muster": muster_public_state(muster)}


async def tick_muster_deadlines(session: AsyncSession) -> None:
    now = _utc_now()
    q = await session.execute(
        select(GuildRaidMuster).where(
            GuildRaidMuster.status == MUSTER_STATUS_PENDING,
            GuildRaidMuster.deadline_at <= now,
        )
    )
    for muster in q.scalars():
        pids = [int(x) for x in (muster.participant_ids_json or [])]
        responses = dict(muster.responses_json or {})
        cancelled = False
        for pid in pids:
            if responses.get(str(pid)) not in ("accepted",):
                responses[str(pid)] = responses.get(str(pid)) or "timeout"
                cancelled = True
        muster.responses_json = responses
        if cancelled:
            muster.status = MUSTER_STATUS_CANCELLED
        else:
            await _complete_muster_and_start_raid(session, muster)
            continue
    await session.commit()


def _schedule_raid_prologue(raid_id: int) -> None:
    asyncio.create_task(_finish_raid_prologue(raid_id), name=f"raid_prologue:{raid_id}")


async def _finish_raid_prologue(raid_id: int) -> None:
    from waifu_bot.db.session import get_session, init_engine

    init_engine()
    try:
        async for session in get_session():
            raid = await session.get(GuildRaid, raid_id)
            if not raid:
                return
            guild = await session.get(Guild, raid.guild_id)
            if not guild:
                return
            part_rows = (
                await session.execute(
                    select(GuildRaidParticipant.player_id).where(GuildRaidParticipant.raid_id == raid_id)
                )
            ).scalars().all()
            pids = [int(x) for x in part_rows]
            party = list(raid.party_snapshot_json or [])
            loc_id = str(raid.location_archetype_id or "forest")
            meta = dict(raid.adventure_meta_json or {})
            tpl = await session.get(GuildRaidTemplate, raid.template_id)
            goal = str(
                meta.get("adventure_goal")
                or pick_raid_adventure_goal(loc_id, template_name=tpl.name if tpl else None)
            )
            prologue = await generate_raid_prologue(
                guild_name=str(meta.get("guild_name") or guild.name or ""),
                guild_tag=str(meta.get("guild_tag") or guild.tag or ""),
                location_archetype_id=loc_id,
                party=party,
                adventure_goal=goal,
                template_name=tpl.name if tpl else None,
            )
            meta["prologue_html"] = prologue
            meta["adventure_goal"] = goal
            raid.adventure_meta_json = meta
            await session.commit()
            await _deliver_prologue(session, raid, guild, prologue, pids)
            break
    except Exception:
        logger.exception("finish raid prologue failed raid_id=%s", raid_id)


async def _complete_muster_and_start_raid(session: AsyncSession, muster: GuildRaidMuster) -> dict[str, Any]:
    if muster.status == MUSTER_STATUS_COMPLETED and muster.raid_id:
        return {
            "success": True,
            "status": "started",
            "raid_id": muster.raid_id,
            "muster": muster_public_state(muster),
            "idempotent": True,
        }
    guild = await session.get(Guild, muster.guild_id)
    if not guild or guild.raid_active_id:
        muster.status = MUSTER_STATUS_CANCELLED
        await session.commit()
        return {"error": "raid_already_active"}
    tpl = await _best_template(session, guild)
    if not tpl:
        muster.status = MUSTER_STATUS_CANCELLED
        await session.commit()
        return {"error": "no_template"}

    pids = [int(x) for x in (muster.participant_ids_json or [])]
    party = await _build_party_snapshot(session, pids)
    loc_id, _style_id = pick_random_raid_setting()
    goal = pick_raid_adventure_goal(loc_id, template_name=tpl.name)
    chat_id = int(guild.telegram_chat_id or 0)
    if not chat_id:
        muster.status = MUSTER_STATUS_CANCELLED
        await session.commit()
        return {"error": "need_guild_chat"}

    now = _utc_now()
    raid = GuildRaid(
        guild_id=guild.id,
        template_id=tpl.id,
        status="active",
        current_stage=1,
        phase="adventure",
        stage_monster_hp_current=0,
        stage_monster_hp_max=0,
        started_at=now,
        ends_at=now + timedelta(days=RAID_WEEK_DAYS),
        gxp_reward=int(tpl.gxp_reward),
        chat_id=chat_id,
        raid_version=2,
        company_vitality=100,
        story_progress=0,
        day_index=0,
        location_archetype_id=loc_id,
        narrative_style_id=0,
        party_snapshot_json=party,
        adventure_meta_json={
            "prologue_html": "",
            "guild_tag": guild.tag,
            "guild_name": guild.name,
            "adventure_goal": goal,
        },
    )
    session.add(raid)
    await session.flush()
    for pid in pids:
        session.add(GuildRaidParticipant(raid_id=raid.id, player_id=pid))
    guild.raid_active_id = raid.id
    muster.status = MUSTER_STATUS_COMPLETED
    muster.raid_id = raid.id
    await session.commit()
    await session.refresh(raid)

    _schedule_raid_prologue(raid.id)
    return {"success": True, "status": "started", "raid_id": raid.id, "muster": muster_public_state(muster)}


async def _deliver_prologue(
    session: AsyncSession,
    raid: GuildRaid,
    guild: Guild,
    prologue: str,
    participant_ids: list[int],
) -> None:
    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        if bot and guild.telegram_chat_id:
            await bot.send_message(chat_id=int(guild.telegram_chat_id), text=prologue[:4000])
        for pid in participant_ids:
            try:
                await bot.send_message(chat_id=int(pid), text=prologue[:4000])
            except Exception:
                logger.debug("raid prologue DM failed pid=%s", pid)
    except Exception:
        logger.exception("deliver prologue failed raid_id=%s", raid.id)


async def log_raid_chat_event(
    session: AsyncSession,
    chat_id: int,
    player_id: int,
    *,
    message_length: int,
    media_types: list[str] | None,
    text_preview: str | None = None,
) -> dict[str, Any]:
    g = (
        await session.execute(select(Guild).where(Guild.telegram_chat_id == int(chat_id)))
    ).scalar_one_or_none()
    if not g or not g.raid_active_id:
        return {"ok": False, "reason": "no_raid"}
    raid = await session.get(GuildRaid, g.raid_active_id)
    if not raid or raid.status != "active" or int(getattr(raid, "raid_version", 1) or 1) < 2:
        return {"ok": False, "reason": "not_v2"}
    part = (
        await session.execute(
            select(GuildRaidParticipant).where(
                GuildRaidParticipant.raid_id == raid.id,
                GuildRaidParticipant.player_id == player_id,
            )
        )
    ).scalar_one_or_none()
    if not part:
        return {"ok": False, "reason": "not_participant"}
    session.add(
        GuildRaidChatEvent(
            raid_id=raid.id,
            player_id=int(player_id),
            event_ts=_utc_now(),
            message_length=int(message_length or 0),
            media_types_json=list(media_types or []),
            text_preview=(text_preview or "")[:512] or None,
        )
    )
    part.message_count = int(part.message_count or 0) + 1
    await session.commit()
    return {"logged": True}


def _msk_slot_index(dt: datetime) -> int:
    local = dt.astimezone(_MSK)
    return min(RAID_V2_SLOT_COUNT - 1, local.hour // RAID_V2_SLOT_HOURS)


def _slot_label(idx: int) -> str:
    return msk_slot_label(idx)


def _slot_start_msk(game_date: date, slot_index: int) -> datetime:
    hour = slot_index * RAID_V2_SLOT_HOURS
    return datetime(game_date.year, game_date.month, game_date.day, hour, 0, tzinfo=_MSK)


def _slot_end_msk(game_date: date, slot_index: int) -> datetime:
    if slot_index >= RAID_V2_SLOT_COUNT - 1:
        next_day = game_date + timedelta(days=1)
        return datetime(next_day.year, next_day.month, next_day.day, 0, 0, tzinfo=_MSK)
    hour = (slot_index + 1) * RAID_V2_SLOT_HOURS
    return datetime(game_date.year, game_date.month, game_date.day, hour, 0, tzinfo=_MSK)


async def aggregate_chat_slot(
    session: AsyncSession,
    raid_id: int,
    for_date: date,
    slot_index: int,
    *,
    min_event_ts: datetime | None = None,
    max_previews_per_slot: int = 5,
) -> dict[str, Any]:
    slot_start = _slot_start_msk(for_date, slot_index).astimezone(timezone.utc)
    slot_end = _slot_end_msk(for_date, slot_index).astimezone(timezone.utc)
    if min_event_ts is not None and min_event_ts > slot_start:
        slot_start = min_event_ts
    filters = [
        GuildRaidChatEvent.raid_id == raid_id,
        GuildRaidChatEvent.event_ts >= slot_start,
        GuildRaidChatEvent.event_ts < slot_end,
    ]
    q = await session.execute(select(GuildRaidChatEvent).where(*filters))
    events = q.scalars().all()
    beat: dict[str, Any] = {
        "slot_index": slot_index,
        "slot_label": _slot_label(slot_index),
        "rest": True,
        "active_players": [],
        "messages": 0,
        "previews": [],
    }
    player_names: dict[int, str] = {}
    raid = await session.get(GuildRaid, raid_id)
    for p in raid.party_snapshot_json or [] if raid else []:
        player_names[int(p.get("player_id") or 0)] = str(p.get("name") or "")
    by_player: dict[int, int] = {}
    previews: list[str] = []
    for ev in events:
        by_player[int(ev.player_id)] = by_player.get(int(ev.player_id), 0) + 1
        beat["rest"] = False
        beat["messages"] = int(beat["messages"]) + 1
        preview = (ev.text_preview or "").strip()
        if preview and len(previews) < max_previews_per_slot:
            previews.append(preview)
    active = []
    for pid, cnt in sorted(by_player.items(), key=lambda x: -x[1]):
        nm = player_names.get(pid) or f"Игрок {pid}"
        active.append(f"{nm} ({cnt})")
    beat["active_players"] = active
    beat["previews"] = previews
    return beat


async def aggregate_chat_slots(
    session: AsyncSession,
    raid_id: int,
    for_date: date,
    *,
    min_event_ts: datetime | None = None,
    max_previews_per_slot: int = 5,
) -> list[dict[str, Any]]:
    day_start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=_MSK).astimezone(timezone.utc)
    day_end = day_start + timedelta(days=1)
    filters = [
        GuildRaidChatEvent.raid_id == raid_id,
        GuildRaidChatEvent.event_ts >= day_start,
        GuildRaidChatEvent.event_ts < day_end,
    ]
    if min_event_ts is not None:
        filters.append(GuildRaidChatEvent.event_ts >= min_event_ts)
    q = await session.execute(select(GuildRaidChatEvent).where(*filters))
    events = q.scalars().all()
    slots: list[dict[str, Any]] = []
    for idx in range(RAID_V2_SLOT_COUNT):
        slots.append(
            {
                "slot_index": idx,
                "slot_label": _slot_label(idx),
                "rest": True,
                "active_players": [],
                "messages": 0,
                "previews": [],
            }
        )

    player_names: dict[int, str] = {}
    raid = await session.get(GuildRaid, raid_id)
    for p in raid.party_snapshot_json or [] if raid else []:
        player_names[int(p.get("player_id") or 0)] = str(p.get("name") or "")

    by_slot: dict[int, dict[int, int]] = {i: {} for i in range(RAID_V2_SLOT_COUNT)}
    previews_by_slot: dict[int, list[str]] = {i: [] for i in range(RAID_V2_SLOT_COUNT)}
    for ev in events:
        si = _msk_slot_index(ev.event_ts)
        by_slot[si][int(ev.player_id)] = by_slot[si].get(int(ev.player_id), 0) + 1
        slots[si]["rest"] = False
        slots[si]["messages"] = int(slots[si]["messages"]) + 1
        preview = (ev.text_preview or "").strip()
        if preview and len(previews_by_slot[si]) < max_previews_per_slot:
            previews_by_slot[si].append(preview)

    for idx in range(RAID_V2_SLOT_COUNT):
        active = []
        for pid, cnt in sorted(by_slot[idx].items(), key=lambda x: -x[1]):
            nm = player_names.get(pid) or f"Игрок {pid}"
            active.append(f"{nm} ({cnt})")
        slots[idx]["active_players"] = active
        slots[idx]["previews"] = previews_by_slot[idx]
    return slots


def _poll_log_matches(pv: dict[str, Any], telegram_poll_id: str) -> bool:
    pid = str(telegram_poll_id)
    if str(pv.get("group_poll_id") or pv.get("__telegram_poll_id__") or "") == pid:
        return True
    dm = pv.get("dm_poll_ids")
    if isinstance(dm, dict):
        return pid in {str(v) for v in dm.values()}
    return False


async def tick_raid_4h_summaries(session: AsyncSession) -> None:
    """Generate 4-hour slot summaries for completed MSK windows."""
    now_msk = msk_now()
    q = await session.execute(
        select(GuildRaid).where(GuildRaid.status == "active", GuildRaid.raid_version >= 2)
    )
    raids = q.scalars().all()
    for raid in raids:
        if not raid.started_at:
            continue
        guild = await session.get(Guild, raid.guild_id)
        if not guild:
            continue
        party = list(raid.party_snapshot_json or [])
        loc_id = str(raid.location_archetype_id or "forest")
        start_date = raid.started_at.astimezone(_MSK).date()
        end_date = now_msk.date()
        current = start_date
        while current <= end_date:
            for si in range(RAID_V2_SLOT_COUNT):
                slot_end = _slot_end_msk(current, si)
                if now_msk < slot_end:
                    continue
                slot_start_utc = _slot_start_msk(current, si).astimezone(timezone.utc)
                if raid.started_at >= slot_end.astimezone(timezone.utc):
                    continue
                existing = (
                    await session.execute(
                        select(GuildRaidSlotSummary).where(
                            GuildRaidSlotSummary.raid_id == raid.id,
                            GuildRaidSlotSummary.game_date == current,
                            GuildRaidSlotSummary.slot_index == si,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    continue
                min_ts = raid.started_at if raid.started_at > slot_start_utc else None
                beat = await aggregate_chat_slot(
                    session, raid.id, current, si, min_event_ts=min_ts
                )
                summary = await generate_raid_slot_summary(
                    guild_name=guild.name,
                    guild_tag=guild.tag,
                    location_archetype_id=loc_id,
                    party=party,
                    slot_label=_slot_label(si),
                    slot_beat=beat,
                )
                session.add(
                    GuildRaidSlotSummary(
                        raid_id=raid.id,
                        game_date=current,
                        slot_index=si,
                        slot_label=_slot_label(si),
                        summary_html=summary,
                        slot_beats_json=[beat],
                        generated_at=_utc_now(),
                    )
                )
            current += timedelta(days=1)
    await session.flush()


async def record_poll_vote_by_poll_id(
    session: AsyncSession,
    *,
    telegram_poll_id: str,
    player_id: int,
    option_ids: list[int],
) -> None:
    q = await session.execute(
        select(GuildRaidDailyLog).where(
            GuildRaidDailyLog.resolved_at.is_(None),
            GuildRaidDailyLog.delivered_at.isnot(None),
        )
    )
    for log in q.scalars():
        pv = log.poll_votes_json or {}
        if not _poll_log_matches(pv, telegram_poll_id):
            continue
        inner = pv.get("votes") if isinstance(pv.get("votes"), dict) else {}
        inner[str(player_id)] = option_ids
        pv = dict(pv)
        pv["votes"] = inner
        log.poll_votes_json = pv
        await session.commit()
        return


def _tactic_options_with_mechanics(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in raw:
        out.append(
            mechanics_for_tactic_option(
                label=str(t.get("label") or "Тактика"),
                risk=str(t.get("risk") or "medium"),
                terrain_fit=t.get("terrain_fit"),
            )
        )
    if len(out) < 3:
        out.append(dict(NEUTRAL_TACTIC))
    return out[:4]


async def _pick_winning_tactic(
    session: AsyncSession,
    log: GuildRaidDailyLog,
    raid: GuildRaid,
    guild: Guild,
) -> dict[str, Any]:
    options = list(log.tactic_poll_options_json or [])
    if not options:
        return dict(NEUTRAL_TACTIC)
    pv = dict(log.poll_votes_json or {})
    votes = pv.get("votes") if isinstance(pv.get("votes"), dict) else pv
    if not votes:
        return dict(NEUTRAL_TACTIC)

    leader_id = await _guild_leader_id(session, guild.id)
    counts: dict[int, int] = {i: 0 for i in range(len(options))}
    for pid_str, opt_ids in votes.items():
        if not opt_ids:
            continue
        weight = 2 if leader_id is not None and int(pid_str) == int(leader_id) else 1
        for oid in opt_ids:
            if 0 <= int(oid) < len(options):
                counts[int(oid)] += weight

    best_idx = max(counts, key=lambda i: counts[i])
    if counts[best_idx] <= 0:
        return dict(NEUTRAL_TACTIC)
    return dict(options[best_idx])


async def compose_raid_daily_log(
    session: AsyncSession, raid: GuildRaid, *, force: bool = False
) -> GuildRaidDailyLog | None:
    if int(getattr(raid, "raid_version", 1) or 1) < 2 or raid.status != "active":
        return None
    day_index = int(raid.day_index or 0) + 1
    if day_index > RAID_WEEK_DAYS:
        return None

    if not force:
        compose_due = daily_compose_due_msk(raid, day_index)
        if compose_due is None or msk_now() < compose_due:
            return None

    existing = (
        await session.execute(
            select(GuildRaidDailyLog).where(
                GuildRaidDailyLog.raid_id == raid.id,
                GuildRaidDailyLog.day_index == day_index,
                GuildRaidDailyLog.generated_at.isnot(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        if force and not existing.delivered_at:
            await session.delete(existing)
            await session.flush()
        else:
            return None

    guild = await session.get(Guild, raid.guild_id)
    if not guild:
        return None

    game_date = msk_today() - timedelta(days=1)
    slot_rows = (
        await session.execute(
            select(GuildRaidSlotSummary)
            .where(
                GuildRaidSlotSummary.raid_id == raid.id,
                GuildRaidSlotSummary.game_date == game_date,
            )
            .order_by(GuildRaidSlotSummary.slot_index)
        )
    ).scalars().all()
    slot_summaries = [
        {
            "slot_index": r.slot_index,
            "slot_label": r.slot_label,
            "summary_html": r.summary_html,
        }
        for r in slot_rows
    ]
    if not slot_summaries and day_index == 1 and raid.started_at:
        min_event_ts = None
        started_local = raid.started_at.astimezone(_MSK)
        if started_local.date() == game_date:
            min_event_ts = raid.started_at
        beats = await aggregate_chat_slots(
            session, raid.id, game_date, min_event_ts=min_event_ts
        )
        from waifu_bot.services.guild_raid_narrative_ai import (
            _build_slot_fallback_summary,
            _location_name,
        )

        loc = _location_name(str(raid.location_archetype_id or "forest"))
        for beat in beats:
            if beat.get("rest"):
                continue
            slot_summaries.append(
                {
                    "slot_index": beat.get("slot_index"),
                    "slot_label": beat.get("slot_label"),
                    "summary_html": _build_slot_fallback_summary(
                        slot_label=str(beat.get("slot_label") or ""),
                        slot_beat=beat,
                        location=loc,
                    ),
                }
            )

    chronicle: list[str] = []
    prev_logs = (
        await session.execute(
            select(GuildRaidDailyLog)
            .where(GuildRaidDailyLog.raid_id == raid.id, GuildRaidDailyLog.narrative_html.isnot(None))
            .order_by(GuildRaidDailyLog.day_index)
        )
    ).scalars().all()
    for pl in prev_logs:
        if pl.narrative_html:
            chronicle.append(pl.narrative_html)

    party = list(raid.party_snapshot_json or [])
    loc_id = str(raid.location_archetype_id or "forest")
    meta = dict(raid.adventure_meta_json or {})
    adventure_goal = str(meta.get("adventure_goal") or "").strip() or None
    narrative = await compose_raid_daily_narrative(
        guild_name=guild.name,
        guild_tag=guild.tag,
        day_index=day_index,
        location_archetype_id=loc_id,
        party=party,
        slot_summaries=slot_summaries,
        company_vitality=int(raid.company_vitality or 0),
        story_progress=int(raid.story_progress or 0),
        last_tactic=raid.last_tactic_choice_json,
        last_resolve=raid.last_resolve_json,
        chronicle_summaries=chronicle,
        adventure_goal=adventure_goal,
    )
    narrative = _strip_leaked_json(narrative)
    raw_tactics = await generate_raid_daily_tactics(
        guild_name=guild.name,
        guild_tag=guild.tag,
        day_index=day_index,
        location_archetype_id=loc_id,
        party=party,
        narrative_preview=narrative,
        last_tactic=raid.last_tactic_choice_json,
        last_resolve=raid.last_resolve_json,
        story_progress=int(raid.story_progress or 0),
    )
    tactics = _tactic_options_with_mechanics(raw_tactics)
    slot_beats = [dict(r.slot_beats_json[0]) for r in slot_rows if r.slot_beats_json]

    log = GuildRaidDailyLog(
        raid_id=raid.id,
        day_index=day_index,
        game_date=game_date,
        narrative_html=narrative,
        slot_beats_json=slot_beats or None,
        tactic_poll_options_json=tactics,
        generated_at=_utc_now(),
    )
    session.add(log)
    await session.flush()
    return log


async def process_raid_daily_generate(
    session: AsyncSession, raid: GuildRaid, *, force: bool = False
) -> GuildRaidDailyLog | None:
    return await compose_raid_daily_log(session, raid, force=force)


async def deliver_raid_daily(session: AsyncSession, log: GuildRaidDailyLog) -> None:
    if log.delivered_at:
        return
    raid = await session.get(GuildRaid, log.raid_id)
    if not raid or raid.status != "active":
        return
    guild = await session.get(Guild, raid.guild_id)
    if not guild or not guild.telegram_chat_id:
        logger.warning("deliver_raid_daily skipped: no guild chat raid_id=%s log_id=%s", log.raid_id, log.id)
        return

    claim_ts = _utc_now()
    claimed = (
        await session.execute(
            update(GuildRaidDailyLog)
            .where(GuildRaidDailyLog.id == log.id, GuildRaidDailyLog.delivered_at.is_(None))
            .values(delivered_at=claim_ts)
            .returning(GuildRaidDailyLog.id)
        )
    ).scalar_one_or_none()
    if not claimed:
        await session.refresh(log)
        return
    log.delivered_at = claim_ts
    await session.flush()

    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        chat_id = int(guild.telegram_chat_id)
        narrative = _strip_leaked_json(log.narrative_html or "")[:4000]
        await bot.send_message(chat_id=chat_id, text=narrative)

        options = [
            str(t.get("label") or f"Вариант {i+1}")[:90]
            for i, t in enumerate(log.tactic_poll_options_json or [])
        ]
        if not options:
            options = [NEUTRAL_TACTIC["label"], "Форсировать переход", "Рискованный рейд"]

        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=f"Тактика на день {log.day_index} (до 08:00 МСК)",
            options=options,
            is_anonymous=False,
            allows_multiple_answers=False,
        )
        log.poll_message_id = poll_msg.message_id
        log.poll_chat_id = chat_id
        resolve_due = daily_resolve_due_msk(raid, int(log.day_index))
        log.poll_deadline_at = (
            resolve_due.astimezone(timezone.utc) if resolve_due else _utc_now() + timedelta(hours=3)
        )
        poll_id = poll_msg.poll.id if poll_msg.poll else None

        log.poll_votes_json = {
            "group_poll_id": poll_id,
            "__telegram_poll_id__": poll_id,
            "votes": {},
        }
        raid.day_index = int(log.day_index)
        await session.commit()
    except Exception:
        logger.exception("deliver_raid_daily failed raid_id=%s log_id=%s", log.raid_id, log.id)
        await session.execute(
            update(GuildRaidDailyLog)
            .where(GuildRaidDailyLog.id == log.id)
            .values(delivered_at=None)
        )
        await session.commit()


async def resolve_raid_daily_poll(session: AsyncSession, log: GuildRaidDailyLog) -> None:
    if log.resolved_at:
        return
    raid = await session.get(GuildRaid, log.raid_id)
    if not raid:
        return
    guild = await session.get(Guild, raid.guild_id)
    if not guild:
        return

    winner = await _pick_winning_tactic(session, log, raid, guild)
    log.winning_tactic_json = winner
    resolve = resolve_daily_tactic(
        tactic=winner,
        location_archetype_id=raid.location_archetype_id,
        party_snapshot=list(raid.party_snapshot_json or []),
        guild_level=int(guild.level or 1),
    )
    log.resolve_json = resolve
    log.resolved_at = _utc_now()

    raid.last_tactic_choice_json = winner
    raid.last_resolve_json = resolve
    raid.company_vitality = max(0, min(100, int(raid.company_vitality or 0) + int(resolve["vitality_delta"])))
    raid.story_progress = max(0, min(100, int(raid.story_progress or 0) + int(resolve["progress_delta"])))

    outcome = outcome_tier(
        vitality=int(raid.company_vitality),
        progress=int(raid.story_progress),
        day_index=int(raid.day_index or 0),
    )

    summary = (
        f"Тактика: {winner.get('label', '—')}. "
        f"Выносливость: {raid.company_vitality} ({resolve['vitality_delta']:+d}). "
        f"Прогресс: {raid.story_progress} ({resolve['progress_delta']:+d})."
    )

    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        if guild.telegram_chat_id:
            await bot.send_message(chat_id=int(guild.telegram_chat_id), text=summary[:3500])
    except Exception:
        logger.exception("raid resolve summary failed raid_id=%s", raid.id)

    if outcome == "defeat":
        await _finish_raid(session, raid, guild, "defeat")
    elif int(raid.day_index or 0) >= RAID_WEEK_DAYS and outcome in ("victory", "partial", "failed"):
        await _finish_raid(session, raid, guild, outcome)

    await session.commit()


async def _finish_raid(session: AsyncSession, raid: GuildRaid, guild: Guild, outcome: str) -> None:
    party = list(raid.party_snapshot_json or [])
    meta = dict(raid.adventure_meta_json or {})
    if outcome == "defeat":
        epilogue = await generate_raid_defeat_epilogue(
            guild_name=guild.name,
            guild_tag=guild.tag,
            location_archetype_id=str(raid.location_archetype_id or ""),
            party=party,
            day_index=int(raid.day_index or 0),
        )
        raid.status = "defeat"
    else:
        epilogue = await generate_raid_finale(
            guild_name=guild.name,
            guild_tag=guild.tag,
            location_archetype_id=str(raid.location_archetype_id or ""),
            party=party,
            outcome=outcome,
            story_progress=int(raid.story_progress or 0),
            company_vitality=int(raid.company_vitality or 0),
        )
        raid.status = "victory" if outcome == "victory" else "defeat" if outcome == "failed" else "victory"

    meta["finale_html"] = epilogue
    raid.adventure_meta_json = meta

    mult = gxp_multiplier_for_outcome(outcome)
    gxp = max(0, int(round(int(raid.gxp_reward or 0) * mult)))
    if gxp > 0:
        await add_gxp(session, guild.id, gxp, reason=f"raid_v2_{outcome}")

    guild.raid_active_id = None

    try:
        from waifu_bot.services.webhook import get_bot
        from waifu_bot.services.guild_raid_service import _grant_raid_victory_loot

        bot = get_bot()
        if guild.telegram_chat_id:
            await bot.send_message(chat_id=int(guild.telegram_chat_id), text=epilogue[:4000])
        if outcome in ("victory", "partial"):
            await _grant_raid_victory_loot(session, raid, guild)
    except Exception:
        logger.exception("raid finish delivery failed raid_id=%s", raid.id)


async def _pending_daily_log_for_deliver(
    session: AsyncSession, raid_id: int, day_index: int
) -> GuildRaidDailyLog | None:
    result = await session.execute(
        select(GuildRaidDailyLog).where(
            GuildRaidDailyLog.raid_id == raid_id,
            GuildRaidDailyLog.day_index == day_index,
            GuildRaidDailyLog.generated_at.isnot(None),
            GuildRaidDailyLog.delivered_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _pending_daily_log_for_resolve(session: AsyncSession, raid_id: int) -> GuildRaidDailyLog | None:
    result = await session.execute(
        select(GuildRaidDailyLog)
        .where(
            GuildRaidDailyLog.raid_id == raid_id,
            GuildRaidDailyLog.delivered_at.isnot(None),
            GuildRaidDailyLog.resolved_at.is_(None),
        )
        .order_by(GuildRaidDailyLog.day_index.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _daily_log_generated(
    session: AsyncSession, raid_id: int, day_index: int
) -> GuildRaidDailyLog | None:
    result = await session.execute(
        select(GuildRaidDailyLog).where(
            GuildRaidDailyLog.raid_id == raid_id,
            GuildRaidDailyLog.day_index == day_index,
            GuildRaidDailyLog.generated_at.isnot(None),
        )
    )
    return result.scalar_one_or_none()


async def tick_raid_daily_msk(session: AsyncSession) -> None:
    """Run compose/deliver/resolve per raid calendar (MSK) anchored at started_at."""
    now_msk = msk_now()
    q = await session.execute(
        select(GuildRaid).where(GuildRaid.status == "active", GuildRaid.raid_version >= 2)
    )
    raids = q.scalars().all()
    if not raids:
        return

    for raid in raids:
        try:
            if not raid.started_at:
                continue

            pending_resolve = await _pending_daily_log_for_resolve(session, raid.id)
            if pending_resolve:
                resolve_due = daily_resolve_due_msk(raid, int(pending_resolve.day_index))
                if resolve_due and now_msk >= resolve_due:
                    await resolve_raid_daily_poll(session, pending_resolve)

            next_day = int(raid.day_index or 0) + 1
            if next_day > RAID_WEEK_DAYS:
                continue

            compose_due = daily_compose_due_msk(raid, next_day)
            if compose_due and now_msk >= compose_due:
                existing = await _daily_log_generated(session, raid.id, next_day)
                if not existing:
                    log = await compose_raid_daily_log(session, raid)
                    if log:
                        await session.commit()

            deliver_due = daily_deliver_due_msk(raid, next_day)
            if deliver_due and now_msk >= deliver_due:
                log = await _pending_daily_log_for_deliver(session, raid.id, next_day)
                if log:
                    await deliver_raid_daily(session, log)
        except Exception:
            logger.exception("raid daily tick failed raid_id=%s", raid.id)
    await session.commit()


async def raid_v2_state(session: AsyncSession, guild: Guild, mem: GuildMember) -> dict[str, Any]:
    """Extended raid snapshot for WebApp."""
    from waifu_bot.services.guild_raid_service import get_raid_loot_state, raid_state_for_player

    base = await raid_state_for_player(session, mem.player_id)
    muster = await get_active_muster(session, guild.id)
    base["active_muster"] = muster_public_state(muster) if muster else None

    chronicle: list[dict[str, Any]] = []
    if guild.raid_active_id:
        logs = (
            await session.execute(
                select(GuildRaidDailyLog)
                .where(GuildRaidDailyLog.raid_id == guild.raid_active_id)
                .order_by(GuildRaidDailyLog.day_index)
            )
        ).scalars().all()
        for lg in logs:
            chronicle.append(
                {
                    "day_index": lg.day_index,
                    "narrative_html": lg.narrative_html,
                    "delivered_at": lg.delivered_at.isoformat() if lg.delivered_at else None,
                    "winning_tactic": lg.winning_tactic_json,
                    "resolve": lg.resolve_json,
                    "poll_deadline_at": lg.poll_deadline_at.isoformat() if lg.poll_deadline_at else None,
                    "poll_options": lg.tactic_poll_options_json,
                }
            )
        r = await session.get(GuildRaid, guild.raid_active_id)
        if r and int(getattr(r, "raid_version", 1) or 1) >= 2:
            active = base.get("active_raid") or {}
            active.update(
                {
                    "raid_version": 2,
                    "day_index": r.day_index,
                    "company_vitality": r.company_vitality,
                    "story_progress": r.story_progress,
                    "location_archetype_id": r.location_archetype_id,
                    "narrative_style_id": r.narrative_style_id,
                    "party_snapshot": r.party_snapshot_json,
                    "prologue_html": (r.adventure_meta_json or {}).get("prologue_html"),
                    "last_tactic": r.last_tactic_choice_json,
                    "last_resolve": r.last_resolve_json,
                }
            )
            base["active_raid"] = active
    base["chronicle"] = chronicle
    return base


async def resolve_active_v2_raid(
    session: AsyncSession,
    *,
    chat_id: int | None = None,
    guild_id: int | None = None,
) -> tuple[Guild, GuildRaid] | dict[str, Any]:
    guild: Guild | None = None
    if chat_id is not None:
        guild = (
            await session.execute(select(Guild).where(Guild.telegram_chat_id == int(chat_id)))
        ).scalar_one_or_none()
    elif guild_id is not None:
        guild = await session.get(Guild, int(guild_id))
    else:
        return {"error": "need_context"}
    if not guild or not guild.raid_active_id:
        return {"error": "no_active_raid"}
    raid = await session.get(GuildRaid, guild.raid_active_id)
    if not raid or raid.status != "active":
        return {"error": "no_active_raid"}
    if int(getattr(raid, "raid_version", 1) or 1) < 2:
        return {"error": "no_active_v2_raid"}
    return guild, raid


async def admin_force_slot_summaries(session: AsyncSession, raid: GuildRaid) -> dict[str, Any]:
    before = (
        await session.execute(
            select(GuildRaidSlotSummary).where(GuildRaidSlotSummary.raid_id == raid.id)
        )
    ).scalars().all()
    before_n = len(before)
    await tick_raid_4h_summaries(session)
    await session.flush()
    after = (
        await session.execute(
            select(GuildRaidSlotSummary).where(GuildRaidSlotSummary.raid_id == raid.id)
        )
    ).scalars().all()
    return {
        "success": True,
        "raid_id": int(raid.id),
        "slot_summaries_total": len(after),
        "slot_summaries_created": max(0, len(after) - before_n),
    }


async def admin_force_generate(session: AsyncSession, raid: GuildRaid) -> dict[str, Any]:
    log = await process_raid_daily_generate(session, raid, force=True)
    if not log:
        return {"error": "generate_failed"}
    return {
        "success": True,
        "log_id": int(log.id),
        "day_index": int(log.day_index),
        "raid_id": int(raid.id),
    }


async def admin_force_deliver(session: AsyncSession, raid: GuildRaid) -> dict[str, Any]:
    log = (
        await session.execute(
            select(GuildRaidDailyLog)
            .where(
                GuildRaidDailyLog.raid_id == raid.id,
                GuildRaidDailyLog.generated_at.isnot(None),
                GuildRaidDailyLog.delivered_at.is_(None),
            )
            .order_by(GuildRaidDailyLog.day_index.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not log:
        return {"error": "no_pending_deliver"}
    await deliver_raid_daily(session, log)
    await session.refresh(log)
    pv = log.poll_votes_json or {}
    return {
        "success": True,
        "log_id": int(log.id),
        "day_index": int(log.day_index),
        "poll_id": pv.get("__telegram_poll_id__"),
    }


async def admin_force_resolve(session: AsyncSession, raid: GuildRaid) -> dict[str, Any]:
    log = (
        await session.execute(
            select(GuildRaidDailyLog)
            .where(
                GuildRaidDailyLog.raid_id == raid.id,
                GuildRaidDailyLog.delivered_at.isnot(None),
                GuildRaidDailyLog.resolved_at.is_(None),
            )
            .order_by(GuildRaidDailyLog.day_index.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not log:
        return {"error": "no_pending_resolve"}
    await resolve_raid_daily_poll(session, log)
    await session.refresh(raid)
    await session.refresh(log)
    winner = log.winning_tactic_json or {}
    return {
        "success": True,
        "log_id": int(log.id),
        "day_index": int(log.day_index),
        "tactic_label": winner.get("label"),
        "company_vitality": int(raid.company_vitality or 0),
        "story_progress": int(raid.story_progress or 0),
        "raid_status": str(raid.status),
    }


_CANCEL_RAID_MESSAGES: dict[str, str] = {
    "admin": "Рейд гильдии [{tag}] отменён администратором.",
    "leader_left": "Рейд гильдии [{tag}] отменён: глава покинул отряд.",
    "leader_cancel": "Рейд гильдии [{tag}] отменён главой гильдии.",
    "no_participants": "Рейд гильдии [{tag}] отменён: в отряде не осталось участников.",
}


async def leader_cancel_raid(session: AsyncSession, player_id: int) -> dict[str, Any]:
    ctx = await _require_guild_leader(session, player_id)
    if isinstance(ctx, dict):
        return ctx
    _mem, guild = ctx
    if not guild.raid_active_id:
        return {"error": "no_active_raid"}
    raid = await session.get(GuildRaid, guild.raid_active_id)
    if not raid or raid.status != "active":
        guild.raid_active_id = None
        await session.commit()
        return {"error": "no_active_raid"}
    await cancel_guild_raid(session, raid, guild, reason="leader_cancel")
    await session.commit()
    return {"success": True, "raid_id": int(raid.id)}


async def cancel_guild_raid(
    session: AsyncSession,
    raid: GuildRaid,
    guild: Guild,
    *,
    reason: str = "admin",
    notify: bool = True,
) -> None:
    raid.status = "cancelled"
    guild.raid_active_id = None
    await session.flush()
    if not notify:
        return
    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        if bot and guild.telegram_chat_id:
            template = _CANCEL_RAID_MESSAGES.get(reason, _CANCEL_RAID_MESSAGES["admin"])
            await bot.send_message(
                chat_id=int(guild.telegram_chat_id),
                text=template.format(tag=guild.tag),
            )
    except Exception:
        logger.exception("cancel_guild_raid notify failed raid_id=%s reason=%s", raid.id, reason)


async def admin_stop_raid(
    session: AsyncSession,
    raid: GuildRaid,
    guild: Guild,
    *,
    mode: str = "abort",
) -> dict[str, Any]:
    if mode == "defeat":
        await _finish_raid(session, raid, guild, "defeat")
        await session.commit()
        return {"success": True, "mode": "defeat", "raid_id": int(raid.id)}

    await cancel_guild_raid(session, raid, guild, reason="admin")
    return {"success": True, "mode": "abort", "raid_id": int(raid.id)}


async def admin_add_participant(
    session: AsyncSession,
    raid: GuildRaid,
    guild: Guild,
    player_id: int,
) -> dict[str, Any]:
    pid = int(player_id)
    gm = (
        await session.execute(
            select(GuildMember).where(GuildMember.guild_id == guild.id, GuildMember.player_id == pid)
        )
    ).scalar_one_or_none()
    if not gm:
        return {"error": "not_guild_member", "player_id": pid}

    existing = (
        await session.execute(
            select(GuildRaidParticipant).where(
                GuildRaidParticipant.raid_id == raid.id,
                GuildRaidParticipant.player_id == pid,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return {"error": "already_participant", "player_id": pid}

    thr = await session.get(GuildLevelThreshold, guild.level)
    max_slots = int(thr.raid_party_slots) if thr else 5
    parts = (
        await session.execute(select(GuildRaidParticipant).where(GuildRaidParticipant.raid_id == raid.id))
    ).scalars().all()
    if len(parts) >= max_slots:
        return {"error": "slots_full", "max": max_slots}

    session.add(GuildRaidParticipant(raid_id=raid.id, player_id=pid))
    await session.flush()
    pids = [int(p.player_id) for p in parts] + [pid]
    raid.party_snapshot_json = await _build_party_snapshot(session, pids)

    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        await bot.send_message(
            chat_id=pid,
            text=f"Вас добавили в активный рейд гильдии [{guild.tag}].",
        )
    except Exception:
        logger.debug("admin_add_participant DM failed pid=%s", pid)

    return {"success": True, "player_id": pid, "participant_count": len(pids)}

"""Guild raid v2: weekly chronicle (muster, chat log, daily MSK pipeline)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import (
    Guild,
    GuildLevelThreshold,
    GuildMember,
    GuildRaid,
    GuildRaidChatEvent,
    GuildRaidDailyLog,
    GuildRaidMuster,
    GuildRaidParticipant,
    GuildRaidTemplate,
    MainWaifu,
)
from waifu_bot.services.abyss_service import msk_now, msk_today
from waifu_bot.services.guild_raid_mechanics import (
    MUSTER_HOURS,
    NEUTRAL_TACTIC,
    RAID_WEEK_DAYS,
    TACTIC_POLL_HOURS,
    gxp_multiplier_for_outcome,
    mechanics_for_tactic_option,
    outcome_tier,
    resolve_daily_tactic,
)
from waifu_bot.services.guild_raid_narrative_ai import (
    generate_raid_daily_narrative,
    generate_raid_defeat_epilogue,
    generate_raid_finale,
    generate_raid_prologue,
    pick_random_raid_setting,
)
from waifu_bot.services.guild_progress import add_gxp

logger = logging.getLogger(__name__)
_MSK = ZoneInfo("Europe/Moscow")

_last_guild_raid_daily_gen: date | None = None
_last_guild_raid_daily_deliver: date | None = None
_last_guild_raid_daily_resolve: date | None = None

MUSTER_STATUS_PENDING = "pending"
MUSTER_STATUS_COMPLETED = "completed"
MUSTER_STATUS_CANCELLED = "cancelled"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    existing = await get_active_muster(session, guild.id)
    if existing:
        return {"error": "muster_already_active", "muster": muster_public_state(existing)}

    thr = await session.get(GuildLevelThreshold, guild.level)
    max_slots = int(thr.raid_party_slots) if thr else 5
    pids = list(dict.fromkeys(int(x) for x in participant_ids))[:max_slots]
    if len(pids) < 2:
        return {"error": "need_participants", "min": 2}
    for pid in pids:
        gm = await session.execute(
            select(GuildMember).where(GuildMember.guild_id == guild.id, GuildMember.player_id == pid)
        )
        if gm.scalar_one_or_none() is None:
            return {"error": "not_all_guild_members", "player_id": pid}

    if int(chat_id) == 0:
        return {"error": "need_guild_chat"}
    guild.telegram_chat_id = int(chat_id)

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


async def _complete_muster_and_start_raid(session: AsyncSession, muster: GuildRaidMuster) -> dict[str, Any]:
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
    loc_id, style_id = pick_random_raid_setting()
    chat_id = int(guild.telegram_chat_id or 0)
    if not chat_id:
        muster.status = MUSTER_STATUS_CANCELLED
        await session.commit()
        return {"error": "need_guild_chat"}

    prologue = await generate_raid_prologue(
        guild_name=guild.name,
        guild_tag=guild.tag,
        location_archetype_id=loc_id,
        narrative_style_id=style_id,
        party=party,
    )

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
        narrative_style_id=style_id,
        party_snapshot_json=party,
        adventure_meta_json={"prologue_html": prologue, "guild_tag": guild.tag, "guild_name": guild.name},
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

    await _deliver_prologue(session, raid, guild, prologue, pids)
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
    return min(7, local.hour // 3)


def _slot_label(idx: int) -> str:
    start = idx * 3
    end = start + 2
    return f"{start:02d}:00–{end:02d}:59 МСК"


async def aggregate_chat_slots(
    session: AsyncSession,
    raid_id: int,
    for_date: date,
) -> list[dict[str, Any]]:
    day_start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=_MSK).astimezone(timezone.utc)
    day_end = day_start + timedelta(days=1)
    q = await session.execute(
        select(GuildRaidChatEvent).where(
            GuildRaidChatEvent.raid_id == raid_id,
            GuildRaidChatEvent.event_ts >= day_start,
            GuildRaidChatEvent.event_ts < day_end,
        )
    )
    events = q.scalars().all()
    slots: list[dict[str, Any]] = []
    for idx in range(8):
        slots.append({"slot_index": idx, "slot_label": _slot_label(idx), "rest": True, "active_players": [], "messages": 0})

    player_names: dict[int, str] = {}
    raid = await session.get(GuildRaid, raid_id)
    for p in raid.party_snapshot_json or [] if raid else []:
        player_names[int(p.get("player_id") or 0)] = str(p.get("name") or "")

    by_slot: dict[int, dict[int, int]] = {i: {} for i in range(8)}
    for ev in events:
        si = _msk_slot_index(ev.event_ts)
        by_slot[si][int(ev.player_id)] = by_slot[si].get(int(ev.player_id), 0) + 1
        slots[si]["rest"] = False
        slots[si]["messages"] = int(slots[si]["messages"]) + 1

    for idx in range(8):
        active = []
        for pid, cnt in sorted(by_slot[idx].items(), key=lambda x: -x[1]):
            nm = player_names.get(pid) or f"Игрок {pid}"
            active.append(f"{nm} ({cnt})")
        slots[idx]["active_players"] = active
    return slots


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
        if str(pv.get("__telegram_poll_id__") or "") != str(telegram_poll_id):
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


async def process_raid_daily_generate(
    session: AsyncSession, raid: GuildRaid, *, force: bool = False
) -> GuildRaidDailyLog | None:
    if int(getattr(raid, "raid_version", 1) or 1) < 2 or raid.status != "active":
        return None
    day_index = int(raid.day_index or 0) + 1
    if day_index > RAID_WEEK_DAYS:
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

    game_date = msk_today()
    slot_beats = await aggregate_chat_slots(session, raid.id, game_date)
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

    narrative, raw_tactics = await generate_raid_daily_narrative(
        guild_name=guild.name,
        guild_tag=guild.tag,
        day_index=day_index,
        location_archetype_id=str(raid.location_archetype_id or "forest"),
        narrative_style_id=int(raid.narrative_style_id or 1),
        party=list(raid.party_snapshot_json or []),
        slot_beats=slot_beats,
        company_vitality=int(raid.company_vitality or 0),
        story_progress=int(raid.story_progress or 0),
        last_tactic=raid.last_tactic_choice_json,
        last_resolve=raid.last_resolve_json,
        chronicle_summaries=chronicle,
    )
    tactics = _tactic_options_with_mechanics(raw_tactics)

    log = GuildRaidDailyLog(
        raid_id=raid.id,
        day_index=day_index,
        game_date=game_date,
        narrative_html=narrative,
        slot_beats_json=slot_beats,
        tactic_poll_options_json=tactics,
        generated_at=_utc_now(),
    )
    session.add(log)
    await session.flush()
    return log


async def deliver_raid_daily(session: AsyncSession, log: GuildRaidDailyLog) -> None:
    if log.delivered_at:
        return
    raid = await session.get(GuildRaid, log.raid_id)
    if not raid or raid.status != "active":
        return
    guild = await session.get(Guild, raid.guild_id)
    if not guild or not guild.telegram_chat_id:
        return

    from waifu_bot.services.webhook import get_bot

    bot = get_bot()
    chat_id = int(guild.telegram_chat_id)
    narrative = (log.narrative_html or "")[:4000]
    await bot.send_message(chat_id=chat_id, text=narrative)

    options = [str(t.get("label") or f"Вариант {i+1}")[:90] for i, t in enumerate(log.tactic_poll_options_json or [])]
    if not options:
        options = [NEUTRAL_TACTIC["label"], "Форсировать переход", "Рискованный рейд"]

    poll_msg = await bot.send_poll(
        chat_id=chat_id,
        question=f"Тактика на день {log.day_index} (3 ч)",
        options=options,
        is_anonymous=False,
        allows_multiple_answers=False,
    )
    log.poll_message_id = poll_msg.message_id
    log.poll_chat_id = chat_id
    log.poll_deadline_at = _utc_now() + timedelta(hours=TACTIC_POLL_HOURS)
    log.delivered_at = _utc_now()
    poll_id = poll_msg.poll.id if poll_msg.poll else None
    log.poll_votes_json = {"__telegram_poll_id__": poll_id, "votes": {}}
    raid.day_index = int(log.day_index)

    parts = (
        await session.execute(select(GuildRaidParticipant.player_id).where(GuildRaidParticipant.raid_id == raid.id))
    ).scalars().all()
    for pid in parts:
        try:
            dm_poll = await bot.send_poll(
                chat_id=int(pid),
                question=f"Рейд: тактика дня {log.day_index}",
                options=options,
                is_anonymous=False,
                allows_multiple_answers=False,
            )
            if not log.poll_votes_json:
                log.poll_votes_json = {}
        except Exception:
            logger.debug("raid poll DM failed pid=%s", pid)

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


_last_guild_raid_daily_gen: date | None = None
_last_guild_raid_daily_deliver: date | None = None
_last_guild_raid_daily_resolve: date | None = None


async def tick_raid_daily_msk(session: AsyncSession) -> None:
    """Run 04:50 generate, 05:00 deliver, 08:00 resolve once per MSK day window."""
    global _last_guild_raid_daily_gen, _last_guild_raid_daily_deliver, _last_guild_raid_daily_resolve

    now_msk = msk_now()
    today = now_msk.date()
    h, m = now_msk.hour, now_msk.minute

    q = await session.execute(
        select(GuildRaid).where(GuildRaid.status == "active", GuildRaid.raid_version >= 2)
    )
    raids = q.scalars().all()
    if not raids:
        return

    for raid in raids:
        try:
            if h == 4 and m >= 50 and _last_guild_raid_daily_gen != today:
                log = await process_raid_daily_generate(session, raid)
                if log:
                    _last_guild_raid_daily_gen = today
                    await session.commit()
            elif h == 5 and m < 10 and _last_guild_raid_daily_deliver != today:
                day_index = int(raid.day_index or 0) + 1
                if day_index > RAID_WEEK_DAYS:
                    continue
                dl_q = await session.execute(
                    select(GuildRaidDailyLog).where(
                        GuildRaidDailyLog.raid_id == raid.id,
                        GuildRaidDailyLog.day_index == day_index,
                        GuildRaidDailyLog.generated_at.isnot(None),
                        GuildRaidDailyLog.delivered_at.is_(None),
                    )
                )
                log = dl_q.scalar_one_or_none()
                if log:
                    await deliver_raid_daily(session, log)
                    _last_guild_raid_daily_deliver = today
            elif h == 8 and m < 10 and _last_guild_raid_daily_resolve != today:
                dl_q = await session.execute(
                    select(GuildRaidDailyLog).where(
                        GuildRaidDailyLog.raid_id == raid.id,
                        GuildRaidDailyLog.delivered_at.isnot(None),
                        GuildRaidDailyLog.resolved_at.is_(None),
                    ).order_by(GuildRaidDailyLog.day_index.desc()).limit(1)
                )
                log = dl_q.scalar_one_or_none()
                if log:
                    await resolve_raid_daily_poll(session, log)
                    _last_guild_raid_daily_resolve = today
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

    raid.status = "cancelled"
    guild.raid_active_id = None
    await session.flush()
    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        if bot and guild.telegram_chat_id:
            await bot.send_message(
                chat_id=int(guild.telegram_chat_id),
                text=f"Рейд гильдии [{guild.tag}] отменён администратором.",
            )
    except Exception:
        logger.exception("admin_stop_raid notify failed raid_id=%s", raid.id)
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

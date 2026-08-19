"""Daily GD participate prefs: list chats, upsert toggle, enroll filter."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GDCycle, GDPlayerChatPref, GDRegistration
from waifu_bot.game.msk_time import msk_next_datetime
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map
from waifu_bot.services.gd_cycle_service import GDCycleService
from waifu_bot.services.gd_daily_stats import chat_message_share_pct
from waifu_bot.services.player_chats import (
    list_player_active_bot_group_chats,
    player_has_active_bot_chat,
)


def participate_pref_enabled(row: GDPlayerChatPref | None) -> bool:
    """Missing pref row means the player is enrolled by default."""
    if row is None:
        return True
    return bool(row.participate)


def filter_enroll_candidate_ids(
    candidate_ids: Iterable[int], opt_out_ids: Iterable[int]
) -> list[int]:
    blocked = {int(x) for x in opt_out_ids}
    return [int(uid) for uid in candidate_ids if int(uid) not in blocked]


def player_share_pct(player_msgs: int, chat_total: int) -> float:
    """0–100 with one decimal, for the WebApp share bar."""
    return round(chat_message_share_pct(int(player_msgs), int(chat_total)), 1)


def sort_gd_chat_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            0 if r.get("in_today_roster") else 1,
            str(r.get("title") or "").lower(),
            int(r.get("chat_id") or 0),
        ),
    )


def is_daily_gd_cycle(cycle: GDCycle | None) -> bool:
    if cycle is None:
        return False
    state = cycle.battle_state_json or {}
    return str(state.get("mode") or "") == "daily" or getattr(cycle, "game_date", None) is not None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def build_gd_chat_row(
    *,
    chat_id: int,
    title: str,
    participate: bool,
    cycle: GDCycle | None,
    registration: GDRegistration | None,
    chat_msg_total: int,
) -> dict[str, Any]:
    in_roster = (
        registration is not None
        and cycle is not None
        and str(cycle.status) == "active"
        and is_daily_gd_cycle(cycle)
    )
    stats = dict(getattr(registration, "day_stats_json", None) or {}) if registration else {}
    try:
        player_msgs = int(stats.get("msg_total") or 0) if registration else 0
    except (TypeError, ValueError):
        player_msgs = 0
    try:
        chat_total = int(chat_msg_total or 0) if cycle else 0
    except (TypeError, ValueError):
        chat_total = 0
    game_date = getattr(cycle, "game_date", None) if cycle else None
    return {
        "chat_id": int(chat_id),
        "title": (title or "").strip() or f"Чат {int(chat_id)}",
        "participate": bool(participate),
        "in_today_roster": bool(in_roster),
        "cycle_id": int(cycle.id) if cycle is not None else None,
        "game_date": game_date.isoformat() if game_date is not None else None,
        "ends_at": _iso(getattr(cycle, "ends_at", None) if cycle else None),
        "player_msg_total": max(0, player_msgs),
        "chat_msg_total": max(0, chat_total),
        "player_share_pct": player_share_pct(player_msgs, chat_total),
    }


async def load_gd_opt_out_player_ids(
    session: AsyncSession, chat_id: int, candidate_ids: list[int]
) -> set[int]:
    if not candidate_ids:
        return set()
    rows = (
        await session.execute(
            select(GDPlayerChatPref.player_id).where(
                GDPlayerChatPref.chat_id == int(chat_id),
                GDPlayerChatPref.player_id.in_([int(x) for x in candidate_ids]),
                GDPlayerChatPref.participate.is_(False),
            )
        )
    ).all()
    return {int(r[0]) for r in rows}


async def next_daily_start_hint(session: AsyncSession, *, now: datetime | None = None) -> str:
    cfg = await get_game_config_map(session)
    start_h = cfg_int(cfg, "gd_daily_start_hour_msk", 4)
    start_m = cfg_int(cfg, "gd_daily_start_minute_msk", 30)
    nxt = msk_next_datetime(start_h, start_m, after=now)
    iso = _iso(nxt)
    return iso or ""


async def list_gd_player_chats(
    session: AsyncSession,
    player_id: int,
    gd: GDCycleService,
) -> dict[str, Any]:
    pid = int(player_id)
    chats = await list_player_active_bot_group_chats(session, pid)
    chat_ids = [int(c["chat_id"]) for c in chats]
    pref_map: dict[int, bool] = {}
    cycle_by_chat: dict[int, GDCycle] = {}
    reg_by_cycle: dict[int, GDRegistration] = {}
    if chat_ids:
        pref_rows = (
            await session.execute(
                select(GDPlayerChatPref).where(
                    GDPlayerChatPref.player_id == pid,
                    GDPlayerChatPref.chat_id.in_(chat_ids),
                )
            )
        ).scalars().all()
        pref_map = {int(r.chat_id): bool(r.participate) for r in pref_rows}

        cycles = (
            await session.execute(
                select(GDCycle).where(
                    GDCycle.chat_id.in_(chat_ids),
                    GDCycle.status == "active",
                )
            )
        ).scalars().all()
        for cycle in cycles:
            if is_daily_gd_cycle(cycle):
                cycle_by_chat[int(cycle.chat_id)] = cycle

        cycle_ids = [c.id for c in cycle_by_chat.values()]
        if cycle_ids:
            regs = (
                await session.execute(
                    select(GDRegistration).where(
                        GDRegistration.cycle_id.in_(cycle_ids),
                        GDRegistration.user_id == pid,
                    )
                )
            ).scalars().all()
            reg_by_cycle = {int(r.cycle_id): r for r in regs}

    rows: list[dict[str, Any]] = []
    for chat in chats:
        cid = int(chat["chat_id"])
        cycle = cycle_by_chat.get(cid)
        reg = reg_by_cycle.get(int(cycle.id)) if cycle is not None else None
        chat_total = await gd.get_chat_msg_total(cycle) if cycle is not None else 0
        rows.append(
            build_gd_chat_row(
                chat_id=cid,
                title=str(chat.get("title") or ""),
                participate=pref_map.get(cid, True),
                cycle=cycle,
                registration=reg,
                chat_msg_total=chat_total,
            )
        )
    return {
        "chats": sort_gd_chat_rows(rows),
        "next_start_hint": await next_daily_start_hint(session),
    }


async def set_gd_participate(
    session: AsyncSession,
    player_id: int,
    chat_id: int,
    participate: bool,
) -> dict[str, Any]:
    pid = int(player_id)
    cid = int(chat_id)
    if not await player_has_active_bot_chat(session, pid, cid):
        return {"error": "forbidden", "message": "Чат недоступен."}
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(GDPlayerChatPref)
        .values(
            player_id=pid,
            chat_id=cid,
            participate=bool(participate),
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["player_id", "chat_id"],
            set_={"participate": bool(participate), "updated_at": now},
        )
    )
    await session.execute(stmt)
    return {"ok": True, "chat_id": cid, "participate": bool(participate)}

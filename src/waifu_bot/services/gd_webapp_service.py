"""GD v1 WebApp: available chats, muster invite, joinable cycles."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models import GDCycle, GDDungeonTemplate, GDRegistration
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.gd_cycle_service import GDCycleService
from waifu_bot.services.gd_scaling import late_join_reward_stage_mult
from waifu_bot.services.player_chats import (
    list_player_active_bot_group_chats,
    player_has_active_bot_chat,
)

logger = logging.getLogger(__name__)

REDIS_MUSTER_TS = "gd_muster_ts:"


def _bot_deep_link(payload: str) -> str | None:
    un = (settings.bot_username or "").strip().lstrip("@")
    if not un:
        return None
    return f"https://t.me/{un}?start={payload}"


def build_gd_muster_invite_text(
    *,
    dungeon_name: str,
    chat_id: int,
    registration_closes: datetime | None,
    party_count: int,
    max_party: int,
) -> str:
    closes_bit = ""
    if registration_closes is not None:
        closes = registration_closes
        if closes.tzinfo is None:
            closes = closes.replace(tzinfo=timezone.utc)
        from zoneinfo import ZoneInfo

        closes_bit = (
            f"\nОкно записи до {closes.astimezone(ZoneInfo('Europe/Moscow')).strftime('%H:%M')} МСК."
        )
    deep = _bot_deep_link(f"gd_join_{chat_id}")
    link_bit = f"\nВступить в ЛС: {deep}" if deep else "\nВступить: /gd_join в группе или во вкладке «Групповые»."
    return (
        f"⚔️ Сбор в «{dungeon_name}»!\n"
        f"Отряд: {party_count}/{max_party}.{closes_bit}"
        f"{link_bit}\n"
        "Или откройте вкладку «Групповые» в WebApp."
    )


async def _party_count_for_cycle(session: AsyncSession, cycle: GDCycle) -> int:
    from sqlalchemy import func

    if cycle.status == "active":
        party = (cycle.battle_state_json or {}).get("party") or []
        if isinstance(party, list) and party:
            return len(party)
    return int(
        await session.scalar(
            select(func.count())
            .select_from(GDRegistration)
            .where(GDRegistration.cycle_id == cycle.id)
        )
        or 0
    )


async def _chat_cycle_flags(
    session: AsyncSession,
    chat_id: int,
    player_id: int,
    gd: GDCycleService,
    cfg: dict[str, str],
) -> dict[str, Any]:
    """Status flag for available-chats picker."""
    max_party = cfg_int(cfg, "gd_max_party_size", 10)
    active = await gd.get_active_v1_cycle(session, chat_id)
    if active:
        state = active.battle_state_json or {}
        wave = str(state.get("wave") or "")
        party_count = await _party_count_for_cycle(session, active)
        joined = await session.scalar(
            select(GDRegistration.id).where(
                GDRegistration.cycle_id == active.id,
                GDRegistration.user_id == player_id,
            )
        )
        base = {
            "cycle_id": active.id,
            "cycle_status": "active",
            "wave": wave,
            "party_count": party_count,
            "max_party": max_party,
        }
        if joined:
            return {**base, "flag": "already_joined"}
        if wave == "done":
            return {**base, "flag": "active", "joinable": False}
        return {
            **base,
            "flag": "active",
            "joinable": True,
            "collecting_for_round": int(state.get("collecting_for_round") or 1),
        }

    reg = await gd.get_registration_cycle(session, chat_id)
    if reg:
        party_count = await _party_count_for_cycle(session, reg)
        joined = await session.scalar(
            select(GDRegistration.id).where(
                GDRegistration.cycle_id == reg.id,
                GDRegistration.user_id == player_id,
            )
        )
        base = {
            "cycle_id": reg.id,
            "cycle_status": "registration",
            "party_count": party_count,
            "max_party": max_party,
        }
        if joined:
            return {**base, "flag": "already_joined"}
        return {
            **base,
            "flag": "registration",
            "joinable": True,
            "registration_closes": reg.registration_closes.isoformat()
            if reg.registration_closes
            else None,
        }

    # Cooldown check without opening a cycle
    cooldown_h = cfg_float(cfg, "gd_cooldown_after_finish_hours", 168.0)
    if cooldown_h > 0:
        last = (
            await session.execute(
                select(GDCycle)
                .where(
                    GDCycle.chat_id == chat_id,
                    GDCycle.status == "finished",
                    GDCycle.finished_at.isnot(None),
                )
                .order_by(GDCycle.finished_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last and last.finished_at:
            fin = last.finished_at
            if fin.tzinfo is None:
                fin = fin.replace(tzinfo=timezone.utc)
            unlock = fin + timedelta(hours=float(cooldown_h))
            if unlock > datetime.now(timezone.utc):
                return {
                    "flag": "cooldown",
                    "unlock_at": unlock.isoformat(),
                    "joinable": False,
                    "party_count": 0,
                    "max_party": max_party,
                }
    return {
        "flag": "none",
        "joinable": False,
        "party_count": 0,
        "max_party": max_party,
    }


async def list_gd_available_chats(
    session: AsyncSession,
    player_id: int,
    gd: GDCycleService,
) -> list[dict[str, Any]]:
    cfg = await get_game_config_map(session)
    chats = await list_player_active_bot_group_chats(session, player_id)
    out: list[dict[str, Any]] = []
    for ch in chats:
        flags = await _chat_cycle_flags(session, int(ch["chat_id"]), player_id, gd, cfg)
        row = dict(ch)
        row.update(flags)
        out.append(row)
    return out


async def list_gd_joinable_dungeons(
    session: AsyncSession,
    player_id: int,
    gd: GDCycleService,
) -> list[dict[str, Any]]:
    """Cycles in player's bot chats where the player is not yet registered."""
    cfg = await get_game_config_map(session)
    chats = await list_player_active_bot_group_chats(session, player_id)
    chat_ids = [int(c["chat_id"]) for c in chats]
    if not chat_ids:
        return []
    title_by = {int(c["chat_id"]): c for c in chats}
    rows = (
        await session.execute(
            select(GDCycle, GDDungeonTemplate)
            .outerjoin(GDDungeonTemplate, GDDungeonTemplate.id == GDCycle.dungeon_template_id)
            .where(
                GDCycle.chat_id.in_(chat_ids),
                GDCycle.status.in_(("registration", "active")),
            )
            .order_by(GDCycle.id.desc())
        )
    ).all()
    out: list[dict[str, Any]] = []
    for cycle, tmpl in rows:
        already = await session.scalar(
            select(GDRegistration.id).where(
                GDRegistration.cycle_id == cycle.id,
                GDRegistration.user_id == player_id,
            )
        )
        if already:
            continue
        state = cycle.battle_state_json or {}
        wave = str(state.get("wave") or "")
        if cycle.status == "active" and wave == "done":
            continue
        collecting = int(state.get("collecting_for_round") or 1)
        joined_preview = collecting if cycle.status == "active" else 1
        total_est = max(8, int(cycle.total_rounds or 12))
        stage_mult = late_join_reward_stage_mult(joined_preview, total_est, cfg)
        meta = title_by.get(int(cycle.chat_id), {})
        out.append(
            {
                "v1": True,
                "id": cycle.id,
                "chat_id": int(cycle.chat_id),
                "chat_title": meta.get("title"),
                "telegram_url": meta.get("telegram_url"),
                "dungeon_name": (tmpl.name if tmpl else None) or "Подземелье",
                "cycle_status": cycle.status,
                "collecting_for_round": collecting,
                "wave": wave or None,
                "joined_at_round_preview": joined_preview,
                "reward_stage_mult": round(stage_mult, 3),
                "reward_stage_pct": int(round(100 * stage_mult)),
                "registration_closes": cycle.registration_closes.isoformat()
                if cycle.status == "registration" and cycle.registration_closes
                else None,
                "party_count": len(state.get("party") or [])
                if cycle.status == "active"
                else None,
            }
        )
    return out


async def muster_gd_in_chat(
    session: AsyncSession,
    player_id: int,
    chat_id: int,
    gd: GDCycleService,
    bot: Any | None,
) -> dict[str, Any]:
    """Open (or reuse) registration and post one invite to the group."""
    cid = int(chat_id)
    if not await player_has_active_bot_chat(session, player_id, cid):
        return {
            "error": "forbidden",
            "message": "Чат недоступен: бот и вы должны быть в одной группе "
            "(напишите любое сообщение в группе с ботом).",
        }
    if await gd.get_active_v1_cycle(session, cid):
        return {
            "error": "active",
            "message": "В этом чате поход уже идёт — откройте «Доступно вступление».",
        }

    cfg = await get_game_config_map(session)
    already_open = await gd.get_registration_cycle_any(session, cid) is not None
    gd._last_cooldown_unlock_at = None
    cycle = await gd.ensure_registration_cycle(session, cid)
    if not cycle:
        if getattr(gd, "_last_cooldown_unlock_at", None) is not None:
            unlock = gd._last_cooldown_unlock_at
            return {
                "error": "cooldown",
                "message": (
                    f"Кулдаун после прошлого похода до "
                    f"{unlock.astimezone().strftime('%d.%m %H:%M')} UTC."
                ),
                "unlock_at": unlock.isoformat(),
            }
        return {"error": "closed", "message": "Не удалось открыть регистрацию."}

    # Auto-join the muster starter into the party
    join_result = await gd.register_join(session, cid, player_id)
    join_err = join_result.get("error") if isinstance(join_result, dict) else None
    if join_err and join_err != "duplicate":
        return {
            "error": join_err,
            "message": join_result.get("message")
            or "Не удалось записаться в отряд после открытия сбора.",
            "cycle_id": cycle.id,
            "join": join_result,
        }

    from sqlalchemy import func

    party_count = int(
        await session.scalar(
            select(func.count())
            .select_from(GDRegistration)
            .where(GDRegistration.cycle_id == cycle.id)
        )
        or 0
    )
    max_party = cfg_int(cfg, "gd_max_party_size", 10)
    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
    dungeon_name = tpl.name if tpl else "Подземелье"
    deep = _bot_deep_link(f"gd_join_{cid}")

    posted = False
    skipped_rate = False
    cooldown_s = cfg_int(cfg, "gd_muster_repost_cooldown_seconds", 300)
    now_ts = time.time()
    redis = gd.redis
    can_post = True
    if redis and already_open:
        try:
            raw = await redis.get(f"{REDIS_MUSTER_TS}{cid}")
            if raw is not None:
                last = float(raw)
                if now_ts - last < float(cooldown_s):
                    can_post = False
                    skipped_rate = True
        except Exception:
            logger.debug("muster redis get failed", exc_info=True)

    if bot and can_post:
        text = build_gd_muster_invite_text(
            dungeon_name=dungeon_name,
            chat_id=cid,
            registration_closes=cycle.registration_closes,
            party_count=party_count,
            max_party=max_party,
        )
        try:
            await bot.send_message(chat_id=cid, text=text)
            posted = True
            if redis:
                try:
                    await redis.set(
                        f"{REDIS_MUSTER_TS}{cid}",
                        str(now_ts),
                        ex=max(3600, cooldown_s * 4),
                    )
                except Exception:
                    logger.debug("muster redis set failed", exc_info=True)
        except Exception:
            logger.exception("GD muster message failed chat_id=%s", cid)
            return {
                "error": "send_failed",
                "message": "Не удалось отправить сообщение в чат (права бота?).",
                "cycle_id": cycle.id,
            }
    elif not bot:
        logger.warning("GD muster: bot=None, invite not sent chat_id=%s", cid)

    return {
        "success": True,
        "cycle_id": cycle.id,
        "chat_id": cid,
        "dungeon_name": dungeon_name,
        "already_open": already_open,
        "invite_posted": posted,
        "invite_skipped_rate_limit": skipped_rate,
        "party_count": party_count,
        "max_party": max_party,
        "registration_closes": cycle.registration_closes.isoformat()
        if cycle.registration_closes
        else None,
        "deep_link": deep,
        "join": join_result,
    }


async def join_gd_from_webapp_or_dm(
    session: AsyncSession,
    player_id: int,
    chat_id: int,
    gd: GDCycleService,
    bot: Any | None = None,
    *,
    require_membership: bool = True,
) -> dict[str, Any]:
    """Membership-checked join (registration or late). Optionally announce late join in group."""
    cid = int(chat_id)
    if require_membership and not await player_has_active_bot_chat(session, player_id, cid):
        return {
            "error": "forbidden",
            "message": "Чат недоступен: напишите сообщение в группе с ботом, затем повторите.",
        }
    result = await gd.join_chat(session, cid, player_id)
    if result.get("success") and result.get("late_join") and bot:
        name = result.get("name") or "Вайфу"
        try:
            pct = int(round(100 * float(result.get("reward_stage_mult") or 1)))
            await bot.send_message(
                chat_id=cid,
                text=f"➕ {name} присоединилась к отряду (награда ~{pct}% от полного похода).",
            )
        except Exception:
            logger.debug("late join announce failed", exc_info=True)
    return result


async def stop_gd_for_player(
    session: AsyncSession,
    player_id: int,
    gd: GDCycleService,
    bot: Any | None = None,
    *,
    chat_id: int | None = None,
    cycle_id: int | None = None,
) -> dict[str, Any]:
    """Registered participant stops an active GD (no victory rewards).

    Prefer cycle_id (DB lookup, bypasses Redis). chat_id is fallback via DB query.
    """
    cfg = await get_game_config_map(session)
    if cfg_int(cfg, "gd_stop_enabled", 1) != 1:
        return {"error": "disabled", "message": "Завершение похода игроком отключено."}

    cycle: GDCycle | None = None
    if cycle_id is not None:
        cycle = await session.get(GDCycle, int(cycle_id))
        if cycle is not None and cycle.status != "active":
            cycle = None
    elif chat_id is not None:
        # DB-only: do not trust Redis negative cache
        cycle = (
            await session.execute(
                select(GDCycle)
                .where(GDCycle.chat_id == int(chat_id), GDCycle.status == "active")
                .limit(1)
            )
        ).scalar_one_or_none()
    else:
        return {"error": "bad_request", "message": "Укажите cycle_id или chat_id."}

    if not cycle:
        return {"error": "no_active", "message": "Нет активного похода."}

    joined = await session.scalar(
        select(GDRegistration.id).where(
            GDRegistration.cycle_id == cycle.id,
            GDRegistration.user_id == int(player_id),
        )
    )
    if not joined:
        return {
            "error": "forbidden",
            "message": "Завершить поход может только участник отряда.",
        }
    result = await gd.cancel_active_cycle(session, cycle, reason="player_stop")
    notify_chat = int(cycle.chat_id)
    if result.get("success") and bot:
        try:
            await bot.send_message(
                chat_id=notify_chat,
                text=(
                    "🏁 Поход завершён участником. Награды за победу не выдаются. "
                    "Новый сбор — через WebApp или /gd_join."
                ),
            )
        except Exception:
            logger.debug("GD stop notify failed", exc_info=True)
    return result

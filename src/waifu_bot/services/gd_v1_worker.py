"""GD v1.0: registration deadlines, round ticks, rewards."""
from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    GDCycle,
    GDDungeonTemplate,
    GDRound,
    GDRewardRow,
    GDRegistration,
    MainWaifu,
    Player,
)
from waifu_bot.db.session import get_session
from waifu_bot.game.constants import (
    GD_ROUND_DURATION_MINUTES_DEFAULT,
    GD_V1_START_CHAT_MESSAGE,
    MAX_LEVEL,
    WAIFU_CLASS_LABEL_RU,
    WAIFU_RACE_LABEL_RU,
)
from waifu_bot.game.formulas import calculate_total_experience_for_level
from waifu_bot.services.combat import apply_main_waifu_levelups
from waifu_bot.services.game_config_service import get_game_config_map, cfg_float, cfg_int
from waifu_bot.services.gd_scaling import (
    blend_dual_reward_scores,
    clean_run_bonus_multiplier,
    late_join_reward_stage_mult,
    power_score_from_contrib,
    presence_score_for_uid,
    reward_level_multiplier,
    wipe_reward_multiplier,
)
from waifu_bot.services.gd_cycle_service import GDCycleService
from waifu_bot.services import gd_active_cache as gd_active_cache_mod
from waifu_bot.services.gd_narrative_ai import (
    build_gd_folding_chronicle,
    generate_gd_finale_narrative,
    generate_gd_round_narrative,
    generate_gd_start_narrative,
)
from waifu_bot.services.gd_narrative_seeds import (
    merge_used_seed_ids,
    narrative_fingerprint,
    pick_absurd_event_seed,
    recent_fingerprints_from_rounds,
)
from waifu_bot.services.gd_battle_log import (
    format_gd_battle_hp_system_message,
    format_gd_group_compact_message,
    format_gd_round_battle_log_message,
)
from waifu_bot.services.gd_round_engine import (
    apply_admin_force_dungeon_victory_result,
    precheck_admin_force_dungeon_victory,
    process_gd_round,
)
from waifu_bot.services.guild_progress import apply_gd_round_guild_hooks

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

# Один активный process_gd_v1_round_for_cycle на cycle_id (воркер + /gd_v1_force_round в одном процессе).
_gd_v1_processing_cycle_ids: set[int] = set()


def gd_v1_try_begin_round_processing(cycle_id: int) -> bool:
    """
    Атомарно занять слот обработки раунда для cycle_id (до любого await в хендлере).
    Возвращает False, если цикл уже обрабатывается (воркер или другая команда).
    """
    if cycle_id in _gd_v1_processing_cycle_ids:
        return False
    _gd_v1_processing_cycle_ids.add(cycle_id)
    return True


def gd_v1_end_round_processing(cycle_id: int) -> None:
    """Освободить слот (после run_locked или при отмене в хендлере)."""
    _gd_v1_processing_cycle_ids.discard(cycle_id)


def _chunk_text(text: str, limit: int = 3900) -> list[str]:
    """Разбить длинный текст на сообщения <= limit, по возможности по границам строк."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        if len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue
        if len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return chunks


def format_gd_battle_hp_system_message(battle_state: dict[str, Any] | None) -> str:
    """Deprecated re-export — use gd_battle_log.format_gd_battle_hp_system_message."""
    from waifu_bot.services.gd_battle_log import (
        format_gd_battle_hp_system_message as _fmt,
    )

    return _fmt(battle_state)


def format_gd_round_battle_log_message(
    result: dict[str, Any], ctx: dict[str, Any]
) -> str:
    """Deprecated re-export — use gd_battle_log.format_gd_round_battle_log_message."""
    from waifu_bot.services.gd_battle_log import (
        format_gd_round_battle_log_message as _fmt,
    )

    return _fmt(result, ctx)


def _round_top_contributor_name(state: dict[str, Any] | None, ctx: dict[str, Any]) -> str | None:
    st = state or {}
    activity = st.get("activity_totals") or {}
    contrib = st.get("contribution") or {}
    party = list(ctx.get("party") or st.get("party") or [])
    name_by = {
        int(p["user_id"]): str(p.get("name") or f"Игрок {p['user_id']}")
        for p in party
        if p.get("user_id") is not None
    }
    scores: dict[int, float] = {}
    for uid_s in set(list(activity.keys()) + list(contrib.keys())):
        try:
            uid = int(uid_s)
        except (TypeError, ValueError):
            continue
        scores[uid] = presence_score_for_uid(uid, activity, contrib, floor=0.0) + power_score_from_contrib(
            contrib.get(str(uid))
        )
    if not scores:
        return None
    best = max(scores, key=lambda u: scores[u])
    if scores[best] <= 0:
        return None
    return name_by.get(best)


def _power_hint_for_narrative(state: dict[str, Any] | None) -> str | None:
    """Short RU hint that gear/level mattered (no raw numbers)."""
    st = state or {}
    party = list(st.get("party") or [])
    if not party:
        return None
    geared = [p for p in party if p.get("gear_aware") or p.get("weapon_damage")]
    if not geared:
        return None
    top = max(geared, key=lambda p: int(p.get("level") or 1) * 100 + int(p.get("weapon_damage") or 0))
    name = str(top.get("name") or "вайфу")
    return f"удар {name} ощутимо сильнее за счёт прокачки и экипировки"


def _compute_round_mvp(state: dict[str, Any] | None) -> tuple[int, str] | None:
    """MVP по накопленному вкладу/активности на момент раунда (для победного нарратива)."""
    st = state or {}
    contrib = st.get("contribution") or {}
    activity = st.get("activity_totals") or {}
    party = st.get("party") or []
    name_by_uid: dict[int, str] = {}
    for p in party:
        uid = p.get("user_id")
        if uid is not None:
            name_by_uid[int(uid)] = str(p.get("name") or f"Игрок {uid}")
    scores: dict[int, float] = {}
    for uid_str in set(list(contrib.keys()) + list(activity.keys())):
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            continue
        scores[uid] = presence_score_for_uid(uid, activity, contrib) + power_score_from_contrib(
            contrib.get(uid_str)
        )
    if not scores:
        return None
    mvp_uid = max(scores, key=lambda u: scores[u])
    return mvp_uid, name_by_uid.get(mvp_uid, f"Игрок {mvp_uid}")


async def _refresh_party_display_from_main_waifu(
    session: AsyncSession, party: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Имя/класс/раса/уровень из актуальной ОВ; HP и прочее состояние боя из снимка в party."""
    out: list[dict[str, Any]] = []
    for p in party:
        uid = int(p.get("user_id") or 0)
        if not uid:
            out.append(dict(p))
            continue
        w = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == uid))
        ).scalar_one_or_none()
        if not w:
            out.append(dict(p))
            continue
        m = dict(p)
        m["name"] = w.name
        m["class_id"] = int(w.class_)
        m["race_id"] = int(w.race)
        m["level"] = int(w.level or 1)
        out.append(m)
    return out


async def format_gd_v1_battle_status_report(session: AsyncSession, cycle: GDCycle) -> str:
    """Текстовый отчёт о текущем бое GD v1: подземелье, раунд, монстры, отряд (имя/уровень/класс/раса/HP)."""
    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
    dungeon_name = tpl.name if tpl else "—"
    st = cycle.battle_state_json or {}
    collecting = int(st.get("collecting_for_round") or 1)
    wave = st.get("wave")
    wave_ru = {
        "pending_init": "ожидание инициализации",
        "trash": "обычные враги",
        "boss": "босс",
        "done": "завершено",
    }.get(str(wave or ""), str(wave) if wave is not None else "—")

    raw_party = list(st.get("party") or [])
    party = await _refresh_party_display_from_main_waifu(session, raw_party)
    monsters = list(st.get("monsters") or [])

    lines: list[str] = [
        f"⚔️ Текущий бой GD v1",
        f"Подземелье: {dungeon_name}",
        f"Цикл: #{cycle.id}",
        f"Раунд (сбор действий): {collecting}",
        f"Последний записанный в журнале раунд: {int(cycle.current_round_number or 0)}",
        f"Волна: {wave_ru}",
        "",
        "Монстры:",
    ]
    if not monsters:
        lines.append("· нет данных в состоянии боя")
    else:
        for m in monsters:
            nm = str(m.get("name") or "Монстр")
            boss = " · босс" if m.get("is_boss") else ""
            lvl = m.get("level", "?")
            cur = int(m.get("hp") or 0)
            mx = max(1, int(m.get("max_hp") or 1))
            if cur <= 0:
                lines.append(f"· {nm}{boss} · ур. {lvl} · HP 0 / {mx} (повержен)")
            else:
                lines.append(f"· {nm}{boss} · ур. {lvl} · HP {cur} / {mx}")

    lines.extend(["", "Отряд:"])
    if not party:
        lines.append("· пусто")
    else:
        for p in party:
            name = str(p.get("name") or f"Игрок {p.get('user_id', '?')}")
            lvl = p.get("level", "?")
            cid = int(p.get("class_id") or 0)
            rid = int(p.get("race_id") or 0)
            cls_word = WAIFU_CLASS_LABEL_RU.get(cid, f"класс id {cid}")
            race_word = WAIFU_RACE_LABEL_RU.get(rid, f"раса id {rid}")
            cur = int(p.get("current_hp") or 0)
            mx = max(1, int(p.get("max_hp") or 1))
            fallen = bool(p.get("fallen")) or cur <= 0
            knock = " · нокдаун" if fallen else ""
            lines.append(
                f"· {name} · ур. {lvl} · {cls_word} · {race_word} · HP {cur} / {mx}{knock}"
            )

    if cycle.round_deadline_at is not None:
        lines.append("")
        lines.append(f"Дедлайн сбора раунда (UTC): {cycle.round_deadline_at}")

    return "\n".join(lines)


@dataclass
class GDRoundProcessResult:
    ok: bool
    cycle_id: int
    skipped_reason: str | None = None
    narrative_sent: bool = False
    telegram_message_id: int | None = None
    round_number: int | None = None
    buffer_user_count: int = 0


async def send_gd_v1_group_start_narrative(
    bot: Any,
    session: AsyncSession,
    cycle: GDCycle,
) -> None:
    """Сообщение с правилами раунда + ИИ-вступление о составе и входе в подземелье."""
    try:
        await bot.send_message(chat_id=cycle.chat_id, text=GD_V1_START_CHAT_MESSAGE)
    except Exception:
        logger.exception("GD start rules message failed chat_id=%s", cycle.chat_id)
    raw_party = (cycle.battle_state_json or {}).get("party") or []
    party = await _refresh_party_display_from_main_waifu(session, raw_party)
    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
    dungeon_name = tpl.name if tpl else "Подземелье"
    biome = (tpl.description or "")[:120] if tpl else ""
    cfg = await get_game_config_map(session)
    timeout = float(cfg.get("gd_ai_timeout_seconds") or "18")
    _, intro = await generate_gd_start_narrative(
        dungeon_name=dungeon_name,
        biome_tag=biome,
        party=party,
        timeout_sec=timeout,
    )
    try:
        await bot.send_message(chat_id=cycle.chat_id, text=intro)
    except Exception:
        logger.exception("GD start AI narrative message failed chat_id=%s", cycle.chat_id)


async def process_gd_registration_deadlines(
    session: AsyncSession, gd_cycle: GDCycleService, bot: Any | None
) -> None:
    closed = await gd_cycle.process_due_registration_closures(session)
    await session.commit()
    if closed:
        logger.info(
            "GD v1 registration auto-close: %s cycle(s) processed (%s)",
            len(closed),
            ", ".join(f"#{c.id}:{c.status}" for c in closed),
        )
    for c in closed:
        if bot and c.status == "active":
            logger.info(
                "GD v1 auto-start cycle_id=%s chat_id=%s — отправляю стартовый нарратив",
                c.id,
                c.chat_id,
            )
            fresh = await session.get(GDCycle, c.id)
            if fresh:
                await send_gd_v1_group_start_narrative(bot, session, fresh)
        elif not bot and c.status == "active":
            logger.warning(
                "GD v1 auto-start cycle_id=%s chat_id=%s: bot=None — поход активен, "
                "но стартовое сообщение не отправлено (проверьте get_bot()/webhook).",
                c.id,
                c.chat_id,
            )
        elif bot and c.status == "cancelled":
            try:
                await bot.send_message(
                    chat_id=c.chat_id,
                    text="❌ Недостаточно участников для похода. Регистрация отменена.",
                )
            except Exception:
                logger.exception("GD cancel msg failed chat_id=%s", c.chat_id)


async def _persist_round(
    session: AsyncSession,
    cycle: GDCycle,
    result: dict[str, Any],
    narrative_db: str | None,
    telegram_msg_id: int | None,
) -> None:
    session.add(
        GDRound(
            cycle_id=cycle.id,
            round_number=int(result["round_number"]),
            monsters_json=result["monsters_json"],
            actions_json=result["actions_json"],
            outcomes_json=result["outcomes_json"],
            context_json=result["context_json"],
            round_outcome=str(result["round_outcome"]),
            ai_narrative=narrative_db,
            telegram_msg_id=telegram_msg_id,
        )
    )
    cycle.current_round_number = int(result["round_number"])
    await session.flush()


async def _gd_v1_execute_round_resolution_after_simulation(
    session: AsyncSession,
    cycle_id: int,
    cycle: GDCycle,
    result: dict[str, Any],
    buffer_user_count: int,
    bot: Any | None,
    now: datetime,
    dur_td: timedelta,
) -> GDRoundProcessResult:
    """
    Общий путь после симуляции (process_gd_round) или админ-форса победы:
    коммит состояния боя, ИИ-нарратив раунда, системное HP, запись gd_rounds, награды при victory.
    """
    chat_id = int(cycle.chat_id)
    rnd = int(result.get("round_number") or 0)
    cfg_map = await get_game_config_map(session)
    st_check = cycle.battle_state_json or {}

    cancel_reason: str | None = None
    if result["round_outcome"] == "idle":
        idle_lim = cfg_int(cfg_map, "gd_idle_silent_rounds_to_end", 2)
        if int(st_check.get("idle_silent_streak") or 0) >= idle_lim:
            cancel_reason = "idle"
    elif result["round_outcome"] == "party_wiped":
        wipe_lim = cfg_int(cfg_map, "gd_max_wipes_to_end", 3)
        if int(st_check.get("wipe_count") or 0) >= wipe_lim:
            cancel_reason = "defeat"

    # Auto-cancel: idle streak or wipe ceiling (no victory rewards)
    if cancel_reason:
        from waifu_bot.core import redis as redis_core
        from waifu_bot.services.gd_cycle_service import GDCycleService

        cycle.round_deadline_at = None
        await session.flush()
        gd_svc = GDCycleService(redis_core.get_redis())
        await gd_svc.cancel_active_cycle(session, cycle, reason=cancel_reason)
        result = dict(result)
        result["round_outcome"] = f"cancelled_{cancel_reason}"
        await _persist_round(session, cycle, result, None, None)
        await session.commit()
        reason_ru = {
            "idle": "тишина в чате",
            "defeat": "слишком много нокаутов отряда",
        }.get(cancel_reason, cancel_reason)
        end_text = (
            f"🏁 Поход свёрнут ({reason_ru}). Награды за победу не выдаются. "
            f"Новый сбор — через WebApp или /gd_join."
        )
        if bot and chat_id is not None:
            try:
                await bot.send_message(chat_id=chat_id, text=end_text)
            except Exception:
                logger.exception("GD cancel notify failed cycle_id=%s", cycle_id)
        return GDRoundProcessResult(
            ok=True,
            cycle_id=cycle_id,
            narrative_sent=False,
            telegram_message_id=None,
            round_number=rnd,
            buffer_user_count=buffer_user_count,
        )

    # Silent round without auto-end: template message, no AI
    if result["round_outcome"] == "idle":
        cycle.round_deadline_at = now + dur_td
        await session.commit()
        streak = int(st_check.get("idle_silent_streak") or 0)
        idle_lim = cfg_int(cfg_map, "gd_idle_silent_rounds_to_end", 2)
        chat_text = (
            f"😴 Отряд молчит — раунд {result.get('round_number', '?')} пропущен "
            f"(тишина {streak}/{idle_lim}). Напишите в чат, чтобы продолжить бой."
        )
        msg_id = None
        narrative_sent = False
        if bot and chat_id is not None:
            try:
                sent = await bot.send_message(chat_id=chat_id, text=chat_text)
                msg_id = sent.message_id
                narrative_sent = True
            except Exception:
                logger.exception("GD idle send failed cycle_id=%s", cycle_id)
        cycle2 = await session.get(GDCycle, cycle_id)
        if cycle2:
            await _persist_round(session, cycle2, result, None, msg_id)
            await session.commit()
        return GDRoundProcessResult(
            ok=True,
            cycle_id=cycle_id,
            narrative_sent=narrative_sent,
            telegram_message_id=msg_id,
            round_number=rnd,
            buffer_user_count=buffer_user_count,
        )

    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)

    if result["round_outcome"] != "victory":
        cycle.round_deadline_at = now + dur_td
    else:
        cycle.round_deadline_at = None

    await session.commit()

    ctx = dict(result["context_json"])
    ctx["dungeon_name"] = tpl.name if tpl else "Подземелье"
    biome_full = (tpl.description or "") if tpl else ""
    ctx["biome_tag"] = biome_full[:40]
    ctx["total_est"] = max(8, (cycle.total_rounds or 12))
    ctx["outcomes_summary"] = {
        "round_outcome": result["round_outcome"],
        "hits_n": len((result.get("outcomes_json") or {}).get("hits") or []),
    }
    battle_party = list((cycle.battle_state_json or {}).get("party") or ctx.get("party") or [])
    ctx["party"] = await _refresh_party_display_from_main_waifu(session, battle_party)
    st0 = cycle.battle_state_json or {}
    if result["round_outcome"] == "victory":
        mvp = _compute_round_mvp(st0)
        if mvp:
            ctx["mvp_name"] = mvp[1]
    # Absurd seed + anti-repeat fingerprints
    recent_rounds = (
        await session.execute(
            select(GDRound)
            .where(GDRound.cycle_id == cycle_id)
            .order_by(GDRound.round_number.desc())
            .limit(8)
        )
    ).scalars().all()
    # Also pull last few narratives from prior finished cycles in this chat
    prior = (
        await session.execute(
            select(GDRound)
            .join(GDCycle, GDCycle.id == GDRound.cycle_id)
            .where(
                GDCycle.chat_id == chat_id,
                GDRound.ai_narrative.isnot(None),
                GDRound.cycle_id != cycle_id,
            )
            .order_by(GDRound.id.desc())
            .limit(6)
        )
    ).scalars().all()
    fps = recent_fingerprints_from_rounds(list(recent_rounds) + list(prior), limit=10)
    ctx["recent_narrative_fingerprints"] = fps
    prior_narrs = [
        str(r.ai_narrative)
        for r in list(recent_rounds)[:2]
        if getattr(r, "ai_narrative", None)
    ]
    fallen_names = [
        str(p.get("name") or p.get("user_id"))
        for p in (st0.get("party") or [])
        if p.get("fallen")
    ]
    ctx["folding_chronicle"] = build_gd_folding_chronicle(
        prior_narrs,
        wave=str(st0.get("wave") or ""),
        round_num=int(result.get("round_number") or 0),
        wipe_count=int(st0.get("wipe_count") or 0),
        last_outcome=str(result.get("round_outcome") or ""),
        fallen_names=fallen_names,
    )
    seed = pick_absurd_event_seed(
        biome_tag=biome_full,
        used_seed_ids=list(st0.get("used_narrative_seed_ids") or []),
    )
    if seed:
        ctx["absurd_event_seed"] = seed
        merge_used_seed_ids(st0, seed.get("id"))
        cycle.battle_state_json = st0
        await session.flush()
    hint = _power_hint_for_narrative(st0)
    if hint:
        ctx["power_hint"] = hint

    timeout = float(
        (await get_game_config_map(session)).get("gd_ai_timeout_seconds") or "15"
    )
    narrative_db: str | None = None
    chat_text = ""
    msg_id = None
    narrative_sent = False
    top_name = _round_top_contributor_name(cycle.battle_state_json, ctx)
    try:
        ai_raw, narr_body = await generate_gd_round_narrative(ctx, timeout_sec=timeout)
        narrative_db = ai_raw
        chat_text = format_gd_group_compact_message(
            narr_body,
            cycle.battle_state_json,
            round_number=result.get("round_number", "?"),
            round_outcome=str(result.get("round_outcome") or ""),
            top_contributor_name=top_name,
        )
        if bot and chat_id is not None:
            sent = await bot.send_message(chat_id=chat_id, text=chat_text)
            msg_id = sent.message_id
            narrative_sent = True
    except Exception:
        logger.exception("GD round narrative or send failed cycle_id=%s", cycle_id)
        chat_text = format_gd_group_compact_message(
            f"[Раунд {result.get('round_number', '?')}] Продолжаем поход.",
            cycle.battle_state_json,
            round_number=result.get("round_number", "?"),
            round_outcome=str(result.get("round_outcome") or ""),
            top_contributor_name=top_name,
        )
        if bot and chat_id is not None:
            try:
                sent = await bot.send_message(chat_id=chat_id, text=chat_text)
                msg_id = sent.message_id
                narrative_sent = True
            except Exception:
                logger.exception("GD round fallback send failed cycle_id=%s", cycle_id)

    # Full battle log + HP → DM to registered participants only (not group spam)
    if bot:
        try:
            battle_log_text = format_gd_round_battle_log_message(result, ctx)
            hp_text = format_gd_battle_hp_system_message(cycle.battle_state_json)
            detail = battle_log_text + "\n\n" + hp_text
            regs = (
                await session.execute(
                    select(GDRegistration).where(GDRegistration.cycle_id == cycle_id)
                )
            ).scalars().all()
            from waifu_bot.services.player_notification_prefs import should_send_dm

            for reg in regs:
                uid = int(reg.user_id)
                try:
                    if not await should_send_dm(session, uid, "group_dungeon"):
                        continue
                    for chunk in _chunk_text(detail, 3900):
                        await bot.send_message(chat_id=uid, text=chunk)
                except Exception:
                    logger.debug(
                        "GD round detail DM failed cycle_id=%s uid=%s",
                        cycle_id,
                        uid,
                        exc_info=True,
                    )
        except Exception:
            logger.exception("GD round detail DM batch failed cycle_id=%s", cycle_id)

    if narrative_db:
        # Store fingerprint on state for future cycles via GDRound.ai_narrative
        _ = narrative_fingerprint(narrative_db)

    cycle2 = await session.get(GDCycle, cycle_id)
    if not cycle2:
        logger.error("GD v1 cycle missing after AI cycle_id=%s", cycle_id)
        return GDRoundProcessResult(
            ok=False,
            cycle_id=cycle_id,
            skipped_reason="cycle_lost_after_round",
            round_number=rnd,
            buffer_user_count=buffer_user_count,
        )

    await _persist_round(session, cycle2, result, narrative_db, msg_id)
    if result["round_outcome"] == "victory":
        cycle2.status = "finished"
        cycle2.finished_at = datetime.now(timezone.utc)
        try:
            from waifu_bot.core import redis as redis_core

            await gd_active_cache_mod.invalidate_active_cycle_cache(
                redis_core.get_redis(), cycle2.chat_id
            )
        except Exception:
            logger.debug("gd active cache invalidate on victory failed", exc_info=True)
        await session.commit()
        logger.info(
            "GD v1 round tick done cycle_id=%s round=%s outcome=victory narrative_sent=%s buffer_users=%s",
            cycle_id,
            result.get("round_number"),
            narrative_sent,
            buffer_user_count,
        )
        await finalize_gd_v1_rewards_and_notify(session, cycle2, bot)
    else:
        await session.commit()
        logger.info(
            "GD v1 round tick done cycle_id=%s round=%s outcome=%s narrative_sent=%s buffer_users=%s",
            cycle_id,
            result.get("round_number"),
            result.get("round_outcome"),
            narrative_sent,
            buffer_user_count,
        )

    return GDRoundProcessResult(
        ok=True,
        cycle_id=cycle_id,
        narrative_sent=narrative_sent,
        telegram_message_id=msg_id,
        round_number=rnd,
        buffer_user_count=buffer_user_count,
    )


async def heal_gd_active_cycles_missing_deadline(session: AsyncSession) -> None:
    """Активные циклы без дедлайна (миграция / сбой): выставить дедлайн от now."""
    cfg = await get_game_config_map(session)
    dur_m = int(float(cfg.get("gd_round_duration_minutes", str(GD_ROUND_DURATION_MINUTES_DEFAULT))))
    now = datetime.now(timezone.utc)
    r = await session.execute(
        select(GDCycle).where(
            GDCycle.status == "active",
            GDCycle.round_deadline_at.is_(None),
        )
    )
    for c in r.scalars():
        c.round_deadline_at = now + timedelta(minutes=dur_m)


async def run_gd_v1_round_tick_poll(session: AsyncSession, bot: Any | None, redis_client: Any | None) -> None:
    await heal_gd_active_cycles_missing_deadline(session)
    await session.commit()

    now = datetime.now(timezone.utc)
    q = await session.execute(
        select(GDCycle.id).where(
            GDCycle.status == "active",
            GDCycle.round_deadline_at.isnot(None),
            GDCycle.round_deadline_at <= now,
        )
    )
    ids = [row[0] for row in q.all()]
    for cid in ids:
        try:
            res = await process_gd_v1_round_for_cycle(cid, bot, redis_client, force=False)
            if not res.ok and res.skipped_reason and res.skipped_reason not in (
                "claim_failed",
                "already_processing",
            ):
                logger.info(
                    "GD v1 round poll cycle_id=%s skipped_reason=%s buffer_users=%s",
                    cid,
                    res.skipped_reason,
                    res.buffer_user_count,
                )
        except Exception:
            logger.exception("GD v1 round tick failed cycle_id=%s", cid)


async def process_gd_v1_round_for_cycle(
    cycle_id: int,
    bot: Any | None,
    redis_client: Any | None,
    *,
    force: bool = False,
) -> GDRoundProcessResult:
    """
    Один цикл: claim по дедлайну (или force), симуляция раунда, commit состояния боя,
    затем ИИ и запись gd_rounds отдельной транзакцией.
    При неожиданной ошибке: rollback, попытка восстановить дедлайн, исключение пробрасывается.
    """
    if not gd_v1_try_begin_round_processing(cycle_id):
        logger.info("GD v1 round skip cycle_id=%s reason=already_processing", cycle_id)
        return GDRoundProcessResult(
            ok=False, cycle_id=cycle_id, skipped_reason="already_processing"
        )
    try:
        return await _process_gd_v1_round_for_cycle_locked(
            cycle_id, bot, redis_client, force=force
        )
    finally:
        gd_v1_end_round_processing(cycle_id)


async def process_gd_v1_admin_force_victory_cycle(
    cycle_id: int,
    bot: Any | None,
    redis_client: Any | None,
    admin_user_id: int,
) -> GDRoundProcessResult:
    """
    Админ: мгновенный финал похода (все монстры повержены).
    Тот же пайплайн, что после process_gd_round с round_outcome=victory: ИИ раунда, HP, gd_rounds, награды.
    """
    if not gd_v1_try_begin_round_processing(cycle_id):
        logger.info("GD v1 admin victory skip cycle_id=%s reason=already_processing", cycle_id)
        return GDRoundProcessResult(
            ok=False, cycle_id=cycle_id, skipped_reason="already_processing"
        )
    try:
        return await _process_gd_v1_admin_force_victory_locked(
            cycle_id, bot, redis_client, admin_user_id
        )
    finally:
        gd_v1_end_round_processing(cycle_id)


async def _process_gd_v1_admin_force_victory_locked(
    cycle_id: int,
    bot: Any | None,
    redis_client: Any | None,
    admin_user_id: int,
) -> GDRoundProcessResult:
    gd_cycle_svc = GDCycleService(redis_client)
    now = datetime.now(timezone.utc)

    async for session in get_session():
        try:
            cfg = await get_game_config_map(session)
            dur_m = int(float(cfg.get("gd_round_duration_minutes", str(GD_ROUND_DURATION_MINUTES_DEFAULT))))
            dur_td = timedelta(minutes=dur_m)

            cycle = await session.get(GDCycle, cycle_id)
            if not cycle or cycle.status != "active":
                logger.info(
                    "GD v1 admin victory skip cycle_id=%s reason=not_active",
                    cycle_id,
                )
                return GDRoundProcessResult(
                    ok=False, cycle_id=cycle_id, skipped_reason="not_active"
                )

            skip = precheck_admin_force_dungeon_victory(cycle)
            if skip:
                logger.info(
                    "GD v1 admin victory skip cycle_id=%s reason=%s",
                    cycle_id,
                    skip,
                )
                return GDRoundProcessResult(ok=False, cycle_id=cycle_id, skipped_reason=skip)

            cycle.round_deadline_at = None
            buf = await gd_cycle_svc.pop_round_buffer(cycle_id)
            buffer_user_count = len((buf or {}).get("users") or {})

            pre_monsters = copy.deepcopy((cycle.battle_state_json or {}).get("monsters") or [])
            result = apply_admin_force_dungeon_victory_result(cycle, buf, admin_user_id)
            await apply_gd_round_guild_hooks(
                session, cycle, {"monsters": pre_monsters}, result
            )

            return await _gd_v1_execute_round_resolution_after_simulation(
                session,
                cycle_id,
                cycle,
                result,
                buffer_user_count,
                bot,
                now,
                dur_td,
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "GD v1 process_gd_v1_admin_force_victory failed cycle_id=%s", cycle_id
            )
            async for s2 in get_session():
                try:
                    c = await s2.get(GDCycle, cycle_id)
                    if c and c.status == "active" and c.round_deadline_at is None:
                        c.round_deadline_at = datetime.now(timezone.utc) + timedelta(minutes=2)
                        await s2.commit()
                except Exception:
                    logger.exception(
                        "GD v1 admin victory restore deadline failed cycle_id=%s", cycle_id
                    )
                break
            raise

    logger.error("GD v1 admin_force_victory: no session cycle_id=%s", cycle_id)
    return GDRoundProcessResult(ok=False, cycle_id=cycle_id, skipped_reason="no_session")


async def _process_gd_v1_round_for_cycle_locked(
    cycle_id: int,
    bot: Any | None,
    redis_client: Any | None,
    *,
    force: bool = False,
) -> GDRoundProcessResult:
    gd_cycle_svc = GDCycleService(redis_client)
    now = datetime.now(timezone.utc)

    async for session in get_session():
        try:
            cfg = await get_game_config_map(session)
            dur_m = int(float(cfg.get("gd_round_duration_minutes", str(GD_ROUND_DURATION_MINUTES_DEFAULT))))
            dur_td = timedelta(minutes=dur_m)

            if not force:
                res = await session.execute(
                    update(GDCycle)
                    .where(
                        GDCycle.id == cycle_id,
                        GDCycle.status == "active",
                        GDCycle.round_deadline_at.isnot(None),
                        GDCycle.round_deadline_at <= now,
                    )
                    .values(round_deadline_at=None)
                )
                if res.rowcount != 1:
                    logger.info(
                        "GD v1 round skip cycle_id=%s reason=claim_failed",
                        cycle_id,
                    )
                    return GDRoundProcessResult(
                        ok=False, cycle_id=cycle_id, skipped_reason="claim_failed"
                    )
            else:
                c0 = await session.get(GDCycle, cycle_id)
                if not c0 or c0.status != "active":
                    logger.info("GD v1 round skip cycle_id=%s reason=not_active", cycle_id)
                    return GDRoundProcessResult(
                        ok=False, cycle_id=cycle_id, skipped_reason="not_active"
                    )
                c0.round_deadline_at = None

            buf = await gd_cycle_svc.pop_round_buffer(cycle_id)
            buffer_user_count = len((buf or {}).get("users") or {})

            cycle = await session.get(GDCycle, cycle_id)
            if not cycle:
                await session.commit()
                logger.info("GD v1 round skip cycle_id=%s reason=no_cycle", cycle_id)
                return GDRoundProcessResult(
                    ok=False,
                    cycle_id=cycle_id,
                    skipped_reason="no_cycle",
                    buffer_user_count=buffer_user_count,
                )

            pre_monsters = copy.deepcopy((cycle.battle_state_json or {}).get("monsters") or [])
            result = await process_gd_round(session, cycle, buf)
            if result.get("error") != "no_monsters":
                await apply_gd_round_guild_hooks(
                    session, cycle, {"monsters": pre_monsters}, result
                )
            if result.get("error") == "no_monsters":
                cycle.round_deadline_at = now + timedelta(minutes=2)
                await session.commit()
                logger.info(
                    "GD v1 no_monsters cycle_id=%s buffer_users=%s (нарратив не отправлялся)",
                    cycle_id,
                    buffer_user_count,
                )
                return GDRoundProcessResult(
                    ok=False,
                    cycle_id=cycle_id,
                    skipped_reason="no_monsters",
                    buffer_user_count=buffer_user_count,
                )

            return await _gd_v1_execute_round_resolution_after_simulation(
                session,
                cycle_id,
                cycle,
                result,
                buffer_user_count,
                bot,
                now,
                dur_td,
            )
        except Exception:
            await session.rollback()
            logger.exception("GD v1 process_gd_v1_round_for_cycle failed cycle_id=%s", cycle_id)
            async for s2 in get_session():
                try:
                    c = await s2.get(GDCycle, cycle_id)
                    if c and c.status == "active" and c.round_deadline_at is None:
                        c.round_deadline_at = datetime.now(timezone.utc) + timedelta(minutes=2)
                        await s2.commit()
                except Exception:
                    logger.exception("GD v1 restore deadline failed cycle_id=%s", cycle_id)
                break
            raise

    logger.error("GD v1 process_gd_v1_round_for_cycle: no session cycle_id=%s", cycle_id)
    return GDRoundProcessResult(ok=False, cycle_id=cycle_id, skipped_reason="no_session")


async def _send_gd_reward_dm(bot: Any, uid: int, text_dm: str, rew: GDRewardRow) -> None:
    for attempt in range(3):
        try:
            await bot.send_message(chat_id=uid, text=text_dm)
            rew.dm_sent = True
            return
        except Exception:
            logger.warning("GD reward DM attempt %s failed uid=%s", attempt, uid)


async def finalize_gd_v1_rewards_and_notify(session: AsyncSession, cycle: GDCycle, bot: Any | None) -> None:
    fresh = await session.get(GDCycle, cycle.id)
    if not fresh:
        return
    cycle = fresh
    cfg = await get_game_config_map(session)
    base_exp = cfg_float(cfg, "gd_base_exp_reward", 900)
    base_gold = cfg_float(cfg, "gd_base_gold_reward", 1800)
    boss_e = cfg_float(cfg, "gd_boss_exp_bonus", 1.5)
    boss_g = cfg_float(cfg, "gd_boss_gold_bonus", 1.5)
    chest_gold = int(cfg_float(cfg, "gd_completion_chest_gold", 250))
    chest_exp = int(cfg_float(cfg, "gd_completion_chest_exp", 120))
    total_r = max(1, int(cycle.current_round_number or 1))

    state = cycle.battle_state_json or {}
    contrib = state.get("contribution") or {}
    loot_awards: list[dict] = list(state.get("loot_awards") or [])
    gold_extra_pct = float((state.get("loot_modifiers") or {}).get("gold_pct") or 0)
    wipe_count = int(state.get("wipe_count") or 0)
    wipe_m = wipe_reward_multiplier(wipe_count, cfg)
    clean_m = clean_run_bonus_multiplier(wipe_count, cfg)
    regs = (
        await session.execute(select(GDRegistration).where(GDRegistration.cycle_id == cycle.id))
    ).scalars().all()
    uids = [int(r.user_id) for r in regs]
    joined_at_by_uid: dict[int, int] = {
        int(r.user_id): max(1, int(getattr(r, "joined_at_round", None) or 1)) for r in regs
    }

    activity = state.get("activity_totals") or {}
    # Dual score: presence + power → reward shares (values already normalized shares)
    share_map = blend_dual_reward_scores(
        uids, activity, contrib, cfg, joined_at_round_by_uid=joined_at_by_uid
    )
    # Display scores for ranking / narrative
    scores: dict[int, float] = {
        uid: 1000.0 * float(share_map.get(uid, 0.0)) for uid in uids
    }

    # MVP power vs presence for finale
    party = list(state.get("party") or [])
    name_by = {
        int(p["user_id"]): str(p.get("name") or f"Игрок {p['user_id']}")
        for p in party
        if p.get("user_id") is not None
    }
    power_scores = {uid: power_score_from_contrib(contrib.get(str(uid))) for uid in uids}
    presence_scores = {
        uid: presence_score_for_uid(
            uid,
            activity,
            contrib,
            apply_floor=(joined_at_by_uid.get(uid, 1) <= 1
                         or int((contrib.get(str(uid)) or {}).get("rounds") or 0) >= 1),
        )
        for uid in uids
    }
    mvp_power_name = name_by.get(max(power_scores, key=lambda u: power_scores[u])) if power_scores else None
    mvp_presence_name = (
        name_by.get(max(presence_scores, key=lambda u: presence_scores[u])) if presence_scores else None
    )

    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
    dungeon_name = tpl.name if tpl else "Подземелье"

    # Fingerprints from this cycle's rounds
    rnds = (
        await session.execute(
            select(GDRound)
            .where(GDRound.cycle_id == cycle.id)
            .order_by(GDRound.round_number.desc())
            .limit(8)
        )
    ).scalars().all()
    finale_ctx = {
        "dungeon_name": dungeon_name,
        "contributions": scores,
        "party": party,
        "mvp_power_name": mvp_power_name,
        "mvp_presence_name": mvp_presence_name,
        "recent_narrative_fingerprints": recent_fingerprints_from_rounds(list(rnds)),
        "absurd_event_seed": pick_absurd_event_seed(
            biome_tag=(tpl.description or "") if tpl else "",
            used_seed_ids=list(state.get("used_narrative_seed_ids") or []),
        ),
    }
    timeout = float(cfg.get("gd_ai_timeout_seconds") or "20")
    _, finale_chat = await generate_gd_finale_narrative(finale_ctx, timeout_sec=timeout)
    if bot:
        try:
            await bot.send_message(chat_id=cycle.chat_id, text=finale_chat)
        except Exception:
            logger.exception("GD finale chat failed cycle=%s", cycle.id)

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    rank_map = {uid: i + 1 for i, (uid, _) in enumerate(ranked)}

    dm_tasks: list[Any] = []
    for uid in uids:
        share = float(share_map.get(uid, 0.0))
        c = contrib.get(str(uid), {})
        exp_mult = 1.0 + 0.15 * float(c.get("rounds") or 0) / float(total_r)
        assist_bonus = 1.0 + 0.03 * min(5, int(c.get("assists") or 0))
        jr = joined_at_by_uid.get(uid, 1)
        stage_m = late_join_reward_stage_mult(jr, total_r, cfg)
        waifu_pre = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == uid))
        ).scalar_one_or_none()
        lvl_m = reward_level_multiplier(int(waifu_pre.level or 1) if waifu_pre else 1, cfg)
        pool_m = wipe_m * clean_m * stage_m
        exp = int(
            (base_exp * boss_e * share * exp_mult * lvl_m + chest_exp * stage_m)
            * wipe_m
            * clean_m
            * assist_bonus
        )
        gold = int(
            (
                base_gold * boss_g * share * (1.0 + gold_extra_pct / 100.0) * lvl_m
                + chest_gold * stage_m
            )
            * wipe_m
            * clean_m
            * assist_bonus
        )
        my_items = [x for x in loot_awards if int(x.get("user_id") or 0) == uid]
        rew = GDRewardRow(
            cycle_id=cycle.id,
            user_id=uid,
            exp_earned=exp,
            gold_earned=gold,
            items_json=my_items if my_items else None,
            contribution_pct=100.0 * share,
            dm_sent=False,
        )
        session.add(rew)
        await session.flush()
        player = await session.get(Player, uid)
        if player:
            player.gold = int(player.gold or 0) + gold
        waifu = waifu_pre
        if waifu and exp > 0:
            waifu.experience = (waifu.experience or 0) + exp
            await apply_main_waifu_levelups(session, waifu)
        exp_to_next = 0
        next_level = 1
        if waifu:
            cur_lvl = int(waifu.level or 1)
            if cur_lvl >= int(MAX_LEVEL):
                exp_to_next = 0
                next_level = int(MAX_LEVEL)
            else:
                next_level = cur_lvl + 1
                thr = int(calculate_total_experience_for_level(cur_lvl + 1))
                exp_to_next = max(0, thr - int(waifu.experience or 0))
        skill_n = max(0, int(c.get("skill") or 0) // 50)
        assists_n = int(c.get("assists") or 0)
        item_lines = ""
        if my_items:
            item_lines = "\n" + "\n".join(
                f"Предмет: {it.get('name', 'Предмет')} (ур. {it.get('level', '?')})" for it in my_items
            )
        clean_bit = "Чистый проход (+бонус)!" if wipe_count == 0 else f"Нокаутов: {wipe_count} (штраф к награде)"
        stage_bit = (
            f"Вступление с раунда {jr} · награда ×{stage_m:.2f}\n"
            if jr > 1
            else ""
        )
        text_dm = (
            f"⚔️ Поход в «{dungeon_name}» завершён!\n"
            f"Твой вклад: {rank_map.get(uid, '?')} место из {len(uids)}\n"
            f"Сила (бой): {int(power_scores.get(uid, 0))} · Присутствие: {int(presence_scores.get(uid, 0))}\n"
            f"Ассисты: {assists_n} · Навыков (усл.): {skill_n}\n"
            f"{stage_bit}{clean_bit}\n\n"
            f"Награды (completion chest + доля):\n"
            f"+{exp} EXP ({exp_to_next} до уровня {next_level})\n"
            f"+{gold} золота\n"
            f"{item_lines}"
        )
        if bot:
            from waifu_bot.services.player_notification_prefs import should_send_dm

            if await should_send_dm(session, int(uid), "group_dungeon"):
                dm_tasks.append(_send_gd_reward_dm(bot, uid, text_dm, rew))
    if dm_tasks:
        await asyncio.gather(*dm_tasks, return_exceptions=True)
    await session.commit()

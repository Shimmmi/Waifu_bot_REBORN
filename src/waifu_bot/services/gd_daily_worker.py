"""Daily GD worker: 04:30 auto-start and 04:00 finalize across bot group chats."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    BotGroupChat,
    GDCycle,
    GDDungeonTemplate,
    GDRegistration,
    GDRewardRow,
    MainWaifu,
    Player,
)
from waifu_bot.game.msk_time import gd_should_finalize_now, gd_should_start_now, msk_now
from waifu_bot.services.combat import apply_main_waifu_levelups
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.gd_cycle_service import GDCycleService, REDIS_GD_DAILY_LOCK
from waifu_bot.services.gd_daily_stats import (
    build_player_summary_rows,
    format_mention,
    format_type_breakdown_ru,
    pick_mvp_and_least,
)
from waifu_bot.services.gd_narrative_ai import (
    generate_gd_daily_finale_narrative,
    generate_gd_daily_start_narrative,
)
from waifu_bot.services.gd_pie_chart import generate_gd_daily_pie_png, pie_caption_from_rows
from waifu_bot.services.bot_group_chats import ACTIVE_STATUSES
from waifu_bot.services.gd_scaling import reward_level_multiplier

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


async def _try_lock(redis: Any, key: str, ttl: int = 120) -> bool:
    if not redis:
        return True
    try:
        ok = await redis.set(key, "1", nx=True, ex=ttl)
        return bool(ok)
    except Exception:
        logger.debug("GD daily lock failed key=%s", key, exc_info=True)
        return True


async def _unlock(redis: Any, key: str) -> None:
    if not redis:
        return
    try:
        await redis.delete(key)
    except Exception:
        pass


def format_daily_start_roster_html(party: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for p in party:
        uid = int(p.get("user_id") or 0)
        mention = format_mention(p.get("username"), uid)
        name = p.get("name") or "—"
        lvl = int(p.get("level") or 1)
        perf = int(p.get("perfection_level") or 0)
        gs = int(p.get("gear_score") or 0)
        lines.append(
            f"• {mention} — <b>{name}</b>: ур. {lvl}, совершенствование {perf}, предметы {gs}"
        )
    return "\n".join(lines) if lines else "• (пусто)"


def format_daily_finale_stats_html(
    rows: list[dict[str, Any]],
    *,
    chat_msg_total: int,
    dungeon_name: str,
    mvp: dict[str, Any] | None,
    least: dict[str, Any] | None,
) -> str:
    lines = [
        f"📊 <b>Итоги дневного похода</b> «{dungeon_name}»",
        f"Всего сообщений в чате за день: <b>{int(chat_msg_total)}</b>",
        "",
    ]
    ranked = sorted(rows, key=lambda r: float(r.get("score") or 0), reverse=True)
    for i, r in enumerate(ranked, 1):
        mention = format_mention(r.get("username"), int(r["user_id"]))
        br = format_type_breakdown_ru(r.get("by_type") or {})
        lines.append(
            f"{i}. {mention} — сообщ. <b>{r['msg_total']}</b> "
            f"({r['chat_share_pct']:.1f}% чата), урон <b>{r['damage_total']}</b>\n"
            f"   └ {br}"
        )
    lines.append("")
    if mvp:
        lines.append(
            f"🏆 MVP: {format_mention(mvp.get('username'), int(mvp['user_id']))} "
            f"({mvp.get('name')})"
        )
    if least and (not mvp or least.get("user_id") != mvp.get("user_id")):
        lines.append(
            f"🪵 Малоактивный: {format_mention(least.get('username'), int(least['user_id']))} "
            f"({least.get('name')})"
        )
    silent = [r for r in rows if int(r.get("msg_total") or 0) == 0]
    if silent:
        names = ", ".join(format_mention(s.get("username"), int(s["user_id"])) for s in silent[:8])
        lines.append(f"😴 Без сообщений: {names}")
    return "\n".join(lines)


async def send_daily_start_message(
    bot: Any,
    session: AsyncSession,
    cycle: GDCycle,
    party: list[dict[str, Any]],
    dungeon_name: str,
) -> None:
    cfg = await get_game_config_map(session)
    timeout = float(cfg.get("gd_ai_timeout_seconds") or "18")
    use_ai = cfg_int(cfg, "gd_daily_ai_start", 1) == 1
    roster = format_daily_start_roster_html(party)
    humor_top = ""
    humor_bot = ""
    if use_ai:
        _, humor = await generate_gd_daily_start_narrative(
            dungeon_name=dungeon_name,
            party=party,
            timeout_sec=timeout,
        )
        # Expect two short paragraphs separated by blank line; otherwise use as top.
        parts = [p.strip() for p in (humor or "").split("\n\n") if p.strip()]
        if len(parts) >= 2:
            humor_top, humor_bot = parts[0], parts[-1]
        elif parts:
            humor_top = parts[0]
            humor_bot = "Удачи в дневном походе — экипировка уже зафиксирована до завтра."
        else:
            humor_top = f"Отряд входит в «{dungeon_name}». Слепок вайфу снят — меняйте шмот на здоровье, учтём завтра."
            humor_bot = "Пишите в чат: каждое сообщение кормит статистику дня."
    else:
        humor_top = f"⚔️ Дневной поход «{dungeon_name}» начался."
        humor_bot = "Слепок основной вайфу зафиксирован до следующего утра."

    text = (
        f"{humor_top}\n\n"
        f"<b>Участники дневного похода</b>:\n{roster}\n\n"
        f"{humor_bot}"
    )
    try:
        await bot.send_message(chat_id=cycle.chat_id, text=text, parse_mode="HTML")
    except Exception:
        logger.exception("GD daily start message failed chat_id=%s", cycle.chat_id)


async def finalize_daily_rewards_and_notify(
    session: AsyncSession,
    cycle: GDCycle,
    bot: Any | None,
    *,
    rows: list[dict[str, Any]],
    chat_msg_total: int,
    mvp: dict[str, Any] | None,
    least: dict[str, Any] | None,
) -> None:
    cfg = await get_game_config_map(session)
    base_exp = cfg_float(cfg, "gd_base_exp_reward", 900)
    base_gold = cfg_float(cfg, "gd_base_gold_reward", 1800)
    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
    dungeon_name = tpl.name if tpl else "Подземелье"

    total_score = sum(float(r.get("score") or 0) for r in rows) or 1.0
    ranked = sorted(rows, key=lambda r: float(r.get("score") or 0), reverse=True)

    stats_html = format_daily_finale_stats_html(
        rows,
        chat_msg_total=chat_msg_total,
        dungeon_name=dungeon_name,
        mvp=mvp,
        least=least,
    )
    use_ai = cfg_int(cfg, "gd_daily_ai_finale", 1) == 1
    ai_block = ""
    if use_ai:
        timeout = float(cfg.get("gd_ai_timeout_seconds") or "20")
        _, ai_block = await generate_gd_daily_finale_narrative(
            {
                "dungeon_name": dungeon_name,
                "mvp": mvp,
                "least": least,
                "rows": rows,
                "chat_msg_total": chat_msg_total,
            },
            timeout_sec=timeout,
        )

    finale_text = stats_html
    if ai_block:
        finale_text = f"{ai_block}\n\n{stats_html}"

    if bot:
        try:
            await bot.send_message(chat_id=cycle.chat_id, text=finale_text, parse_mode="HTML")
        except Exception:
            logger.exception("GD daily finale text failed cycle=%s", cycle.id)

        if cfg_int(cfg, "gd_daily_pie_enabled", 1) == 1 and rows:
            try:
                from aiogram.types import BufferedInputFile

                png, src = await generate_gd_daily_pie_png(
                    rows,
                    chat_msg_total=chat_msg_total,
                    title=f"{dungeon_name} — активность",
                )
                caption = pie_caption_from_rows(rows, chat_msg_total=chat_msg_total)
                await bot.send_photo(
                    chat_id=cycle.chat_id,
                    photo=BufferedInputFile(png, filename="gd_daily_pie.png"),
                    caption=caption[:1024],
                )
                logger.info("GD daily pie sent cycle=%s source=%s", cycle.id, src)
            except Exception:
                logger.exception("GD daily pie send failed cycle=%s", cycle.id)

    for i, r in enumerate(ranked):
        uid = int(r["user_id"])
        share = float(r.get("score") or 0) / total_score
        waifu_pre = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == uid))
        ).scalar_one_or_none()
        lvl_m = reward_level_multiplier(int(waifu_pre.level or 1) if waifu_pre else 1, cfg)
        activity_m = 0.35 + 0.65 * min(1.0, float(r.get("msg_total") or 0) / 20.0)
        exp = int(base_exp * share * lvl_m * activity_m)
        gold = int(base_gold * share * lvl_m * activity_m)
        rew = GDRewardRow(
            cycle_id=cycle.id,
            user_id=uid,
            exp_earned=exp,
            gold_earned=gold,
            items_json=None,
            contribution_pct=100.0 * share,
            dm_sent=False,
        )
        session.add(rew)
        await session.flush()
        player = await session.get(Player, uid)
        if player:
            player.gold = int(player.gold or 0) + gold
        if waifu_pre and exp > 0:
            waifu_pre.experience = (waifu_pre.experience or 0) + exp
            await apply_main_waifu_levelups(session, waifu_pre)

        if not bot:
            continue
        try:
            from waifu_bot.services.player_notification_prefs import should_send_dm

            if not await should_send_dm(session, uid, "group_dungeon"):
                continue
        except Exception:
            pass
        rank = i + 1
        dm = (
            f"⚔️ Дневной поход «{dungeon_name}» завершён.\n"
            f"Место: {rank}/{len(ranked)}\n"
            f"Сообщений: {r['msg_total']} ({r['chat_share_pct']:.1f}% чата)\n"
            f"Урон: {r['damage_total']}\n"
            f"Награда: {exp} опыта, {gold} золота."
        )
        for attempt in range(3):
            try:
                await bot.send_message(chat_id=uid, text=dm)
                rew.dm_sent = True
                break
            except Exception:
                logger.warning("GD daily reward DM attempt %s failed uid=%s", attempt, uid)


async def run_gd_daily_finalize_tick(
    session: AsyncSession,
    bot: Any | None,
    redis_client: Any,
    *,
    force_cycle_id: int | None = None,
) -> int:
    """Finalize due daily cycles. Returns number finalized."""
    gd = GDCycleService(redis_client)
    cfg = await get_game_config_map(session)
    end_h = cfg_int(cfg, "gd_daily_end_hour_msk", 4)
    end_m = cfg_int(cfg, "gd_daily_end_minute_msk", 0)
    now = datetime.now(timezone.utc)

    if force_cycle_id is not None:
        cycles = []
        c = await session.get(GDCycle, int(force_cycle_id))
        if c:
            cycles = [c]
    else:
        if not gd_should_finalize_now(end_hour=end_h, end_minute=end_m, now=now):
            # Also pick cycles past ends_at even outside morning window (catch-up)
            cycles = await gd.list_active_daily_cycles_due(session, now=now)
        else:
            cycles = await gd.list_active_daily_cycles_due(session, now=now)

    done = 0
    for cycle in cycles:
        lock_key = f"{REDIS_GD_DAILY_LOCK}fin:{cycle.id}"
        if not await _try_lock(redis_client, lock_key, ttl=180):
            continue
        try:
            fresh = await session.get(GDCycle, cycle.id)
            if not fresh or fresh.status != "active":
                continue
            fin = await gd.finish_daily_cycle(session, fresh, reason="daily_end")
            if not fin.get("success"):
                continue
            regs = (
                await session.execute(
                    select(GDRegistration).where(GDRegistration.cycle_id == fresh.id)
                )
            ).scalars().all()
            chat_total = int(fin.get("chat_msg_total") or 0)
            rows = build_player_summary_rows(list(regs), chat_msg_total=chat_total)
            mvp, least = pick_mvp_and_least(rows)
            await finalize_daily_rewards_and_notify(
                session,
                fresh,
                bot,
                rows=rows,
                chat_msg_total=chat_total,
                mvp=mvp,
                least=least,
            )
            await session.commit()
            done += 1
            logger.info(
                "GD daily finalized cycle_id=%s chat_id=%s party=%s",
                fresh.id,
                fresh.chat_id,
                len(rows),
            )
        except Exception:
            await session.rollback()
            logger.exception("GD daily finalize failed cycle_id=%s", cycle.id)
        finally:
            await _unlock(redis_client, lock_key)
    return done


async def run_gd_daily_start_tick(
    session: AsyncSession,
    bot: Any | None,
    redis_client: Any,
    *,
    force_chat_id: int | None = None,
    force: bool = False,
) -> int:
    """Auto-start daily cycles for active bot chats. Returns number started."""
    gd = GDCycleService(redis_client)
    cfg = await get_game_config_map(session)
    start_h = cfg_int(cfg, "gd_daily_start_hour_msk", 4)
    start_m = cfg_int(cfg, "gd_daily_start_minute_msk", 30)
    now = datetime.now(timezone.utc)

    if force_chat_id is None and not force and not gd_should_start_now(
        start_hour=start_h, start_minute=start_m, now=now
    ):
        return 0

    if force_chat_id is not None:
        chat_ids = [int(force_chat_id)]
    else:
        rows = (
            await session.execute(
                select(BotGroupChat).where(BotGroupChat.status.in_(tuple(ACTIVE_STATUSES)))
            )
        ).scalars().all()
        chat_ids = [int(r.chat_id) for r in rows if int(r.chat_id) < 0]

    started = 0
    for chat_id in chat_ids:
        lock_key = f"{REDIS_GD_DAILY_LOCK}start:{chat_id}:{msk_now(now).date()}"
        if not await _try_lock(redis_client, lock_key, ttl=180):
            continue
        try:
            result = await gd.start_daily_cycle_for_chat(
                session, chat_id, force=force or force_chat_id is not None, now=now
            )
            if result.get("error") == "already" or result.get("error") == "active":
                await session.commit()
                continue
            if not result.get("success"):
                logger.info(
                    "GD daily start skip chat_id=%s err=%s",
                    chat_id,
                    result.get("error") or result,
                )
                await session.commit()
                continue
            await session.commit()
            cycle = await session.get(GDCycle, int(result["cycle_id"]))
            if bot and cycle and cycle.status == "active":
                await send_daily_start_message(
                    bot,
                    session,
                    cycle,
                    list(result.get("party") or []),
                    str(result.get("dungeon_name") or "Подземелье"),
                )
            started += 1
            logger.info(
                "GD daily started cycle_id=%s chat_id=%s party=%s status=%s",
                result.get("cycle_id"),
                chat_id,
                result.get("party_count"),
                result.get("status"),
            )
        except Exception:
            await session.rollback()
            logger.exception("GD daily start failed chat_id=%s", chat_id)
        finally:
            await _unlock(redis_client, lock_key)
    return started

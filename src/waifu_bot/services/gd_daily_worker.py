"""Daily GD worker: 04:30 auto-start and 04:00 finalize across bot group chats."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
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
from waifu_bot.game.constants import MAX_LEVEL
from waifu_bot.game.msk_time import gd_should_start_now, msk_current_game_date, msk_now
from waifu_bot.services.combat import apply_main_waifu_levelups
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map
from waifu_bot.services.gd_cycle_service import GDCycleService, REDIS_GD_DAILY_LOCK
from waifu_bot.services.gd_daily_rewards import (
    compute_daily_payout,
    contribution_display_pct,
    roll_daily_reward_items,
)
from waifu_bot.services.gd_daily_stats import (
    build_player_summary_rows,
    format_top_words_line_ru,
    format_type_breakdown_ru,
    format_waifu_html,
    pick_mvp_and_least,
    sort_rows_by_activity,
)
from waifu_bot.services.gd_daily_word_ai import (
    analyze_day_word_stats,
    merge_word_stats_into_rows,
)
from waifu_bot.services.gd_phantom_log import load_phantom_log, purge_phantom_log
from waifu_bot.services.gd_podium_art import (
    count_active_players,
    generate_gd_daily_podium_png,
    load_player_avatar_bytes,
    race_board_rows,
    send_photo_with_retries,
    should_generate_podium,
)
from waifu_bot.services.bot_group_chats import ACTIVE_STATUSES

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

TELEGRAM_HTML_SOFT_LIMIT = 3500


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


def format_level_display(level: int, perfection_level: int = 0) -> str:
    """Main level, with (paragon) only when MAX_LEVEL and perfection unlocked."""
    lvl = max(1, int(level or 1))
    perf = max(0, int(perfection_level or 0))
    if lvl >= int(MAX_LEVEL) and perf > 0:
        return f"{lvl} ({perf})"
    return str(lvl)


def format_daily_start_roster_html(party: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for p in party:
        name_html = format_waifu_html(p.get("name"), p.get("epithet_short"))
        lvl_txt = format_level_display(
            int(p.get("level") or 1),
            int(p.get("perfection_level") or 0),
        )
        gs = int(p.get("gear_score") or 0)
        lines.append(f"• {name_html}: {lvl_txt}, ур.шмота <b>{gs}</b>")
    return "\n".join(lines) if lines else "• (пусто)"


def _finale_player_block(index: int, r: dict[str, Any]) -> str:
    name_html = format_waifu_html(r.get("name"), r.get("epithet_short"))
    msg_total = int(r.get("msg_total") or 0)
    head = (
        f"{index}. {name_html} — сообщ. <b>{msg_total}</b> "
        f"({float(r.get('chat_share_pct') or 0):.1f}% чата), "
        f"символов <b>{int(r.get('text_chars') or 0)}</b>, "
        f"урон <b>{int(r.get('damage_total') or 0)}</b>"
    )
    if msg_total <= 0:
        return head
    br = format_type_breakdown_ru(r.get("by_type") or {})
    lines = [head, f"   └ медиа: {br}"]
    words = format_top_words_line_ru(r)
    if words:
        lines.append(f"   └ слова: {words}")
    return "\n".join(lines)


def _finale_footer_lines(
    rows: list[dict[str, Any]],
    *,
    mvp: dict[str, Any] | None,
    least: dict[str, Any] | None,
) -> list[str]:
    _ = rows
    lines: list[str] = [""]
    if mvp:
        lines.append(f"🏆 MVP: {format_waifu_html(mvp.get('name'), mvp.get('epithet_short'))}")
    if least and (not mvp or least.get("user_id") != mvp.get("user_id")):
        lines.append(f"🪵 Малоактивный: {format_waifu_html(least.get('name'), least.get('epithet_short'))}")
    return lines


def format_daily_finale_stats_html(
    rows: list[dict[str, Any]],
    *,
    chat_msg_total: int,
    dungeon_name: str,
    mvp: dict[str, Any] | None,
    least: dict[str, Any] | None,
) -> str:
    return "\n\n".join(
        build_daily_finale_html_chunks(
            rows,
            chat_msg_total=chat_msg_total,
            dungeon_name=dungeon_name,
            mvp=mvp,
            least=least,
        )
    )


def build_daily_finale_html_chunks(
    rows: list[dict[str, Any]],
    *,
    chat_msg_total: int,
    dungeon_name: str,
    mvp: dict[str, Any] | None,
    least: dict[str, Any] | None,
    soft_limit: int = TELEGRAM_HTML_SOFT_LIMIT,
    prefix: str = "",
) -> list[str]:
    """Build one or more Telegram HTML chunks (split on player block boundaries)."""
    header_lines = [
        f"📊 <b>Итоги дневного похода</b> «{dungeon_name}»",
        f"Всего сообщений в чате за день: <b>{int(chat_msg_total)}</b>",
        "",
    ]
    ranked = sort_rows_by_activity(rows)
    player_blocks = [_finale_player_block(i, r) for i, r in enumerate(ranked, 1)]
    footer = "\n".join(_finale_footer_lines(rows, mvp=mvp, least=least))

    chunks: list[str] = []
    current = (prefix.strip() + "\n\n" if prefix.strip() else "") + "\n".join(header_lines)

    def _flush() -> None:
        nonlocal current
        text = current.rstrip()
        if text:
            chunks.append(text)
        current = ""

    for block in player_blocks:
        candidate = (current + "\n" + block) if current else block
        if current and len(candidate) > soft_limit:
            _flush()
            current = block
        else:
            current = candidate

    if footer.strip():
        candidate = (current + "\n" + footer) if current else footer
        if current and len(candidate) > soft_limit:
            _flush()
            current = footer.lstrip("\n")
        else:
            current = candidate
    _flush()
    return chunks or ["📊 <b>Итоги дневного похода</b>"]


def _chunk_plain_text(text: str, soft_limit: int = TELEGRAM_HTML_SOFT_LIMIT) -> list[str]:
    if len(text) <= soft_limit:
        return [text]
    parts = text.split("\n\n")
    chunks: list[str] = []
    cur = ""
    for part in parts:
        candidate = f"{cur}\n\n{part}" if cur else part
        if cur and len(candidate) > soft_limit:
            chunks.append(cur)
            cur = part
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks or [text[:soft_limit]]


def format_aggregated_reward_dm(
    *,
    game_date: date,
    parts: list[dict[str, Any]],
) -> str:
    """Build plain-text aggregated reward DM for one user/game_date."""
    total_exp = sum(int(p.get("exp") or 0) for p in parts)
    total_gold = sum(int(p.get("gold") or 0) for p in parts)
    all_items: list[dict[str, Any]] = []
    for p in parts:
        for it in p.get("items") or []:
            if isinstance(it, dict):
                all_items.append(it)

    lines = [
        f"⚔️ Дневные походы за {game_date.isoformat()} завершены.",
        f"Итого: {total_exp} опыта, {total_gold} золота.",
    ]
    if all_items:
        lines.append(
            "Предметы: "
            + ", ".join(f"{it.get('name')} (ур. {it.get('level')})" for it in all_items)
        )
    lines.append("")
    for p in parts:
        item_bit = ""
        items = p.get("items") or []
        if items:
            item_bit = "\n  Предметы: " + ", ".join(
                f"{it.get('name')} (ур. {it.get('level')})" for it in items if isinstance(it, dict)
            )
        lines.append(
            f"• «{p.get('dungeon_name') or 'Подземелье'}» — место {p.get('rank')}/{p.get('party_size')}\n"
            f"  Сообщений: {p.get('msg_total')} (учтено {p.get('counted_msgs')}/500), "
            f"урон {p.get('damage_total')}\n"
            f"  Награда: {int(p.get('exp') or 0)} опыта, {int(p.get('gold') or 0)} золота."
            f"{item_bit}"
        )
    return "\n".join(lines)


DAILY_START_INTRO = "Отряд наших вайфу:"


def _finale_image_enabled(cfg: dict[str, str]) -> bool:
    if "gd_daily_finale_image_enabled" in cfg:
        return cfg_int(cfg, "gd_daily_finale_image_enabled", 1) == 1
    return cfg_int(cfg, "gd_daily_pie_enabled", 1) == 1


async def send_daily_start_message(
    bot: Any,
    session: AsyncSession,
    cycle: GDCycle,
    party: list[dict[str, Any]],
    dungeon_name: str,
) -> None:
    _ = (session, dungeon_name)
    roster = format_daily_start_roster_html(party)
    text = f"{DAILY_START_INTRO}\n{roster}"
    try:
        await bot.send_message(chat_id=cycle.chat_id, text=text, parse_mode="HTML")
    except Exception:
        logger.exception("GD daily start message failed chat_id=%s", cycle.chat_id)


async def _send_podium_for_cycle(
    session: AsyncSession,
    bot: Any,
    cycle: GDCycle,
    rows: list[dict[str, Any]],
    *,
    dungeon_name: str,
    cfg: dict[str, str],
) -> None:
    _ = dungeon_name  # title is fixed «Итоги дня»; kept for call-site compat
    if not _finale_image_enabled(cfg):
        return
    active_count = count_active_players(rows)
    if not should_generate_podium(rows):
        logger.info(
            "GD daily race board skipped cycle=%s active=%s (need >= 1)",
            cycle.id,
            active_count,
        )
        return
    board = race_board_rows(rows)
    if not board:
        return
    avatars: dict[int, bytes | None] = {}
    for r in board:
        uid = int(r["user_id"])
        waifu = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == uid))
        ).scalar_one_or_none()
        avatars[uid] = load_player_avatar_bytes(uid, waifu)

    result = await generate_gd_daily_podium_png(
        rows,
        avatars=avatars,
        title="Итоги дня",
    )
    if not result:
        return
    png, src = result
    ok = await send_photo_with_retries(
        bot,
        chat_id=int(cycle.chat_id),
        png=png,
        filename="gd_daily_race_board.webp",
        caption="",
    )
    if ok:
        logger.info("GD daily race board sent cycle=%s source=%s", cycle.id, src)
    else:
        logger.error("GD daily race board send failed cycle=%s source=%s", cycle.id, src)


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
    """Pay rewards + race-board image. DMs are flushed later via flush_daily_reward_dms.

    Group-chat text finale (HTML/AI) is intentionally not sent — board image only.
    """
    cfg = await get_game_config_map(session)
    tpl = await session.get(GDDungeonTemplate, cycle.dungeon_template_id)
    dungeon_name = tpl.name if tpl else "Подземелье"

    ranked = sort_rows_by_activity(rows)
    sum_msgs = sum(max(0, int(r.get("msg_total") or 0)) for r in ranked)

    if bot:
        try:
            await _send_podium_for_cycle(
                session, bot, cycle, rows, dungeon_name=dungeon_name, cfg=cfg
            )
        except Exception:
            logger.exception("GD daily podium failed cycle=%s", cycle.id)

    for i, r in enumerate(ranked):
        uid = int(r["user_id"])
        waifu_pre = (
            await session.execute(select(MainWaifu).where(MainWaifu.player_id == uid))
        ).scalar_one_or_none()
        player = await session.get(Player, uid)
        waifu_level = int(waifu_pre.level or 1) if waifu_pre else int(r.get("level") or 1)
        perfection_level = int(getattr(player, "perfection_level", 0) or 0) if player else int(
            r.get("perfection_level") or 0
        )
        payout = compute_daily_payout(
            msg_total=int(r.get("msg_total") or 0),
            waifu_level=waifu_level,
            perfection_level=perfection_level,
            cfg=cfg,
        )
        exp = int(payout["exp"])
        gold = int(payout["gold"])
        items: list[dict[str, Any]] = []
        if payout.get("eligible"):
            items = await roll_daily_reward_items(
                session,
                player_id=uid,
                waifu_level=waifu_level,
                item_chance=float(payout["item_chance"]),
                item_rolls=int(payout["item_rolls"]),
                cfg=cfg,
            )
        contrib_pct = contribution_display_pct(int(r.get("msg_total") or 0), sum_msgs)
        rew = GDRewardRow(
            cycle_id=cycle.id,
            user_id=uid,
            exp_earned=exp,
            gold_earned=gold,
            items_json=items if items else None,
            contribution_pct=contrib_pct,
            dm_sent=False,
        )
        session.add(rew)
        await session.flush()
        if player and gold > 0:
            player.gold = int(player.gold or 0) + gold
        if waifu_pre and exp > 0:
            waifu_pre.experience = (waifu_pre.experience or 0) + exp
            await apply_main_waifu_levelups(session, waifu_pre)
        try:
            from waifu_bot.services.hidden_milestones import hook_milestones

            await hook_milestones(session, uid, ["gd_regular"])
        except Exception:
            pass


async def _load_unsent_reward_parts(
    session: AsyncSession,
    game_dates: set[date],
) -> dict[tuple[int, date], list[dict[str, Any]]]:
    """Load unsent reward rows grouped by (user_id, game_date) with chat context."""
    if not game_dates:
        return {}
    rows = (
        await session.execute(
            select(GDRewardRow, GDCycle)
            .join(GDCycle, GDCycle.id == GDRewardRow.cycle_id)
            .where(
                GDRewardRow.dm_sent.is_(False),
                GDCycle.status == "finished",
                GDCycle.game_date.in_(tuple(game_dates)),
            )
            .order_by(GDRewardRow.id.asc())
        )
    ).all()
    if not rows:
        return {}

    cycle_ids = {int(c.id) for _, c in rows}
    regs = (
        await session.execute(
            select(GDRegistration).where(GDRegistration.cycle_id.in_(tuple(cycle_ids)))
        )
    ).scalars().all()
    regs_by_cycle: dict[int, list[GDRegistration]] = defaultdict(list)
    for reg in regs:
        regs_by_cycle[int(reg.cycle_id)].append(reg)

    tpl_ids = {int(c.dungeon_template_id) for _, c in rows if c.dungeon_template_id}
    tpls = {}
    if tpl_ids:
        for tpl in (
            await session.execute(
                select(GDDungeonTemplate).where(GDDungeonTemplate.id.in_(tuple(tpl_ids)))
            )
        ).scalars().all():
            tpls[int(tpl.id)] = tpl.name

    cfg = await get_game_config_map(session)
    out: dict[tuple[int, date], list[dict[str, Any]]] = defaultdict(list)

    for rew, cycle in rows:
        gdate = cycle.game_date
        if gdate is None:
            continue
        cycle_regs = regs_by_cycle.get(int(cycle.id), [])
        chat_total = int((cycle.battle_state_json or {}).get("chat_msg_total") or 0)
        summary = build_player_summary_rows(cycle_regs, chat_msg_total=chat_total)
        ranked = sort_rows_by_activity(summary)
        rank_map = {int(r["user_id"]): i + 1 for i, r in enumerate(ranked)}
        row_map = {int(r["user_id"]): r for r in ranked}
        uid = int(rew.user_id)
        rsum = row_map.get(uid) or {}
        msg_total = int(rsum.get("msg_total") or 0)
        payout = compute_daily_payout(msg_total=msg_total, waifu_level=int(rsum.get("level") or 1), cfg=cfg)
        items = rew.items_json if isinstance(rew.items_json, list) else (rew.items_json or None)
        if items is None:
            items = []
        out[(uid, gdate)].append(
            {
                "reward_id": int(rew.id),
                "reward": rew,
                "dungeon_name": tpls.get(int(cycle.dungeon_template_id), "Подземелье"),
                "rank": rank_map.get(uid, "?"),
                "party_size": len(ranked) or 1,
                "msg_total": msg_total,
                "counted_msgs": int(payout.get("counted_msgs") or 0),
                "damage_total": int(rsum.get("damage_total") or 0),
                "exp": int(rew.exp_earned or 0),
                "gold": int(rew.gold_earned or 0),
                "items": items,
            }
        )
    return out


def _mark_parts_dm_sent(parts: list[dict[str, Any]]) -> None:
    for p in parts:
        rew = p.get("reward")
        if rew is not None:
            rew.dm_sent = True


def _is_permanent_telegram_dm_error(exc: BaseException) -> bool:
    """True when retrying cannot succeed (blocked bot, deleted user, no chat)."""
    try:
        from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
    except Exception:  # pragma: no cover
        TelegramBadRequest = ()  # type: ignore[assignment,misc]
        TelegramForbiddenError = ()  # type: ignore[assignment,misc]

    if TelegramForbiddenError and isinstance(exc, TelegramForbiddenError):
        return True
    msg = str(exc or "").lower()
    if "bot was blocked by the user" in msg or "user is deactivated" in msg:
        return True
    if "chat not found" in msg or "bot can't initiate conversation" in msg:
        return True
    if TelegramBadRequest and isinstance(exc, TelegramBadRequest):
        return (
            "chat not found" in msg
            or "user is deactivated" in msg
            or "bot can't initiate conversation" in msg
            or "forbidden" in msg
        )
    return False


async def flush_daily_reward_dms(
    session: AsyncSession,
    bot: Any | None,
    game_dates: set[date] | None = None,
) -> tuple[int, int]:
    """Send one aggregated DM per (user_id, game_date).

    Returns ``(users_messaged, users_marked_dm_sent)``. Marked includes
    successful sends plus settled skips (Forbidden / zero reward).
    Reward digests are always attempted (not gated by group_dungeon prefs).
    """
    if not bot:
        return 0, 0
    today = msk_current_game_date()
    dates = set(game_dates or set())
    dates.add(today)
    dates.add(today - timedelta(days=1))

    grouped = await _load_unsent_reward_parts(session, dates)
    if not grouped:
        return 0, 0

    sent_users = 0
    marked_users = 0
    for (uid, gdate), parts in grouped.items():
        total_exp = sum(int(p.get("exp") or 0) for p in parts)
        total_gold = sum(int(p.get("gold") or 0) for p in parts)
        has_items = any(p.get("items") for p in parts)
        if total_exp <= 0 and total_gold <= 0 and not has_items:
            _mark_parts_dm_sent(parts)
            marked_users += 1
            logger.info(
                "GD daily reward DM settled (zero reward) uid=%s date=%s",
                uid,
                gdate,
            )
            continue

        text = format_aggregated_reward_dm(game_date=gdate, parts=parts)
        ok = False
        permanent_fail = False
        for chunk in _chunk_plain_text(text):
            chunk_ok = False
            for attempt in range(3):
                try:
                    await bot.send_message(chat_id=uid, text=chunk)
                    chunk_ok = True
                    break
                except Exception as e:
                    if _is_permanent_telegram_dm_error(e):
                        permanent_fail = True
                        logger.warning(
                            "GD daily reward DM permanent fail uid=%s date=%s err=%s: %s",
                            uid,
                            gdate,
                            type(e).__name__,
                            str(e)[:200],
                        )
                        break
                    logger.warning(
                        "GD daily reward DM attempt %s failed uid=%s date=%s err=%s: %s",
                        attempt,
                        uid,
                        gdate,
                        type(e).__name__,
                        str(e)[:200],
                    )
            if permanent_fail:
                ok = False
                break
            if not chunk_ok:
                ok = False
                break
            ok = True
        if permanent_fail:
            # Rewards already granted; stop retrying undeliverable DMs.
            _mark_parts_dm_sent(parts)
            marked_users += 1
            continue
        if not ok:
            continue
        _mark_parts_dm_sent(parts)
        marked_users += 1
        sent_users += 1
        logger.info("GD daily reward DM sent uid=%s date=%s", uid, gdate)
    if marked_users:
        await session.flush()
    return sent_users, marked_users


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
    now = datetime.now(timezone.utc)

    if force_cycle_id is not None:
        cycles = []
        c = await session.get(GDCycle, int(force_cycle_id))
        if c:
            cycles = [c]
    else:
        # Due cycles (ends_at elapsed); also outside the 04:00 window for catch-up.
        cycles = await gd.list_active_daily_cycles_due(session, now=now)

    done = 0
    touched_dates: set[date] = set()
    for cycle in cycles:
        lock_key = f"{REDIS_GD_DAILY_LOCK}fin:{cycle.id}"
        if not await _try_lock(redis_client, lock_key, ttl=180):
            continue
        try:
            fresh = await session.get(GDCycle, cycle.id)
            if not fresh or fresh.status != "active":
                continue

            word_stats: dict[int, dict[str, Any]] = {}
            try:
                phantom = await load_phantom_log(redis_client, fresh.id)
                words_timeout = float(cfg.get("gd_daily_words_timeout_seconds") or "60")
                word_stats = await analyze_day_word_stats(phantom, timeout_sec=words_timeout)
            except Exception:
                logger.exception("GD daily word stats failed cycle=%s", fresh.id)
            finally:
                try:
                    await purge_phantom_log(redis_client, fresh.id)
                except Exception:
                    pass

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
            merge_word_stats_into_rows(rows, word_stats)
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
            if fresh.game_date:
                touched_dates.add(fresh.game_date)
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

    # Aggregated DMs for touched dates + today/yesterday recovery sweep
    try:
        sent_n, marked_n = await flush_daily_reward_dms(session, bot, touched_dates)
        if marked_n:
            await session.commit()
            logger.info(
                "GD daily reward DMs flushed sent=%s settled=%s",
                sent_n,
                marked_n,
            )
    except Exception:
        await session.rollback()
        logger.exception("GD daily reward DM flush failed")

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

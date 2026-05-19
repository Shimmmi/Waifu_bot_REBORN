"""Тики экспедиции v1.3: урон, твисты, обновление HP, текст для Telegram."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import ActiveExpedition, ExpeditionAffix, ExpeditionSlot, HiredWaifu
from waifu_bot.game.expedition_redesign import (
    AFFIX_LEVEL_BASE_HP_PCT,
    PERK_CHALLENGE_CATEGORIES,
    _db_category_to_challenge_categories,
    best_perk_level_for_category,
    calc_event_damage,
    count_class_counters_for_category,
    count_race_counters_for_category,
    distribute_damage_to_squad,
    squad_perk_challenge_categories,
    twist_roll,
    union_challenge_categories_from_db_affix_rows,
    weighted_challenge_category,
)
from waifu_bot.services.expedition_events_ai import generate_expedition_tick_narrative


def _hp_bar(cur: int, max_hp: int, width: int = 10) -> str:
    if max_hp <= 0:
        return "░" * width
    filled = int(round(width * cur / max_hp))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


async def run_one_tick(session: AsyncSession, active: ActiveExpedition, *, silent: bool = False) -> dict:
    """
    Один тик (одно событие). Возвращает ok, narrative, telegram_narrative, telegram_status,
    telegram_text (склейка для совместимости), skip_damage.
    """
    if not active.affix_level or not active.affix_template_id:
        return {"ok": False, "error": "not_v13"}
    affix_level = int(active.affix_level)
    if affix_level not in AFFIX_LEVEL_BASE_HP_PCT:
        return {"ok": False, "error": "bad_affix_level"}

    affix_row = await session.get(ExpeditionAffix, int(active.affix_template_id))
    if not affix_row:
        return {"ok": False, "error": "affix_not_found"}

    squad_ids = list(active.squad_waifu_ids or [])
    squad: list[HiredWaifu] = []
    for wid in squad_ids:
        w = await session.get(HiredWaifu, wid)
        if w and w.player_id == active.player_id:
            squad.append(w)
    if not squad:
        return {"ok": False, "error": "no_squad"}

    primary = _db_category_to_challenge_categories(getattr(affix_row, "category", None))
    sid = getattr(active, "expedition_slot_id", None)
    if sid:
        slot = await session.get(ExpeditionSlot, int(sid))
        slot_aids = list(getattr(slot, "affix_ids", None) or []) if slot else []
        if slot_aids:
            stmt_sa = select(ExpeditionAffix).where(ExpeditionAffix.id.in_(slot_aids))
            slot_affix_rows = list((await session.execute(stmt_sa)).scalars().all())
            if slot_affix_rows:
                primary = union_challenge_categories_from_db_affix_rows(slot_affix_rows)
    squad_cats = frozenset()
    for u in squad:
        squad_cats = squad_cats | squad_perk_challenge_categories(u.perks or [])

    rng = random.Random((active.id << 8) + int(active.events_done or 0))
    challenge_cat = weighted_challenge_category(
        primary_categories=primary,
        squad_categories=squad_cats,
        rng=rng,
    )
    race_n = count_race_counters_for_category(squad, challenge_cat)
    class_n = count_class_counters_for_category(squad, challenge_cat)
    perk_lv = best_perk_level_for_category(squad, challenge_cat, default_level=1)
    base_pct = AFFIX_LEVEL_BASE_HP_PCT[affix_level]
    squad_hp_total = sum(max(1, int(getattr(u, "max_hp", 1) or 1)) for u in squad)
    variance = rng.uniform(0.85, 1.15)
    total_dmg = calc_event_damage(
        base_hp_pct=base_pct,
        squad_hp_total=squad_hp_total,
        race_counters=race_n,
        class_counters=class_n,
        perk_level=perk_lv,
        difficulty_level=affix_level,
        rand_variance=variance,
    )

    twist = twist_roll(rng)
    skip_damage = bool(twist and twist.get("skip_next_damage"))
    hp_restore_pct = float(twist.get("hp_restore_pct") or 0) if twist else 0.0

    if not skip_damage:
        dist = distribute_damage_to_squad(squad, total_dmg)
        now = datetime.now(tz=timezone.utc)
        for u in squad:
            uid = int(u.id)
            dmg = int(dist.get(uid, 0))
            cur = int(getattr(u, "current_hp", u.max_hp) or 0)
            u.current_hp = max(0, cur - dmg)
            u.hp_updated_at = now
    if hp_restore_pct > 0:
        for u in squad:
            m = max(1, int(getattr(u, "max_hp", 1) or 1))
            c = int(getattr(u, "current_hp", 0) or 0)
            u.current_hp = min(m, c + int(round(m * hp_restore_pct)))

    events_done = int(active.events_done or 0) + 1
    events_total = int(active.events_total or 0)
    active.events_done = events_done
    started = active.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if events_done < events_total:
        active.next_tick_at = started + timedelta(minutes=15 * (events_done + 1))
    else:
        active.next_tick_at = None

    ts = dict(active.tick_state or {})
    prev = ts.get("last_narrative") or ""
    loc = active.display_base_location or "Локация"
    roman = ("I", "II", "III", "IV", "V")[affix_level - 1]
    affix_name = getattr(affix_row, "name", "") or ""
    challenge_label = f"{affix_name.strip()} {roman}".strip()

    outcome_roll = rng.random()
    if outcome_roll < 0.45:
        outcome = "triumph"
    elif outcome_roll < 0.78:
        outcome = "struggle"
    else:
        outcome = "survived_barely"

    if silent:
        narrative = "…"
    else:
        total_max_hp = sum(max(1, int(getattr(u, "max_hp", 1) or 1)) for u in squad)
        total_cur_hp = sum(max(0, int(getattr(u, "current_hp", 0) or 0)) for u in squad)
        squad_hp_ratio = (total_cur_hp / total_max_hp) if total_max_hp else 0.0
        narrative = await generate_expedition_tick_narrative(
            location=loc,
            biome_tags=[active.display_biome_tag or ""],
            challenge_name=challenge_label,
            challenge_category=challenge_cat,
            challenge_level=affix_level,
            squad_snapshot=[
                {
                    "name": u.name or "Наёмница",
                    "class_id": int(u.class_ or 1),
                    "race_id": int(u.race or 1),
                    "hp_current": int(getattr(u, "current_hp", 0) or 0),
                    "hp_max": int(getattr(u, "max_hp", 1) or 1),
                    "matched_perks": [
                        str(p)
                        for p in (u.perks or [])
                        if challenge_cat in PERK_CHALLENGE_CATEGORIES.get(str(p), frozenset())
                    ],
                }
                for u in squad
            ],
            outcome=outcome,
            event_num=events_done,
            total_events=events_total,
            is_final=(events_done >= events_total),
            twist=twist,
            prev_summary=prev,
            squad_hp_ratio=squad_hp_ratio,
        )
    ts["last_narrative"] = (narrative or "") if not silent else (ts.get("last_narrative") or "")
    ts["last_challenge_category"] = challenge_cat
    active.tick_state = ts

    now = datetime.now(tz=timezone.utc)
    ends_at = active.ends_at
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    sec_left = max(0, int((ends_at - now).total_seconds()))
    left_min = max(0, sec_left // 60)

    if silent:
        return {
            "ok": True,
            "telegram_text": "",
            "telegram_narrative": "",
            "telegram_status": "",
            "narrative": "",
            "skip_damage": skip_damage,
        }

    narr_lines = [
        f"🗺 «{loc}» · Событие {events_done}/{events_total} · осталось ~{left_min} мин",
        "",
        (narrative or "…"),
    ]
    if twist and twist.get("text"):
        narr_lines.append("")
        narr_lines.append(f"✨ {twist['text']}")
    narrative_msg = "\n".join(narr_lines)

    status_lines = [
        "━━━━━━━━━━━━━━━━━",
    ]
    for u in squad:
        c = int(getattr(u, "current_hp", 0) or 0)
        m = max(1, int(getattr(u, "max_hp", 1) or 1))
        warn = " ⚠️" if c < m * 0.25 else ""
        status_lines.append(f"❤ {u.name or 'Наёмница'}   {_hp_bar(c, m)}  {c}/{m}{warn}")
    status_lines.append("━━━━━━━━━━━━━━━━━")
    status_lines.append(f"🪙 Накоплено: {int(active.reward_gold or 0)} золота")
    status_lines.append(f"✨ Опыт: +{int(active.reward_experience or 0)} (по возвращении)")
    status_lines.append("(база до итога; после экспедиции применяется множитель исхода)")
    status_msg = "\n".join(status_lines)

    return {
        "ok": True,
        "telegram_text": narrative_msg + "\n\n" + status_msg,
        "telegram_narrative": narrative_msg,
        "telegram_status": status_msg,
        "narrative": narrative,
        "skip_damage": skip_damage,
    }

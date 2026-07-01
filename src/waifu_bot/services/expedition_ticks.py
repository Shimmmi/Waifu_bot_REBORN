"""Тики экспедиции v1.3/v1.4: урон по тегам сложности + ±10% challenge, твисты, Telegram."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import ActiveExpedition, ExpeditionAffix, ExpeditionSlot, HiredWaifu
from waifu_bot.game.expedition_data import PERK_BY_ID
from waifu_bot.game.expedition_difficulty_tags import (
    DIFFICULTY_TAG_LABEL_RU,
    PERK_TAG_COVERAGE,
    challenge_categories_boosted_by_tags,
    resolve_perk_id,
    squad_covered_tags,
    unit_covered_tags,
    union_affix_tags,
    union_legacy_affix_tags,
)
from waifu_bot.game.expedition_redesign import (
    AFFIX_LEVEL_BASE_HP_PCT,
    PERK_CHALLENGE_CATEGORIES,
    _db_category_to_challenge_categories,
    calc_event_damage_v14,
    distribute_damage_to_squad,
    expedition_event_interval_minutes,
    squad_perk_challenge_categories,
    twist_roll,
    union_challenge_categories_from_db_affix_rows,
    weighted_challenge_category,
)
from waifu_bot.game.expedition_narrative_catalog import archetype_for_id, mode_for_id
from waifu_bot.services.expedition_events_ai import generate_expedition_tick_narrative


def _hp_bar(cur: int, max_hp: int, width: int = 10) -> str:
    if max_hp <= 0:
        return "░" * width
    filled = int(round(width * cur / max_hp))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _tag_labels(tag_ids: frozenset[str] | set[str]) -> list[str]:
    return [
        DIFFICULTY_TAG_LABEL_RU[t]
        for t in sorted(tag_ids)
        if t in DIFFICULTY_TAG_LABEL_RU
    ]


def tick_narrative_history(tick_state: dict | None) -> list[str]:
    """Эпизоды экспедиции для финального нарратива (history или fallback на last_narrative)."""
    ts = tick_state or {}
    hist = ts.get("narrative_history")
    if isinstance(hist, list):
        out = [str(x).strip() for x in hist if str(x).strip()]
        if out:
            return out
    last = ts.get("last_narrative")
    if last and str(last).strip():
        return [str(last).strip()]
    return []


def _tick_pressure_label(*, squad_prepared: bool, tag_mult: float, uncovered_count: int) -> str:
    if not squad_prepared or uncovered_count >= 2:
        return "high"
    if squad_prepared and tag_mult <= 0.92:
        return "low"
    return "medium"


def _roll_narrative_outcome(rng: random.Random, *, squad_prepared: bool) -> str:
    roll = rng.random()
    if squad_prepared:
        if roll < 0.55:
            return "triumph"
        if roll < 0.85:
            return "struggle"
        return "survived_barely"
    if roll < 0.25:
        return "triumph"
    if roll < 0.65:
        return "struggle"
    return "survived_barely"


def _relevant_perk_names_for_tags(unit: HiredWaifu, tag_ids: frozenset[str]) -> list[str]:
    names: list[str] = []
    for p in getattr(unit, "perks", None) or []:
        pid = resolve_perk_id(str(p) if p is not None else "")
        tags = PERK_TAG_COVERAGE.get(pid)
        if tags and tags & tag_ids:
            perk = PERK_BY_ID.get(pid)
            names.append(getattr(perk, "name", None) or pid)
    return names


def _build_squad_snapshot_for_narrative(
    squad: list[HiredWaifu],
    *,
    challenge_cat: str,
    active_tags: frozenset[str],
) -> list[dict]:
    out: list[dict] = []
    for u in squad:
        unit_tags = unit_covered_tags(u)
        counter_tags = active_tags & unit_tags
        out.append(
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
                "counter_tags_ru": _tag_labels(counter_tags),
                "relevant_perk_names": _relevant_perk_names_for_tags(u, active_tags),
            }
        )
    return out


def _active_tags_for_run(
    active: ActiveExpedition,
    slot: ExpeditionSlot | None,
    slot_affix_rows: list,
    affix_row: ExpeditionAffix | None,
) -> frozenset[str]:
    snap = getattr(active, "difficulty_tags_snapshot", None)
    if snap:
        valid = {str(t) for t in snap if str(t) in DIFFICULTY_TAG_LABEL_RU}
        if valid:
            return frozenset(valid)
    if slot_affix_rows:
        return union_affix_tags(slot_affix_rows)
    if slot:
        legacy = list(getattr(slot, "affixes", None) or [])
        if legacy:
            return union_legacy_affix_tags(legacy)
    if affix_row:
        return union_affix_tags([affix_row])
    return frozenset()


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
    slot: ExpeditionSlot | None = None
    slot_affix_rows: list = []
    sid = getattr(active, "expedition_slot_id", None)
    if sid:
        slot = await session.get(ExpeditionSlot, int(sid))
        slot_aids = list(getattr(slot, "affix_ids", None) or []) if slot else []
        if slot_aids:
            stmt_sa = select(ExpeditionAffix).where(ExpeditionAffix.id.in_(slot_aids))
            slot_affix_rows = list((await session.execute(stmt_sa)).scalars().all())
            if slot_affix_rows:
                primary = union_challenge_categories_from_db_affix_rows(slot_affix_rows)

    active_tags = _active_tags_for_run(active, slot, slot_affix_rows, affix_row)
    covered_tags = squad_covered_tags(squad)
    tag_boost = challenge_categories_boosted_by_tags(active_tags)

    squad_cats = frozenset()
    for u in squad:
        squad_cats = squad_cats | squad_perk_challenge_categories(u.perks or [])

    rng = random.Random((active.id << 8) + int(active.events_done or 0))
    challenge_cat = weighted_challenge_category(
        primary_categories=primary,
        squad_categories=squad_cats,
        tag_boosted_categories=tag_boost,
        rng=rng,
    )
    base_pct = AFFIX_LEVEL_BASE_HP_PCT[affix_level]
    squad_hp_total = sum(max(1, int(getattr(u, "max_hp", 1) or 1)) for u in squad)
    variance = rng.uniform(0.85, 1.15)
    total_dmg = calc_event_damage_v14(
        base_hp_pct=base_pct,
        squad_hp_total=squad_hp_total,
        active_tags=active_tags,
        covered_tags=covered_tags,
        challenge_cat=challenge_cat,
        squad=squad,
        primary_categories=primary,
        affix_level=affix_level,
        rand_variance=variance,
    )

    from waifu_bot.game.expedition_difficulty_tags import calc_tag_coverage_ratio, calc_tag_effectiveness_mult, calc_tick_challenge_adj

    tag_mult = calc_tag_effectiveness_mult(
        active_tags, covered_tags & active_tags, squad=squad, affix_level=affix_level
    )
    tick_adj = calc_tick_challenge_adj(challenge_cat, squad, primary, affix_level=affix_level)

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
        interval = expedition_event_interval_minutes(
            int(active.duration_minutes or 0),
            events_total,
        )
        active.next_tick_at = started + timedelta(minutes=interval * (events_done + 1))
    else:
        active.next_tick_at = None

    ts = dict(active.tick_state or {})
    prev = ts.get("last_narrative") or ""
    loc = active.display_base_location or "Локация"
    roman = ("I", "II", "III", "IV", "V")[affix_level - 1]
    affix_name = getattr(affix_row, "name", "") or ""
    challenge_label = f"{affix_name.strip()} {roman}".strip()

    uncovered_tags = active_tags - covered_tags
    squad_prepared = not (uncovered_tags & active_tags)
    outcome = _roll_narrative_outcome(rng, squad_prepared=squad_prepared)

    from waifu_bot.game.expedition_overhaul import gate_log_entry

    gate_log = list(ts.get("gate_log") or [])
    actual_dmg = 0 if skip_damage else int(total_dmg)
    twist_text = str(twist.get("text") or "").strip() if twist else ""
    if skip_damage:
        twist_text = twist_text or "урон пропущен"
    coverage_ratio = calc_tag_coverage_ratio(
        active_tags,
        covered_tags & active_tags,
        squad=squad,
        affix_level=affix_level,
    )
    gate_log.append(
        gate_log_entry(
            event_index=events_done,
            category=challenge_cat,
            damage=actual_dmg,
            covered=bool(squad_prepared),
            base_pct=base_pct,
            tag_mult=float(tag_mult),
            challenge_adj=float(tick_adj),
            variance=float(variance),
            twist=twist_text,
            active_tags=sorted(list(active_tags)),
            covered_tags=sorted(list(active_tags & covered_tags)),
            coverage=coverage_ratio,
        )
    )
    ts["gate_log"] = gate_log

    if silent:
        narrative = "…"
    else:
        total_max_hp = sum(max(1, int(getattr(u, "max_hp", 1) or 1)) for u in squad)
        total_cur_hp = sum(max(0, int(getattr(u, "current_hp", 0) or 0)) for u in squad)
        squad_hp_ratio = (total_cur_hp / total_max_hp) if total_max_hp else 0.0

        brief = getattr(active, "narrative_brief", None) or {}
        arch = archetype_for_id(getattr(active, "location_archetype_id", None))
        mode = mode_for_id(getattr(active, "expedition_mode_id", None))
        beats = brief.get("event_beats") if isinstance(brief, dict) else []
        current_beat = ""
        if isinstance(beats, list) and events_done <= len(beats):
            current_beat = str(beats[events_done - 1] or "")
        affix_hints = [
            str(getattr(a, "description_hint", "") or "").strip()
            for a in slot_affix_rows
            if getattr(a, "description_hint", None)
        ]
        tag_labels = _tag_labels(active_tags)
        covered_on_active = active_tags & covered_tags
        tick_pressure = _tick_pressure_label(
            squad_prepared=squad_prepared,
            tag_mult=float(tag_mult),
            uncovered_count=len(uncovered_tags & active_tags),
        )
        slot_affix_names = [
            str(getattr(a, "name", "") or "").strip()
            for a in slot_affix_rows
            if str(getattr(a, "name", "") or "").strip()
        ]
        if not slot_affix_names and affix_name:
            slot_affix_names = [affix_name.strip()]
        expedition_context = {
            "title": (brief.get("title") if isinstance(brief, dict) else None) or loc,
            "mode": mode.name_ru if mode else "",
            "archetype": arch.name_ru if arch else "",
            "setting": (brief.get("setting_summary") if isinstance(brief, dict) else "") or "",
            "intro_narrative": (brief.get("intro_narrative") if isinstance(brief, dict) else "") or "",
            "event_beat": current_beat,
            "key_elements": (brief.get("key_elements") if isinstance(brief, dict) else []) or [],
            "mode_rules": mode.prompt_rules_ru if mode else "",
            "avoid_tropes": (brief.get("avoid_tropes") if isinstance(brief, dict) else []) or [],
            "narrative_style_id": brief.get("narrative_style_id") if isinstance(brief, dict) else None,
            "narrative_style_name": brief.get("narrative_style_name") if isinstance(brief, dict) else None,
            "affix_hints": affix_hints[:4],
            "difficulty_tags_ru": tag_labels[:6],
            "tick_pressure": tick_pressure,
            "threats": {
                "slot_affixes_ru": slot_affix_names[:6],
                "active_tags_ru": _tag_labels(active_tags),
                "covered_tags_ru": _tag_labels(covered_on_active),
                "uncovered_tags_ru": _tag_labels(uncovered_tags & active_tags),
                "squad_prepared": squad_prepared,
            },
        }

        narrative = await generate_expedition_tick_narrative(
            location=loc,
            biome_tags=[active.display_biome_tag or ""],
            challenge_name=challenge_label,
            challenge_category=challenge_cat,
            challenge_level=affix_level,
            squad_snapshot=_build_squad_snapshot_for_narrative(
                squad,
                challenge_cat=challenge_cat,
                active_tags=active_tags,
            ),
            outcome=outcome,
            event_num=events_done,
            total_events=events_total,
            is_final=(events_done >= events_total),
            twist=twist,
            prev_summary=prev,
            squad_hp_ratio=squad_hp_ratio,
            expedition_context=expedition_context,
        )
    ts["last_narrative"] = (narrative or "") if not silent else (ts.get("last_narrative") or "")
    if narrative and not silent:
        hist = list(ts.get("narrative_history") or [])
        hist.append(str(narrative).strip())
        ts["narrative_history"] = hist[-15:]
    ts["last_challenge_category"] = challenge_cat
    ts["last_outcome"] = outcome
    ts["squad_prepared"] = squad_prepared
    ts["tag_mult"] = round(tag_mult, 4)
    ts["tick_adj"] = round(tick_adj, 4)
    ts["active_tags"] = sorted(active_tags)
    ts["covered_tags"] = sorted(covered_tags & active_tags)
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

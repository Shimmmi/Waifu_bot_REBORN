"""Старт экспедиции v2: reward_type + depth_tier + процедурная генерация."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import ActiveExpedition, ExpeditionAffix, HiredWaifu, Player
from waifu_bot.game.constants import EXPEDITION_MAX_CONCURRENT, EXPEDITION_MAX_SQUAD, EXPEDITION_MIN_SQUAD
from waifu_bot.game.expedition_difficulty_tags import sorted_tag_list, tags_for_db_affix_row
from waifu_bot.game.expedition_narrative_catalog import pick_expedition_mode, pick_location_archetype
from waifu_bot.game.expedition_overhaul import (
    base_reward_amount,
    depth_tier_by_id,
    pick_procedural_affixes,
    squad_power_total,
    tick_affix_count,
    validate_reward_type,
)
from waifu_bot.game.expedition_redesign import (
    affix_display_icon,
    expedition_event_interval_minutes,
    roman_numeral,
)
from waifu_bot.services.expedition import tags_snapshot_for_affix_rows
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.hired_waifu_state import hired_expedition_eligible, sync_hired_hp_after_heal_complete
from waifu_bot.services.passive_skills import expedition_reward_multiplier, get_passive_skill_bonuses


async def start_expedition_v2(
    service: Any,
    session: AsyncSession,
    player_id: int,
    squad_waifu_ids: list[int],
    reward_type: str,
    depth_tier: int,
) -> dict:
    rt = validate_reward_type(reward_type)
    if not rt:
        return {"error": "invalid_reward_type"}
    depth = depth_tier_by_id(int(depth_tier))
    if depth is None:
        return {"error": "invalid_depth_tier"}

    if not (EXPEDITION_MIN_SQUAD <= len(squad_waifu_ids) <= EXPEDITION_MAX_SQUAD):
        return {"error": "squad_size", "min": EXPEDITION_MIN_SQUAD, "max": EXPEDITION_MAX_SQUAD}

    player = await service._lock_player_for_update(session, player_id)
    if not player:
        return {"error": "player_not_found"}

    if await service._count_active_expeditions(session, player_id) >= EXPEDITION_MAX_CONCURRENT:
        return {"error": "too_many_expeditions", "max": EXPEDITION_MAX_CONCURRENT}

    now = datetime.now(tz=timezone.utc)
    squad: list[HiredWaifu] = []
    for wid in squad_waifu_ids:
        w = await session.get(HiredWaifu, wid)
        if not w or w.player_id != player_id:
            return {"error": "waifu_not_found", "waifu_id": wid}
        sync_hired_hp_after_heal_complete(w, now)
        ok, err = hired_expedition_eligible(w, now)
        if not ok:
            return {"error": err or "waifu_not_eligible", "waifu_id": wid}
        squad.append(w)

    sq_power = squad_power_total(squad)
    if sq_power < depth.min_squad_power:
        return {
            "error": "insufficient_power",
            "required": depth.min_squad_power,
            "have": sq_power,
        }

    # Процедурная локация и аффиксы
    seed = f"{player_id}-{now.timestamp()}-{rt}-{depth.tier}"
    rng = random.Random(seed)
    archetype = pick_location_archetype(rng)
    mode = pick_expedition_mode(rng)
    loc = archetype.name_ru
    biome = archetype.biome_tag

    affix_rows: list[ExpeditionAffix] = list(
        (await session.execute(select(ExpeditionAffix).order_by(ExpeditionAffix.id))).scalars().all()
    )
    # Flavor-only: intro narrative / card icon. Combat tags re-roll each tick in run_one_tick.
    chosen_affixes = pick_procedural_affixes(affix_rows, rng, count=tick_affix_count(depth.tier))
    affix_row = chosen_affixes[0] if chosen_affixes else None
    tag_snap = tags_snapshot_for_affix_rows(chosen_affixes) if chosen_affixes else []

    events_total = depth.events_count
    duration_minutes = depth.duration_minutes
    difficulty_level = depth.difficulty_level
    tick_interval = expedition_event_interval_minutes(duration_minutes, events_total)

    from waifu_bot.db.models import MainWaifu

    mw = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == int(player_id)))
    player_level = int(mw.level or 1) if mw else 10

    base_val = base_reward_amount(rt, depth=depth, player_level=player_level)
    ps_exp = await get_passive_skill_bonuses(session, player_id)
    hs_exp = await get_hidden_skill_bonuses(session, player_id)
    rm = expedition_reward_multiplier(ps_exp, hs_exp)

    reward_gold = max(0, int(round(base_val * rm))) if rt in ("gold", "mixed") else 0
    reward_exp = max(0, int(round(base_val * rm))) if rt in ("waifu_exp", "merc_exp", "mixed") else max(
        0, int(round(base_val * 0.5 * rm))
    )

    ends_at = now + timedelta(minutes=duration_minutes)
    display_name = f"{mode.name_ru}: {loc}"

    active = ActiveExpedition(
        player_id=player_id,
        expedition_slot_id=None,
        started_at=now,
        ends_at=ends_at,
        duration_minutes=duration_minutes,
        chance=0.0,
        success=False,
        reward_gold=reward_gold,
        reward_experience=reward_exp,
        squad_waifu_ids=list(squad_waifu_ids),
        affix_level=difficulty_level,
        affix_template_id=int(affix_row.id) if affix_row else None,
        display_base_location=display_name,
        display_biome_tag=biome,
        events_total=events_total,
        events_done=0,
        next_tick_at=now + timedelta(minutes=tick_interval) if events_total > 0 else None,
        tick_state={"gate_log": []},
        difficulty_tags_snapshot=tag_snap,
        location_archetype_id=archetype.id,
        expedition_mode_id=mode.id,
        reward_type=rt,
        depth_tier=depth.tier,
    )
    session.add(active)
    await session.flush()

    start_intro_narrative = None
    if events_total > 0:
        from waifu_bot.services.expedition import _apply_narrative_at_start

        start_intro_narrative = await _apply_narrative_at_start(
            session,
            active,
            location_archetype_id=archetype.id,
            expedition_mode_id=mode.id,
            legacy_base_location=loc,
            affix_rows=chosen_affixes,
            squad=squad,
            events_total=events_total,
            duration_minutes=duration_minutes,
        )

    await service._lock_squad_expedition(session, active.id, squad_waifu_ids)
    await session.commit()
    await session.refresh(active)

    return {
        "success": True,
        "active_id": active.id,
        "expedition_name": display_name,
        "chance": 0.0,
        "success_result": False,
        "reward_gold": reward_gold,
        "reward_experience": reward_exp,
        "reward_type": rt,
        "depth_tier": depth.tier,
        "squad_power": sq_power,
        "ends_at": ends_at.isoformat(),
        "duration_minutes": duration_minutes,
        "affix_icon": affix_display_icon(affix_row) if affix_row else "🗺",
        "affix_level_roman": roman_numeral(difficulty_level),
        "events_total": events_total,
        "start_intro_narrative": start_intro_narrative,
    }

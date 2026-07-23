"""Merc overhaul services: pity hire, debut, lineup, fodder, ops board, arena, exchange."""
from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import HiredWaifu, MainWaifu, Player, TavernState
from waifu_bot.db.models.merc_meta import MercArenaMatch, MercOpsBoard
from waifu_bot.db.models.waifu import WaifuClass, WaifuRace, WaifuRarity
from waifu_bot.game.merc_arena import fighter_from_unit, simulate_3v3
from waifu_bot.game.merc_combat_rating import refresh_unit_power
from waifu_bot.game.merc_legendary_templates import (
    DEBUT_PICK_IDS,
    LEGENDARY_TEMPLATES,
    TEMPLATE_BY_ID,
    template_public,
)
from waifu_bot.game.merc_perks import (
    PERK_BY_ID,
    archetype_for_perks,
    catalog_public,
    migrate_perk_list,
    roll_perk_ids_for_rarity,
)
from waifu_bot.game.merc_potential import (
    add_manual,
    bench_cap_for_main_level,
    consume_manual,
    fodder_cost_for_next_star,
    normalize_drill_manuals,
    perk_level_cap,
    perk_soft_cap,
)
from waifu_bot.game.merc_config import (
    ARENA_TICKETS_DAILY,
    ARENA_UNLOCK_ACT,
    LEG_BASE_RATE,
    PITY_EPIC_HARD,
    PITY_LEG_HARD,
    PITY_LEG_SOFT_START,
)
from waifu_bot.game.merc_threat_tags import THREAT_TAG_LABELS_RU, THREAT_TAGS

try:
    from zoneinfo import ZoneInfo

    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover
    MOSCOW_TZ = timezone.utc

# Re-export for callers / tests
__all_pity__ = (PITY_LEG_HARD, PITY_LEG_SOFT_START, PITY_EPIC_HARD, LEG_BASE_RATE)


def _moscow_day_key() -> str:
    return datetime.now(tz=MOSCOW_TZ).date().isoformat()


def _week_key() -> str:
    now = datetime.now(tz=MOSCOW_TZ)
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def get_or_create_tavern_state(session: AsyncSession, player_id: int) -> TavernState:
    stmt = select(TavernState).where(TavernState.player_id == player_id)
    state = (await session.execute(stmt)).scalar_one_or_none()
    if not state:
        state = TavernState(player_id=player_id)
        session.add(state)
        await session.flush()
    await migrate_perk_points_to_t1_notes(session, player_id, state)
    state.drill_manuals = normalize_drill_manuals(getattr(state, "drill_manuals", None))
    return state


async def migrate_perk_points_to_t1_notes(
    session: AsyncSession, player_id: int, state: TavernState
) -> None:
    """One-shot: convert leftover perk_upgrade_points into T1 notes by unit perk type."""
    rows = (
        await session.execute(select(HiredWaifu).where(HiredWaifu.player_id == player_id))
    ).scalars().all()
    changed = False
    manuals = normalize_drill_manuals(getattr(state, "drill_manuals", None))
    for u in rows:
        pts = int(getattr(u, "perk_upgrade_points", 0) or 0)
        if pts <= 0:
            continue
        ptype = "ATK"
        perks = migrate_perk_list(list(u.perks or []))
        if perks:
            perk = PERK_BY_ID.get(perks[0])
            if perk:
                ptype = perk.perk_type
        manuals = add_manual(manuals, ptype, tier=1, amount=pts)
        u.perk_upgrade_points = 0
        changed = True
    if changed:
        state.drill_manuals = manuals
        await session.flush()


async def main_waifu_level(session: AsyncSession, player_id: int) -> int:
    mw = (
        await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))
    ).scalar_one_or_none()
    return int(getattr(mw, "level", 1) or 1) if mw else 1


async def pool_count(session: AsyncSession, player_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(HiredWaifu).where(HiredWaifu.player_id == player_id)
        )
        or 0
    )


async def bench_cap(session: AsyncSession, player_id: int) -> int:
    return bench_cap_for_main_level(await main_waifu_level(session, player_id))


def pity_status(state: TavernState) -> dict[str, Any]:
    manuals = normalize_drill_manuals(getattr(state, "drill_manuals", None))
    # keep normalized form on state when read
    if dict(getattr(state, "drill_manuals", None) or {}) != manuals:
        state.drill_manuals = manuals
    return {
        "pity_legendary": int(getattr(state, "pity_legendary", 0) or 0),
        "pity_legendary_hard": PITY_LEG_HARD,
        "pity_epic": int(getattr(state, "pity_epic", 0) or 0),
        "pity_epic_hard": PITY_EPIC_HARD,
        "debut_legendary_done": bool(getattr(state, "debut_legendary_done", False)),
        "merc_coins": int(getattr(state, "merc_coins", 0) or 0),
        "merc_contracts": int(getattr(state, "merc_contracts", 0) or 0),
        "merc_dust": int(getattr(state, "merc_dust", 0) or 0),
        "legendary_crests": int(getattr(state, "legendary_crests", 0) or 0),
        "drill_manuals": manuals,
        "merc_gear_bag": list(getattr(state, "merc_gear_bag", None) or []),
        "arena_rating": int(getattr(state, "arena_rating", 1000) or 1000),
        "arena_tickets": int(getattr(state, "arena_tickets", ARENA_TICKETS_DAILY) or 0),
        "codex_count": len(list(getattr(state, "codex_legendary_ids", None) or [])),
    }


def _roll_rarity_with_pity(state: TavernState, rng: random.Random) -> WaifuRarity:
    """Update pity counters on state; return rolled rarity."""
    leg_c = int(getattr(state, "pity_legendary", 0) or 0) + 1
    epic_c = int(getattr(state, "pity_epic", 0) or 0) + 1
    state.pity_legendary = leg_c
    state.pity_epic = epic_c

    # Hard pity legendary
    if leg_c >= PITY_LEG_HARD:
        state.pity_legendary = 0
        return WaifuRarity.LEGENDARY

    # Soft pity legendary
    leg_rate = LEG_BASE_RATE
    if leg_c >= PITY_LEG_SOFT_START:
        # linear ramp to ~100% at hard
        span = max(1, PITY_LEG_HARD - PITY_LEG_SOFT_START)
        leg_rate = LEG_BASE_RATE + (1.0 - LEG_BASE_RATE) * ((leg_c - PITY_LEG_SOFT_START) / span)

    if rng.random() < leg_rate:
        state.pity_legendary = 0
        return WaifuRarity.LEGENDARY

    # Epic hard pity (does not reset legendary counter)
    if epic_c >= PITY_EPIC_HARD:
        state.pity_epic = 0
        return WaifuRarity.EPIC

    r = rng.random()
    # renormalize non-leg rates among remaining
    if r < 0.50:
        return WaifuRarity.COMMON
    if r < 0.80:
        return WaifuRarity.UNCOMMON
    if r < 0.95:
        return WaifuRarity.RARE
    state.pity_epic = 0
    return WaifuRarity.EPIC


async def _owned_template_ids(session: AsyncSession, player_id: int) -> set[str]:
    rows = (
        await session.execute(
            select(HiredWaifu.template_id).where(
                HiredWaifu.player_id == player_id,
                HiredWaifu.template_id.isnot(None),
            )
        )
    ).all()
    return {str(r[0]) for r in rows if r[0]}


def _unlock_codex(state: TavernState, template_id: str) -> None:
    ids = list(getattr(state, "codex_legendary_ids", None) or [])
    if template_id not in ids:
        ids.append(template_id)
        state.codex_legendary_ids = ids


async def create_from_template(
    session: AsyncSession,
    player_id: int,
    template_id: str,
    *,
    start_level: int = 1,
    start_exp: int = 0,
) -> HiredWaifu | dict:
    """Create legendary from template, or grant crest if duplicate."""
    tpl = TEMPLATE_BY_ID.get(template_id)
    if not tpl:
        return {"error": "template_not_found"}
    state = await get_or_create_tavern_state(session, player_id)
    owned = await _owned_template_ids(session, player_id)
    if template_id in owned:
        state.legendary_crests = int(getattr(state, "legendary_crests", 0) or 0) + 1
        _unlock_codex(state, template_id)
        return {"duplicate": True, "crest_gained": 1, "template_id": template_id}

    perk_ids = roll_perk_ids_for_rarity(
        int(WaifuRarity.LEGENDARY),
        forced_legendary_id=tpl.legendary_perk_id,
    )
    max_hp = 50 + start_level * 15
    now = datetime.now(timezone.utc)
    waifu = HiredWaifu(
        player_id=player_id,
        name=tpl.name_ru,
        race=tpl.race,
        class_=tpl.class_,
        rarity=int(WaifuRarity.LEGENDARY),
        level=start_level,
        exp_current=start_exp,
        perks=perk_ids,
        perk_levels={pid: 1 for pid in perk_ids},
        bio=tpl.lore_ru,
        template_id=tpl.id,
        squad_position=None,
        max_hp=max_hp,
        current_hp=max_hp,
        hp_updated_at=now,
        potential_stars=0,
    )
    refresh_unit_power(waifu)
    session.add(waifu)
    await session.flush()
    _unlock_codex(state, template_id)
    return waifu


async def debut_legendary(session: AsyncSession, player_id: int, template_id: str) -> dict:
    state = await get_or_create_tavern_state(session, player_id)
    if bool(getattr(state, "debut_legendary_done", False)):
        return {"error": "debut_already_done"}
    if template_id not in DEBUT_PICK_IDS:
        return {"error": "invalid_debut_pick", "allowed": list(DEBUT_PICK_IDS)}
    cap = await bench_cap(session, player_id)
    if await pool_count(session, player_id) >= cap:
        return {"error": "reserve_full", "cap": cap}
    result = await create_from_template(session, player_id, template_id)
    if isinstance(result, dict) and result.get("error"):
        return result
    state.debut_legendary_done = True
    if isinstance(result, dict) and result.get("duplicate"):
        return {"ok": True, **result}
    waifu = result
    return {
        "ok": True,
        "waifu_id": waifu.id,
        "name": waifu.name,
        "template_id": template_id,
        "rarity": int(WaifuRarity.LEGENDARY),
    }


def debut_options() -> list[dict]:
    return [template_public(TEMPLATE_BY_ID[i], unlocked=True) for i in DEBUT_PICK_IDS if i in TEMPLATE_BY_ID]


async def generate_hired_with_pity(session: AsyncSession, player_id: int) -> HiredWaifu | dict:
    """Core roll used by tavern hire. May return crest-dict for duplicate legendary."""
    from waifu_bot.services.expedition import hired_level_from_total_exp

    state = await get_or_create_tavern_state(session, player_id)
    start_level, start_exp = 1, 0
    pending = max(0, int(getattr(state, "pending_hired_exp", 0) or 0))
    if pending > 0:
        start_level, start_exp = hired_level_from_total_exp(pending)
        state.pending_hired_exp = 0

    rng = random.Random()
    rarity = _roll_rarity_with_pity(state, rng)

    if rarity == WaifuRarity.LEGENDARY:
        # Prefer not-owned templates
        owned = await _owned_template_ids(session, player_id)
        pool = [t for t in LEGENDARY_TEMPLATES if t.id not in owned] or list(LEGENDARY_TEMPLATES)
        tpl = rng.choice(pool)
        return await create_from_template(
            session, player_id, tpl.id, start_level=start_level, start_exp=start_exp
        )

    race = WaifuRace(rng.randint(1, 7))
    class_ = WaifuClass(rng.randint(1, 7))
    perk_ids = roll_perk_ids_for_rarity(int(rarity.value), rng=rng)
    max_hp = 50 + start_level * 15
    now = datetime.now(timezone.utc)
    waifu = HiredWaifu(
        player_id=player_id,
        name="Наёмница",
        race=race.value,
        class_=class_.value,
        rarity=int(rarity.value),
        level=start_level,
        exp_current=start_exp,
        perks=perk_ids,
        perk_levels={pid: 1 for pid in perk_ids},
        squad_position=None,
        max_hp=max_hp,
        current_hp=max_hp,
        hp_updated_at=now,
    )
    refresh_unit_power(waifu)
    session.add(waifu)
    await session.flush()
    return waifu


def _parse_guild_assist(state: TavernState) -> tuple[str | None, int | None]:
    """guild_assist_day stores ``YYYY-MM-DD`` or ``YYYY-MM-DD:<waifu_id>``."""
    raw = getattr(state, "guild_assist_day", None)
    if not raw:
        return None, None
    s = str(raw)
    if ":" in s:
        day, _, wid = s.partition(":")
        try:
            return day, int(wid)
        except (TypeError, ValueError):
            return day or None, None
    return s, None


async def set_lineup_slot(
    session: AsyncSession,
    player_id: int,
    *,
    side: str,
    slot: int,
    waifu_id: int | None,
) -> dict:
    side = side.lower().strip()
    if side not in ("atk", "def"):
        return {"error": "invalid_side"}
    try:
        slot_i = int(slot)
    except Exception:
        return {"error": "invalid_slot"}
    if slot_i < 1 or slot_i > 3:
        return {"error": "invalid_slot"}

    field = "atk_slot" if side == "atk" else "def_slot"

    # Clear whoever currently occupies this slot
    rows = (
        await session.execute(select(HiredWaifu).where(HiredWaifu.player_id == player_id))
    ).scalars().all()
    for w in rows:
        if getattr(w, field, None) == slot_i:
            setattr(w, field, None)
            # dual-write: clear legacy squad_position if matched
            if side == "atk" and getattr(w, "squad_position", None) == slot_i:
                w.squad_position = None

    if waifu_id is None:
        await session.flush()
        return {"ok": True, "cleared": True}

    waifu = await session.get(HiredWaifu, int(waifu_id))
    if not waifu or int(waifu.player_id) != int(player_id):
        return {"error": "waifu_not_found"}

    # Guild Assist is Ops-only — never on Arena DEF
    if side == "def":
        state = await get_or_create_tavern_state(session, player_id)
        day, assist_wid = _parse_guild_assist(state)
        if day == _moscow_day_key() and assist_wid and int(assist_wid) == int(waifu_id):
            return {"error": "assist_ops_only", "hint": "Guild Assist нельзя ставить в DEF арены"}

    # Clear this unit's previous slot on same side
    setattr(waifu, field, slot_i)
    if side == "atk":
        waifu.squad_position = slot_i  # dual-write
    await session.flush()
    return {"ok": True, "waifu_id": waifu.id, "side": side, "slot": slot_i}


async def get_lineup(session: AsyncSession, player_id: int) -> dict:
    rows = (
        await session.execute(select(HiredWaifu).where(HiredWaifu.player_id == player_id))
    ).scalars().all()
    atk = [None, None, None]
    dfn = [None, None, None]
    for w in rows:
        a = getattr(w, "atk_slot", None)
        d = getattr(w, "def_slot", None)
        if a and 1 <= int(a) <= 3:
            atk[int(a) - 1] = w.id
        if d and 1 <= int(d) <= 3:
            dfn[int(d) - 1] = w.id
    return {"atk": atk, "def": dfn}


async def fodder_for_stars(
    session: AsyncSession,
    player_id: int,
    *,
    target_id: int,
    fodder_ids: list[int],
) -> dict:
    target = await session.get(HiredWaifu, int(target_id))
    if not target or int(target.player_id) != int(player_id):
        return {"error": "target_not_found"}
    stars = int(getattr(target, "potential_stars", 0) or 0)
    if stars >= 5:
        return {"error": "max_stars"}
    need = fodder_cost_for_next_star(stars)
    unique_ids = []
    seen = set()
    for fid in fodder_ids or []:
        i = int(fid)
        if i in seen:
            continue
        seen.add(i)
        unique_ids.append(i)
    if len(unique_ids) < need:
        return {"error": "not_enough_fodder", "need": need, "have": len(unique_ids)}

    lineup = await get_lineup(session, player_id)
    locked = {int(x) for x in (lineup.get("atk") or []) + (lineup.get("def") or []) if x}

    eaten = 0
    for fid in unique_ids:
        if eaten >= need:
            break
        if int(fid) == int(target_id):
            continue
        fw = await session.get(HiredWaifu, int(fid))
        if not fw or int(fw.player_id) != int(player_id):
            continue
        if getattr(fw, "expedition_id", None):
            continue
        if int(fw.id) in locked:
            continue
        fodder_stars = int(getattr(fw, "potential_stars", 0) or 0)
        if fodder_stars >= stars + 1:
            continue
        await session.delete(fw)
        eaten += 1
    if eaten < need:
        return {"error": "not_enough_valid_fodder", "need": need, "eaten": eaten}
    target.potential_stars = stars + 1
    refresh_unit_power(target)
    await session.flush()
    return {
        "ok": True,
        "potential_stars": target.potential_stars,
        "fodder_used": eaten,
        "need": need,
        "perk_level_cap": perk_level_cap(target.potential_stars),
    }


async def convert_to_manual(
    session: AsyncSession,
    player_id: int,
    waifu_id: int,
) -> dict:
    state = await get_or_create_tavern_state(session, player_id)
    waifu = await session.get(HiredWaifu, int(waifu_id))
    if not waifu or int(waifu.player_id) != int(player_id):
        return {"error": "waifu_not_found"}
    if getattr(waifu, "expedition_id", None):
        return {"error": "waifu_busy"}
    perks = migrate_perk_list(list(waifu.perks or []))
    ptype = "ATK"
    if perks:
        perk = PERK_BY_ID.get(perks[0])
        if perk:
            ptype = perk.perk_type
    manuals = add_manual(getattr(state, "drill_manuals", None), ptype, tier=2, amount=1)
    state.drill_manuals = manuals
    await session.delete(waifu)
    await session.flush()
    return {"ok": True, "manual_type": ptype, "tier": 2, "manuals": manuals}


async def apply_manual_to_perk(
    session: AsyncSession,
    player_id: int,
    *,
    waifu_id: int,
    perk_id: str,
    tier: int = 2,
) -> dict:
    state = await get_or_create_tavern_state(session, player_id)
    waifu = await session.get(HiredWaifu, int(waifu_id))
    if not waifu or int(waifu.player_id) != int(player_id):
        return {"error": "waifu_not_found"}
    perk = PERK_BY_ID.get(perk_id)
    if not perk:
        return {"error": "perk_not_found"}
    perks = migrate_perk_list(list(waifu.perks or []))
    if perk_id not in perks:
        return {"error": "perk_not_on_unit"}
    t = max(1, min(3, int(tier or 2)))
    stars = int(getattr(waifu, "potential_stars", 0) or 0)
    levels = dict(getattr(waifu, "perk_levels", None) or {})
    cur = int(levels.get(perk_id, 1) or 1)
    hard = perk_level_cap(stars)
    soft = perk_soft_cap(stars, t)
    if cur >= hard:
        return {"error": "perk_level_cap", "cap": hard}
    if cur >= soft:
        return {"error": "tier_soft_cap", "tier": t, "soft_cap": soft, "hard_cap": hard, "need_tier": min(3, t + 1) if soft < hard else None}
    manuals, err = consume_manual(getattr(state, "drill_manuals", None), perk.perk_type, t, 1)
    if err:
        return {"error": "no_manual", "type": perk.perk_type, "tier": t}
    levels[perk_id] = cur + 1
    waifu.perk_levels = levels
    state.drill_manuals = manuals
    refresh_unit_power(waifu)
    await session.flush()
    return {"ok": True, "perk_id": perk_id, "level": levels[perk_id], "tier": t, "soft_cap": soft, "hard_cap": hard}


# --- Ops board ---

_REWARD_BIASES = ("merc_coins", "merc_dust", "merc_exp", "contracts", "tickets", "mixed")


async def get_or_create_ops_board(session: AsyncSession, player_id: int) -> MercOpsBoard:
    wk = _week_key()
    row = (
        await session.execute(
            select(MercOpsBoard).where(
                MercOpsBoard.player_id == player_id,
                MercOpsBoard.week_key == wk,
            )
        )
    ).scalar_one_or_none()
    if row:
        # Backfill art_key on legacy weekly boards
        contracts = list(row.contracts_json or [])
        changed = False
        for c in contracts:
            if isinstance(c, dict) and not c.get("art_key"):
                bias = str(c.get("reward_bias") or "mixed")
                c["art_key"] = f"ops_bias_{bias}"
                changed = True
        if changed:
            row.contracts_json = contracts
            await session.flush()
        return row
    rng = random.Random(f"{player_id}-{wk}")
    contracts = []
    for i in range(6):
        star = 1 + (i % 5)
        tags = rng.sample(list(THREAT_TAGS), k=min(3, 2 + (star // 2)))
        arch_names = ["Берсерк", "Цитадель", "Тактик", "Медик", "Дуэлянт", "Паладин"]
        bias = _REWARD_BIASES[i % len(_REWARD_BIASES)]
        contracts.append(
            {
                "id": f"{wk}-{i+1}",
                "star": star,
                "duration_minutes": 60 + star * 30,
                "threat_tags": tags,
                "threat_labels": [THREAT_TAG_LABELS_RU.get(t, t) for t in tags],
                "recommended_archetype": rng.choice(arch_names),
                "reward_bias": bias,
                "art_key": f"ops_bias_{bias}",
                "depth_tier": star,  # alias for legacy start
            }
        )
    row = MercOpsBoard(
        player_id=player_id,
        week_key=wk,
        contracts_json=contracts,
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


# --- Arena ---

async def ensure_arena_tickets(state: TavernState) -> None:
    day = _moscow_day_key()
    if getattr(state, "arena_tickets_day", None) != day:
        state.arena_tickets_day = day
        state.arena_tickets = ARENA_TICKETS_DAILY
        state.arena_attacks_today = 0


async def arena_status(session: AsyncSession, player_id: int) -> dict:
    player = await session.get(Player, player_id)
    state = await get_or_create_tavern_state(session, player_id)
    await ensure_arena_tickets(state)
    unlocked = int(getattr(player, "max_act", 1) or 1) >= ARENA_UNLOCK_ACT if player else False
    lineup = await get_lineup(session, player_id)
    return {
        **pity_status(state),
        "unlocked": unlocked,
        "unlock_act": ARENA_UNLOCK_ACT,
        "lineup": lineup,
        "tickets_daily": ARENA_TICKETS_DAILY,
    }


def _bot_defense(rating: int) -> list:
    """Synthetic defenders scaled by rating."""
    from waifu_bot.game.merc_arena import ArenaFighter

    base = max(40, rating // 12)
    return [
        ArenaFighter("Страж-бот", base + 10, ["ironwall_u", "fortify_c"], "Ward", "bulwark"),
        ArenaFighter("Клинок-бот", base + 15, ["cleave_u", "first_strike_c"], "Assault", "vanguard"),
        ArenaFighter("Канал-бот", base + 5, ["mend_u", "mark_u"], "Tactics", "warden"),
    ]


def _arena_opponent_payload(
    player: Player | None,
    tavern: TavernState | None,
    *,
    bot: bool = False,
    fallback_player_id: int | None = None,
) -> dict:
    pid = None
    if bot:
        pid = None
    elif tavern is not None:
        pid = int(tavern.player_id)
    elif player is not None:
        pid = int(player.id)
    elif fallback_player_id is not None:
        pid = int(fallback_player_id)
    username = (getattr(player, "username", None) or None) if player else None
    first = (getattr(player, "first_name", None) or "").strip() if player else ""
    display = (
        first
        or (f"@{username}" if username else None)
        or (f"Игрок {pid}" if pid else "Бот")
    )
    rating = int(getattr(tavern, "arena_rating", 1000) or 1000) if tavern else 1000
    return {
        "player_id": pid,
        "rating": rating,
        "bot": bot,
        "username": username,
        "display_name": display if not bot else "Бот",
    }


async def arena_opponents(
    session: AsyncSession,
    player_id: int,
    *,
    q: str | None = None,
) -> list[dict]:
    state = await get_or_create_tavern_state(session, player_id)
    my_r = int(getattr(state, "arena_rating", 1000) or 1000)
    query = (q or "").strip().lstrip("@")
    if query:
        pattern = f"%{query}%"
        # Global player search (not guild / not tavern-only)
        rows = (
            await session.execute(
                select(Player, TavernState)
                .outerjoin(TavernState, TavernState.player_id == Player.id)
                .where(Player.id != player_id)
                .where(
                    or_(
                        Player.username.ilike(pattern),
                        Player.first_name.ilike(pattern),
                    )
                )
                .order_by(func.abs(func.coalesce(TavernState.arena_rating, 1000) - my_r))
                .limit(10)
            )
        ).all()
        return [_arena_opponent_payload(p, t) for p, t in rows]

    # Nearby ratings (suggested 3) + bots to fill
    others = (
        await session.execute(
            select(TavernState, Player)
            .outerjoin(Player, Player.id == TavernState.player_id)
            .where(TavernState.player_id != player_id)
            .order_by(func.abs(TavernState.arena_rating - my_r))
            .limit(5)
        )
    ).all()
    out = []
    for t, p in others[:3]:
        out.append(_arena_opponent_payload(p, t))
    while len(out) < 3:
        out.append(
            {
                "player_id": None,
                "rating": my_r + random.randint(-40, 40),
                "bot": True,
                "username": None,
                "display_name": "Бот",
            }
        )
    return out


async def arena_attack(
    session: AsyncSession,
    player_id: int,
    *,
    defender_id: int | None = None,
    bot: bool = False,
) -> dict:
    player = await session.get(Player, player_id)
    if not player or int(getattr(player, "max_act", 1) or 1) < ARENA_UNLOCK_ACT:
        return {"error": "arena_locked"}
    state = await get_or_create_tavern_state(session, player_id)
    await ensure_arena_tickets(state)
    if int(state.arena_tickets or 0) < 1:
        return {"error": "no_tickets"}

    lineup = await get_lineup(session, player_id)
    atk_ids = [x for x in lineup["atk"] if x]
    if len(atk_ids) < 1:
        return {"error": "no_atk_lineup"}
    atk_units = []
    for wid in atk_ids:
        w = await session.get(HiredWaifu, int(wid))
        if w:
            refresh_unit_power(w)
            atk_units.append(w)
    attackers = [fighter_from_unit(u) for u in atk_units]

    defenders = []
    if bot or not defender_id:
        defenders = _bot_defense(int(state.arena_rating or 1000))
        defender_id = None
    else:
        d_line = await get_lineup(session, int(defender_id))
        for wid in [x for x in d_line["def"] if x] or [x for x in d_line["atk"] if x]:
            w = await session.get(HiredWaifu, int(wid))
            if w:
                refresh_unit_power(w)
                defenders.append(fighter_from_unit(w))
        if not defenders:
            defenders = _bot_defense(int(state.arena_rating or 1000))

    seed = f"{player_id}-{defender_id}-{datetime.now(timezone.utc).timestamp()}"
    result = simulate_3v3(attackers, defenders, match_seed=seed)
    win = result["winner"] == "attacker"
    delta = 18 if win else -12
    state.arena_rating = max(0, int(state.arena_rating or 1000) + delta)
    state.arena_tickets = int(state.arena_tickets or 0) - 1
    state.arena_attacks_today = int(state.arena_attacks_today or 0) + 1
    if win:
        state.merc_coins = int(state.merc_coins or 0) + 25
        # Rare T3 doctrine drip (thin balance ok)
        if random.random() < 0.08:
            ptype = random.choice(["ATK", "DEF", "SUP"])
            state.drill_manuals = add_manual(getattr(state, "drill_manuals", None), ptype, tier=3, amount=1)
        elif random.random() < 0.35:
            ptype = random.choice(["ATK", "DEF", "SUP"])
            state.drill_manuals = add_manual(getattr(state, "drill_manuals", None), ptype, tier=1, amount=1)
    match = MercArenaMatch(
        attacker_id=player_id,
        defender_id=defender_id,
        winner=result["winner"],
        rating_delta=delta,
        attacker_rating_after=int(state.arena_rating),
        log_json=result["log"],
        seed=seed[:64],
        created_at=datetime.now(timezone.utc),
    )
    session.add(match)
    await session.flush()
    return {
        "ok": True,
        "winner": result["winner"],
        "rating_delta": delta,
        "rating": int(state.arena_rating),
        "tickets": int(state.arena_tickets),
        "log": result["log"],
        "match_id": match.id,
        "coins_gained": 25 if win else 0,
    }


# --- Exchange ---

EXCHANGE_CATALOG = [
    {
        "id": "contract",
        "name": "Контракт найма",
        "icon": "📜",
        "description": "Оплачивает один найм в таверне вместо золота. Удобно копить с операций.",
        "cost_coins": 80,
        "gives": {"merc_contracts": 1},
    },
    {
        "id": "dust_pack",
        "name": "Пыль ×20",
        "icon": "✨",
        "description": "+20 пыли. Нужна для прокачки потенциала ★ наёмниц (fodder / sink).",
        "cost_coins": 40,
        "gives": {"merc_dust": 20},
    },
    {
        "id": "ticket",
        "name": "Тикет арены",
        "icon": "🎟",
        "description": "+1 тикет арены. Тратится на атаку соперника в async-арене 3v3.",
        "cost_coins": 50,
        "gives": {"arena_tickets": 1},
    },
    {
        "id": "notes_atk",
        "name": "Заметки ATK",
        "icon": "📘",
        "description": "Учебник T1 (ATK). Повышает уровень ATK-перка в карточке наёмницы.",
        "cost_coins": 25,
        "gives": {"manual": "ATK", "tier": 1},
    },
    {
        "id": "notes_def",
        "name": "Заметки DEF",
        "icon": "📗",
        "description": "Учебник T1 (DEF). Повышает уровень DEF-перка в карточке наёмницы.",
        "cost_coins": 25,
        "gives": {"manual": "DEF", "tier": 1},
    },
    {
        "id": "notes_sup",
        "name": "Заметки SUP",
        "icon": "📙",
        "description": "Учебник T1 (SUP). Повышает уровень SUP-перка в карточке наёмницы.",
        "cost_coins": 25,
        "gives": {"manual": "SUP", "tier": 1},
    },
    {
        "id": "manual_atk",
        "name": "Учебник ATK",
        "icon": "📖",
        "description": "Учебник T2 (ATK). Сильнее заметок; нужен для средних уровней перков.",
        "cost_coins": 60,
        "gives": {"manual": "ATK", "tier": 2},
    },
    {
        "id": "manual_def",
        "name": "Учебник DEF",
        "icon": "📖",
        "description": "Учебник T2 (DEF). Сильнее заметок; нужен для средних уровней перков.",
        "cost_coins": 60,
        "gives": {"manual": "DEF", "tier": 2},
    },
    {
        "id": "manual_sup",
        "name": "Учебник SUP",
        "icon": "📖",
        "description": "Учебник T2 (SUP). Сильнее заметок; нужен для средних уровней перков.",
        "cost_coins": 60,
        "gives": {"manual": "SUP", "tier": 2},
    },
    {
        "id": "doctrine_atk",
        "name": "Доктрина ATK",
        "icon": "📕",
        "description": "Учебник T3 (ATK). Редкий расходник для высоких уровней ATK-перков.",
        "cost_coins": 140,
        "gives": {"manual": "ATK", "tier": 3},
    },
    {
        "id": "doctrine_def",
        "name": "Доктрина DEF",
        "icon": "📕",
        "description": "Учебник T3 (DEF). Редкий расходник для высоких уровней DEF-перков.",
        "cost_coins": 140,
        "gives": {"manual": "DEF", "tier": 3},
    },
    {
        "id": "doctrine_sup",
        "name": "Доктрина SUP",
        "icon": "📕",
        "description": "Учебник T3 (SUP). Редкий расходник для высоких уровней SUP-перков.",
        "cost_coins": 140,
        "gives": {"manual": "SUP", "tier": 3},
    },
    {
        "id": "gear_box_t1",
        "name": "Ящик снаряжения T1",
        "icon": "📦",
        "description": "Случайный предмет экипа T1 в сумку. Надевается на weapon / charm / relic.",
        "cost_coins": 50,
        "gives": {"loot_box": "gear", "tier": 1},
    },
    {
        "id": "gear_box_t2",
        "name": "Ящик снаряжения T2",
        "icon": "📦",
        "description": "Случайный предмет экипа T2 в сумку. Сильнее T1 по score/редкости.",
        "cost_coins": 100,
        "gives": {"loot_box": "gear", "tier": 2},
    },
    {
        "id": "gear_box_t3",
        "name": "Ящик снаряжения T3",
        "icon": "🎁",
        "description": "Случайный предмет экипа T3 в сумку. Топ-тир для CR и синергий.",
        "cost_coins": 180,
        "gives": {"loot_box": "gear", "tier": 3},
    },
]


async def exchange_buy(session: AsyncSession, player_id: int, item_id: str) -> dict:
    state = await get_or_create_tavern_state(session, player_id)
    item = next((x for x in EXCHANGE_CATALOG if x["id"] == item_id), None)
    if not item:
        return {"error": "item_not_found"}
    cost = int(item["cost_coins"])
    if int(state.merc_coins or 0) < cost:
        return {"error": "insufficient_coins", "need": cost}
    state.merc_coins = int(state.merc_coins or 0) - cost
    gives = item["gives"]
    if "merc_contracts" in gives:
        state.merc_contracts = int(state.merc_contracts or 0) + int(gives["merc_contracts"])
    if "merc_dust" in gives:
        state.merc_dust = int(state.merc_dust or 0) + int(gives["merc_dust"])
    if "arena_tickets" in gives:
        await ensure_arena_tickets(state)
        state.arena_tickets = int(state.arena_tickets or 0) + int(gives["arena_tickets"])
    if "manual" in gives:
        manuals = add_manual(
            getattr(state, "drill_manuals", None),
            gives["manual"],
            tier=int(gives.get("tier") or 2),
            amount=1,
        )
        state.drill_manuals = manuals
    rolled = None
    if gives.get("loot_box") == "gear":
        from waifu_bot.game.merc_gear import roll_merc_gear

        rolled = roll_merc_gear(int(gives.get("tier") or 1))
        bag = list(getattr(state, "merc_gear_bag", None) or [])
        bag.append(rolled)
        state.merc_gear_bag = bag
    await session.flush()
    out = {"ok": True, "wallet": pity_status(state)}
    if rolled:
        out["item"] = rolled
        out["merc_gear_bag"] = list(getattr(state, "merc_gear_bag", None) or [])
    return out


async def codex_list(session: AsyncSession, player_id: int) -> list[dict]:
    state = await get_or_create_tavern_state(session, player_id)
    unlocked = set(getattr(state, "codex_legendary_ids", None) or [])
    return [template_public(t, unlocked=(t.id in unlocked)) for t in LEGENDARY_TEMPLATES]


def perks_catalog() -> list[dict]:
    return catalog_public()


async def grant_ops_rewards(
    session: AsyncSession,
    player_id: int,
    *,
    outcome: str = "success",
    star: int = 1,
    reward_bias: str | None = "mixed",
) -> dict:
    """Primary merc rewards on ops claim (call alongside legacy gold path)."""
    state = await get_or_create_tavern_state(session, player_id)
    mult = {"success": 1.0, "partial_success": 0.7, "partial": 0.7, "failure": 0.4}.get(
        str(outcome), 0.7
    )
    star_n = max(1, min(5, int(star or 1)))
    bias = str(reward_bias or "mixed").strip().lower()
    if bias not in _REWARD_BIASES:
        bias = "mixed"
    base_coins = int((20 + star_n * 15) * mult)
    base_dust = int((5 + star_n * 3) * mult)
    success = str(outcome) == "success"
    partial = str(outcome) in ("partial_success", "partial")

    coins = 0
    dust = 0
    tickets = 0
    contracts = 0
    if bias == "merc_coins":
        coins = int(base_coins * 1.55)
        dust = int(base_dust * 0.25)
    elif bias == "merc_dust":
        coins = int(base_coins * 0.25)
        dust = int(base_dust * 1.8)
    elif bias == "tickets":
        coins = int(base_coins * 0.35)
        dust = int(base_dust * 0.35)
        if success:
            tickets = 1 + (1 if star_n >= 3 else 0)
        elif partial and star_n >= 2:
            tickets = 1
    elif bias == "contracts":
        coins = int(base_coins * 0.35)
        dust = int(base_dust * 0.35)
        if success:
            contracts = 1 + (1 if star_n >= 4 else 0)
        elif partial and star_n >= 3:
            contracts = 1
    elif bias == "merc_exp":
        coins = int(base_coins * 0.3)
        dust = int(base_dust * 0.3)
    else:
        # mixed
        coins = base_coins
        dust = base_dust
        tickets = 1 if success and star_n >= 3 else 0
        contracts = 1 if success and star_n >= 4 else 0

    state.merc_coins = int(state.merc_coins or 0) + coins
    state.merc_dust = int(state.merc_dust or 0) + dust
    if tickets:
        await ensure_arena_tickets(state)
        state.arena_tickets = int(state.arena_tickets or 0) + tickets
    if contracts:
        state.merc_contracts = int(state.merc_contracts or 0) + contracts
    # Early T1 notes drip from ops
    notes = 0
    if (success or partial) and star_n >= 1:
        notes = 1 + (1 if star_n >= 3 and success else 0)
        ptype = random.choice(["ATK", "DEF", "SUP"])
        state.drill_manuals = add_manual(getattr(state, "drill_manuals", None), ptype, tier=1, amount=notes)
    await session.flush()
    return {
        "merc_coins": coins,
        "merc_dust": dust,
        "arena_tickets": tickets,
        "merc_contracts": contracts,
        "t1_notes": notes,
        "reward_bias": bias,
    }

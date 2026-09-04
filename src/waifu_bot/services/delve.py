"""Delve column: O(1) gold/XP tap + O(1) theater frame. GET never calls a language model."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.delve_catalog import (
    ALPHA,
    CEILING_TAIL_EXP,
    CEILING_TAIL_HOURS,
    CEILING_TAIL_K,
    CLOAK_COLORS,
    COPY,
    D0,
    DEPTH_EXP,
    GOLD_OF_CHAT_CAP_DEFAULT,
    T0_SEC,
    T_UP_SEC,
    NODE_BOSS,
    NODE_LABEL_RU,
    fog_spine_type,
    PALETTES,
    PALETTE_IDS,
    REFORM_CD_DAYS,
    SHAFT_BIOMES,
    SPRITE_CAP,
    STANCES,
    TEMPERS,
    UNLOCK_OV_LEVEL,
    XP_OF_SOLO_DAY_DEFAULT,
    branch_sleeves,
    days_in_party,
    enforce_squad_names,
    floor_pct,
    frame_kicker,
    gold_cap_day,
    gold_rate_per_sec,
    hours_in_column,
    instinct_sleeve,
    is_city_depth,
    journal_stamps_for_record,
    merge_journal,
    msk_day_start,
    msk_today,
    phrase_for,
    pick_companion_name,
    portrait_relpath,
    reform_ready,
    sawtooth,
    seed_palette_id,
    shaft_art_for_depth,
    shaft_band_depths,
    spine_type,
    split_weighted,
    template_portrait_url,
    title_for_record,
    title_id_for_record,
    viewport_depths,
    walk_capped_grant,
    xp_cap_day,
    xp_rate_per_sec,
)
from waifu_bot.paths import static_game_directory
from waifu_bot.game.delve_pq import xp_to_next
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.wallet import add_gold

logger = logging.getLogger(__name__)

VALID_STANCES = frozenset(STANCES)
VALID_TEMPERS = frozenset(TEMPERS)


class DelveError(Exception):
    def __init__(self, code: str, http_status: int = 400):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def loyalty_faucet_mult(loyalties: Sequence[int]) -> float:
    """Empty table and all-50 stay 1.0. No per-head party size bonus."""
    values = [max(0, min(100, int(v))) for v in loyalties]
    if not values:
        return 1.0
    extra = 0.0
    any_max = False
    for loyalty in values:
        extra += max(0.0, (loyalty - 50) / 50.0 * 0.10)
        if loyalty == 100:
            any_max = True
    if any_max:
        extra += 0.05
    return max(1.0, min(1.40, 1.0 + extra))


def catch_up_midday_cap_increase(
    minted: int,
    today_after: int,
    *,
    last: datetime,
    now: datetime,
    cap: int,
    rate: float,
    granted_before: int,
) -> tuple[int, int]:
    """Mint the snap gap when cap/rate rose after gold already accrued today."""
    if granted_before <= 0 or cap <= 0 or rate <= 0:
        return minted, today_after
    last_a = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
    now_a = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if msk_today(last_a) != msk_today(now_a):
        return minted, today_after
    start = msk_day_start(now_a)
    sec_last = max(0.0, (last_a - start).total_seconds())
    owed_at_last = min(int(cap), int(rate * sec_last))
    extra = max(0, owed_at_last - int(granted_before))
    if extra <= 0:
        return minted, today_after
    return int(minted) + extra, int(today_after)


def resolve_companion_image_url(row: m.DelveCompanion) -> str:
    """Always a public /static/...webp. Never an authenticated API path."""
    stance = str(row.stance or "guide")
    pid = int(row.player_id)
    slot = int(row.slot)
    game = static_game_directory()
    static_root = game.parent
    dest = game / "delve" / "portraits" / f"{pid}_{slot}.webp"
    path = (row.image_path or "").strip().lstrip("/")
    if path:
        full = static_root / path
        if full.is_file():
            if "chronicle" in path.split("/") and not dest.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(full.read_bytes())
                return f"/static/{portrait_relpath(pid, slot)}"
            return f"/static/{path}"
    if dest.is_file():
        return f"/static/{portrait_relpath(pid, slot)}"
    old = game / "chronicle" / "portraits" / f"{pid}_{slot}.webp"
    if old.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(old.read_bytes())
        return f"/static/{portrait_relpath(pid, slot)}"
    return template_portrait_url(stance)


def _int_attr(obj: Any, name: str, default: int) -> int:
    try:
        return int(getattr(obj, name, default) or default)
    except (TypeError, ValueError):
        return int(default)


def companion_out(
    row: m.DelveCompanion,
    *,
    now: datetime | None = None,
    pq: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stance = str(row.stance or "guide")
    image_url = resolve_companion_image_url(row)
    joined = getattr(row, "joined_at", None) or getattr(row, "created_at", None)
    out = {
        "slot": int(row.slot),
        "name": row.name,
        "stance": stance,
        "stance_label": STANCES.get(stance, {}).get("label", stance),
        "temper": row.temper,
        "temper_label": TEMPERS.get(str(row.temper), {}).get("label", row.temper),
        "cloak_color": row.cloak_color,
        "image_url": image_url,
        "portrait_url": image_url,
        "gold_earned": int(getattr(row, "gold_earned", 0) or 0),
        "xp_earned": int(getattr(row, "xp_earned", 0) or 0),
        "level": _int_attr(row, "level", 1),
        "power": _int_attr(row, "power", 1),
        "gold_wallet": _int_attr(row, "gold_wallet", 0),
        "xp_unspent": _int_attr(row, "xp_unspent", 0),
        "xp_to_next": xp_to_next(_int_attr(row, "level", 1)),
        "hp_current": _int_attr(row, "hp_current", 48),
        "hp_max": _int_attr(row, "hp_max", 48),
        "days": days_in_party(joined, now or _now()),
        "joined_at": joined.isoformat() if joined is not None else None,
    }
    if pq:
        out.update(pq)
    return out


def attribute_party_grant(
    companions: list[m.DelveCompanion],
    gold: int,
    xp: int,
    cards: list[m.CompanionCard] | None = None,
) -> None:
    n = len(companions)
    if n <= 0:
        return
    card_by_slot = {int(c.slot): c for c in (cards or []) if c and c.slot}
    weights: list[int] = []
    paired: list[m.CompanionCard | None] = []
    for row in companions:
        card = card_by_slot.get(int(row.slot))
        paired.append(card)
        if card is not None:
            look = card.look_card or {}
            try:
                loyalty = int(look.get("loyalty", 50))
            except (TypeError, ValueError):
                loyalty = 50
            weights.append(max(1, max(0, min(100, loyalty))))
        else:
            weights.append(50)
    gold_parts = split_weighted(int(gold or 0), weights)
    xp_parts = split_weighted(int(xp or 0), weights)
    for row, card, g, x in zip(companions, paired, gold_parts, xp_parts):
        row.gold_earned = int(getattr(row, "gold_earned", 0) or 0) + int(g)
        row.xp_earned = int(getattr(row, "xp_earned", 0) or 0) + int(x)
        if card is not None:
            card.gold_earned = int(card.gold_earned or 0) + int(g)
            card.xp_earned = int(card.xp_earned or 0) + int(x)


async def get_state(session: AsyncSession, player_id: int) -> m.DelveState | None:
    return await session.get(m.DelveState, int(player_id))


async def get_state_for_update(session: AsyncSession, player_id: int) -> m.DelveState | None:
    return (
        await session.execute(
            select(m.DelveState)
            .where(m.DelveState.player_id == int(player_id))
            .with_for_update()
        )
    ).scalar_one_or_none()


async def list_companions(session: AsyncSession, player_id: int) -> list[m.DelveCompanion]:
    rows = (
        await session.execute(
            select(m.DelveCompanion)
            .where(m.DelveCompanion.player_id == int(player_id))
            .order_by(m.DelveCompanion.slot.asc())
        )
    ).scalars().all()
    return list(rows)


async def get_or_create_state(session: AsyncSession, player_id: int) -> m.DelveState:
    row = await get_state(session, player_id)
    if row:
        return row
    row = m.DelveState(player_id=int(player_id), gold_granted_total=0, xp_granted_total=0, sprite_count=0)
    session.add(row)
    await session.flush()
    return row


async def _caps(session: AsyncSession, ov_level: int) -> tuple[int, int]:
    cfg = await get_game_config_map(session)
    chat_cap = cfg_int(cfg, "chat_reward.daily_points_cap", 600) * cfg_int(
        cfg, "chat_reward.gold_per_point", 2
    )
    gold_frac = cfg_float(cfg, "delve.gold_of_chat_cap", GOLD_OF_CHAT_CAP_DEFAULT)
    xp_frac = cfg_float(cfg, "delve.xp_of_solo_day", XP_OF_SOLO_DAY_DEFAULT)
    g = gold_cap_day(gold_of_chat_cap=gold_frac, chat_gold_cap=chat_cap)
    x = xp_cap_day(ov_level, frac=xp_frac)
    return g, x


async def is_unlocked(session: AsyncSession, player_id: int, mw: m.MainWaifu | None) -> bool:
    if mw is not None and int(mw.level or 1) >= UNLOCK_OV_LEVEL:
        return True
    n_progress = await session.scalar(
        select(func.count())
        .select_from(m.DungeonProgress)
        .where(
            m.DungeonProgress.player_id == int(player_id),
            m.DungeonProgress.is_completed.is_(True),
        )
    )
    if int(n_progress or 0) > 0:
        return True
    n_runs = await session.scalar(
        select(func.count())
        .select_from(m.DungeonRun)
        .where(m.DungeonRun.player_id == int(player_id), m.DungeonRun.status == "completed")
    )
    return int(n_runs or 0) > 0


async def grant_tap(
    session: AsyncSession,
    player: m.Player,
    mw: m.MainWaifu | None,
    state: m.DelveState,
    *,
    now: datetime | None = None,
    loyalty_mult: float = 1.0,
) -> tuple[int, int]:
    """Idempotent gold+XP. Caller must hold a row lock on `state`."""
    if state.t_origin is None:
        return 0, 0
    now = now or _now()
    last = state.last_grant_ts or state.t_origin
    ov_level = int(mw.level or 1) if mw is not None else 1
    cap_g, cap_x = await _caps(session, ov_level)
    mult = max(1.0, min(1.40, float(loyalty_mult or 1.0)))
    cap_g = int(cap_g * mult)
    cap_x = int(cap_x * mult)
    granted_g_before = int(state.gold_granted_today or 0)
    granted_x_before = int(state.xp_granted_today or 0)
    gold, day_g, today_g = walk_capped_grant(
        last,
        now,
        rate=gold_rate_per_sec(cap_g),
        cap=cap_g,
        day_key=state.grant_day_msk,
        granted_today=granted_g_before,
    )
    xp, day_x, today_x = walk_capped_grant(
        last,
        now,
        rate=xp_rate_per_sec(cap_x),
        cap=cap_x,
        day_key=state.grant_day_msk,
        granted_today=granted_x_before,
    )
    gold, today_g = catch_up_midday_cap_increase(
        gold,
        today_g,
        last=last,
        now=now,
        cap=cap_g,
        rate=gold_rate_per_sec(cap_g),
        granted_before=granted_g_before,
    )
    xp, today_x = catch_up_midday_cap_increase(
        xp,
        today_x,
        last=last,
        now=now,
        cap=cap_x,
        rate=xp_rate_per_sec(cap_x),
        granted_before=granted_x_before,
    )
    day_key = day_g or day_x or msk_today(now)
    if gold > 0:
        ok = await add_gold(session, player, gold, source="delve", ref_type="tap", ref_id=int(state.gold_granted_total or 0) + gold)
        if not ok:
            gold = 0
        else:
            state.gold_granted_total = int(state.gold_granted_total or 0) + gold
    if xp > 0 and mw is not None:
        mw.experience = int(getattr(mw, "experience", 0) or 0) + int(xp)
        from waifu_bot.services.combat import apply_main_waifu_levelups

        await apply_main_waifu_levelups(session, mw)
        state.xp_granted_total = int(state.xp_granted_total or 0) + xp
    elif xp > 0 and mw is None:
        xp = 0
        today_x = int(state.xp_granted_today or 0)
    state.grant_day_msk = day_key
    state.gold_granted_today = int(today_g)
    state.xp_granted_today = int(today_x)
    state.last_grant_ts = now
    return gold, xp


def _portrait_path_for_slot(
    player_id: int, slot: int, existing: m.DelveCompanion | None, *, keep_file: bool
) -> str | None:
    dest = static_game_directory() / "delve" / "portraits" / f"{int(player_id)}_{int(slot)}.webp"
    if keep_file:
        if dest.is_file():
            return portrait_relpath(int(player_id), int(slot))
        if existing is not None and str(existing.image_path or "").strip():
            return str(existing.image_path)
        old = static_game_directory() / "chronicle" / "portraits" / f"{int(player_id)}_{int(slot)}.webp"
        if old.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(old.read_bytes())
            return portrait_relpath(int(player_id), int(slot))
    return None


def _apply_theater(state: m.DelveState, frame: dict[str, Any], companions: list[m.DelveCompanion]) -> None:
    rec = max(int(state.pb_depth or 0), int(frame["implied_record"]))
    state.pb_depth = rec
    state.title_id = title_id_for_record(rec)
    instinct = str(frame.get("instinct_palette") or "")
    on_branch = bool(frame.get("on_branch"))
    if on_branch:
        if not state.pending_tint and instinct in PALETTE_IDS:
            state.pending_tint = instinct
    else:
        if state.pending_tint in PALETTE_IDS:
            state.committed_palette = state.pending_tint
        state.pending_tint = None
    palette = (
        state.committed_palette
        if state.committed_palette in PALETTE_IDS
        else seed_palette_id(int(state.spine_seed or 0))
    )
    state.committed_palette = palette
    sryv = frame["state"] in ("ASCENDING", "SURFACE_REST") and int(math_floor_ceil(frame["d_ceiling"])) % 10 == 0
    incoming = journal_stamps_for_record(rec, palette, sryv=sryv)
    incoming.append({"kind": "palette", "d": 0, "palette": palette})
    state.journal_json = merge_journal(state.journal_json, incoming)
    _ = companions


def math_floor_ceil(ceil: float) -> int:
    import math

    return int(math.floor(ceil))


async def sync_hidden_counters(session: AsyncSession, player_id: int, state: m.DelveState, now: datetime) -> None:
    if state.t_origin is None:
        return
    try:
        from waifu_bot.services.hidden_skills import set_skill_counter

        hours = int(hours_in_column(state.t_origin, now))
        await set_skill_counter(session, int(player_id), "expedition_veteran", hours, silent=True)
        await set_skill_counter(session, int(player_id), "mythweaver", int(state.pb_depth or 0), silent=True)
        await set_skill_counter(session, int(player_id), "loyal_commander", int(state.pb_depth or 0), silent=True)
    except Exception:
        logger.debug("delve hidden counters failed player_id=%s", player_id, exc_info=True)


def build_frame(
    state: m.DelveState,
    companions: list[m.DelveCompanion],
    *,
    now: datetime,
    ov_level: int,
    d_max: int | None = None,
    pq_layer: int = 1,
    t_eff: int = 30,
    pq_event: dict[str, Any] | None = None,
    pq_last_d: int | None = None,
) -> dict[str, Any]:
    run_origin = getattr(state, "run_origin", None)
    origin = run_origin if isinstance(run_origin, datetime) else None
    origin = origin or state.t_origin or now
    if int(pq_layer) >= 2 and d_max is not None:
        from waifu_bot.game.delve_pq_layer import walk_frame

        walked = int(state.pq_last_d if pq_last_d is None else pq_last_d)
        tooth = walk_frame(
            last_d=walked,
            d_fair=int(d_max),
            t_eff=int(t_eff or 30),
            pb_depth=int(state.pb_depth or 0),
        )
    else:
        tooth = sawtooth(t_origin=origin, now=now, ov_level=ov_level, d_max=d_max)
    d = int(tooth["d"])
    ceil = float(tooth["d_ceiling"])
    pq_seed = None
    pq_wipe = 0
    if int(pq_layer) >= 2:
        pq_seed = int(getattr(state, "pq_seed", 0) or getattr(state, "spine_seed", 0) or 0)
        pq_wipe = int(getattr(state, "wipe_count", 0) or 0)
    node = spine_type(d, ceil, seed=pq_seed, wipe_count=pq_wipe)
    palette_id = state.committed_palette if state.committed_palette in PALETTE_IDS else seed_palette_id(int(state.spine_seed or 0))
    tempers = [str(c.temper) for c in companions]
    instinct = instinct_sleeve(tempers)
    left, right = branch_sleeves(palette_id, int(state.spine_seed or 0), d)
    sleeves = [left, right]
    instinct_id = sleeves[instinct]
    face = companions[0].name if companions else "Она"
    if pq_event and pq_event.get("phrase"):
        phrase = str(pq_event.get("phrase") or "")
    else:
        phrase = phrase_for(node=node, palette_id=palette_id, name=face, spine_seed=int(state.spine_seed or 0), d=d)
    on_branch = node == "BRANCH" and tooth["state"] == "DESCENDING"
    depths = viewport_depths(d)
    walked = int(pq_last_d if pq_last_d is not None else getattr(state, "pq_last_d", 0) or d)
    if int(pq_layer) >= 2:
        nodes = [
            {"d": n, "type": fog_spine_type(n, ceil, last_d=walked, seed=pq_seed, wipe_count=pq_wipe)}
            for n in depths
        ]
        band_nodes = [
            {"d": n, "type": fog_spine_type(n, ceil, last_d=walked, seed=pq_seed, wipe_count=pq_wipe)}
            for n in shaft_band_depths(d)
        ]
    else:
        nodes = [{"d": n, "type": spine_type(n, ceil)} for n in depths]
        band_nodes = [{"d": n, "type": spine_type(n, ceil)} for n in shaft_band_depths(d)]
    rec = max(int(state.pb_depth or 0), int(tooth["implied_record"]))
    boss_in = None
    if tooth["state"] == "DESCENDING" and node != NODE_BOSS:
        nxt = ((d // 10) + 1) * 10
        while is_city_depth(nxt) and nxt - d < 50:
            nxt += 10
        boss_in = max(0, nxt - d)
    art = shaft_art_for_depth(d)
    return {
        **tooth,
        "node": node,
        "node_label": NODE_LABEL_RU.get(node, node),
        "kicker": frame_kicker(node, palette_id),
        "palette_id": palette_id,
        "phrase": phrase,
        "on_branch": on_branch,
        "sleeves": [{"id": left, "instinct": instinct_id == left}, {"id": right, "instinct": instinct_id == right}],
        "instinct_palette": instinct_id,
        "token_n": len(companions) or 1,
        "nodes": nodes,
        "band_nodes": band_nodes,
        "record": rec,
        "title": title_for_record(rec),
        "boss_in": boss_in,
        "shaft_url": art["url"],
        "shaft_band": art["band"],
        "shaft_biome": art["id"],
        "shaft_label": art["label"],
        "d_max": int(d_max) if d_max is not None else None,
        "event": pq_event,
        "T_eff": int(t_eff or 30) if int(pq_layer) >= 2 else None,
    }


def overlay_flavor_phrase(state: m.DelveState | None, frame: dict[str, Any], companions: Sequence) -> None:
    """Serve cached LLM line with current mercenary names. No LLM."""
    if not frame:
        return
    names = [str(c.name).strip() for c in companions if getattr(c, "name", None)]
    cached = (getattr(state, "flavor_text", None) or "").strip() if state is not None else ""
    source = cached or str(frame.get("phrase") or "")
    fixed = enforce_squad_names(source, names)
    if state is not None and cached and fixed != cached:
        state.flavor_text = fixed[:280]
    if fixed:
        frame["phrase"] = fixed


def showcase_from_state(
    player_id: int,
    state: m.DelveState | None,
    *,
    now: datetime | None = None,
    ov_level: int = 1,
) -> dict[str, Any]:
    if state is None or state.t_origin is None:
        return {
            "started": False,
            "pb_depth": 0,
            "title": None,
            "companions": [],
            "gold_granted_total": 0,
            "xp_granted_total": 0,
        }
    now = now or _now()
    tooth = sawtooth(t_origin=state.t_origin, now=now, ov_level=ov_level)
    rec = max(int(state.pb_depth or 0), int(tooth["implied_record"]))
    return {
        "started": True,
        "pb_depth": rec,
        "depth": int(tooth["d"]),
        "state": tooth["state"],
        "status": tooth["status"],
        "title": title_for_record(rec),
        "title_id": title_id_for_record(rec),
        "palette_id": state.committed_palette,
        "gold_granted_total": int(state.gold_granted_total or 0),
        "xp_granted_total": int(state.xp_granted_total or 0),
    }


async def lite_showcase(session: AsyncSession, player_id: int, *, now: datetime | None = None) -> dict[str, Any]:
    state = await get_state(session, player_id)
    mw = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id)))
    ).scalar_one_or_none()
    ov = int(mw.level or 1) if mw is not None else 1
    out = showcase_from_state(int(player_id), state, now=now, ov_level=ov)
    try:
        comps = await list_companions(session, player_id)
        out["companions"] = [companion_out(c, now=now) for c in comps]
    except Exception:
        out["companions"] = []
    return out


async def grant_and_sync(
    session: AsyncSession,
    player_id: int,
    *,
    now: datetime | None = None,
    mark_legacy_seen: bool = False,
    skip_grant: bool = False,
) -> dict[str, Any]:
    now = now or _now()
    player = await session.get(m.Player, int(player_id))
    if player is None:
        raise DelveError("player_not_found", 404)
    mw = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id)))
    ).scalar_one_or_none()
    unlocked = await is_unlocked(session, player_id, mw)
    state = await get_state_for_update(session, player_id)
    gold_now = 0
    xp_now = 0
    pq_party = None
    from waifu_bot.services.companion_living import (
        card_loyalty,
        list_living_cards,
        migrate_delve_to_cards,
        reconcile_delve_party_to_living,
    )

    living_cards: list[m.CompanionCard] = await list_living_cards(session, player_id)
    if state and state.t_origin is not None:
        await reconcile_delve_party_to_living(session, player_id, now=now)
        living_cards = await list_living_cards(session, player_id)
        if not skip_grant:
            loyalty_mult = loyalty_faucet_mult([card_loyalty(c) for c in living_cards])
            gold_now, xp_now = await grant_tap(
                session, player, mw, state, now=now, loyalty_mult=loyalty_mult
            )
        companions = await list_companions(session, player_id)
        if not skip_grant and (gold_now or xp_now):
            attribute_party_grant(companions, gold_now, xp_now, cards=living_cards)
        try:
            from waifu_bot.services.delve_pq import resolve_pq
            from waifu_bot.services.game_config_service import get_game_config_map

            cfg = await get_game_config_map(session)
            pq_party = await resolve_pq(
                session, state, living_cards, companions, now=now, cfg=cfg
            )
        except Exception:
            logger.exception("delve pq catch-up failed player=%s", player_id)
        pq_d_max = None
        pq_layer = 1
        t_eff = 30
        if pq_party is not None:
            from waifu_bot.game.delve_pq import d_max_of, party_power
            from waifu_bot.game.delve_pq_layer import d_max_eff

            pq_layer = int(getattr(pq_party, "layer", 2) or 2)
            t_eff = int(getattr(pq_party, "t_eff", 30) or 30)
            pq_d_max = d_max_eff(pq_party.mercs, depth=int(pq_party.last_d or 0)) if pq_layer >= 2 else d_max_of(party_power(pq_party.mercs))
        frame = build_frame(
            state,
            companions,
            now=now,
            ov_level=int(mw.level or 1) if mw else 1,
            d_max=pq_d_max,
            pq_layer=pq_layer,
            t_eff=t_eff,
            pq_event=getattr(pq_party, "last_event", None) if pq_party is not None else None,
            pq_last_d=int(pq_party.last_d) if pq_party is not None else None,
        )
        _apply_theater(state, frame, companions)
        if not skip_grant:
            await sync_hidden_counters(session, int(player_id), state, now)
        try:
            from waifu_bot.services.chronicle import resolve_chronicle

            await migrate_delve_to_cards(session, player_id, now=now)
            await resolve_chronicle(session, state, now=now, ov_level=int(mw.level or 1) if mw else 1)
        except Exception:
            logger.exception("delve chronicle catch-up failed player=%s", player_id)
    show_cutover = bool(state and state.migration_from_chronicle and not state.legacy_seen)
    if mark_legacy_seen and state is not None:
        state.legacy_seen = True
    companions = await list_companions(session, player_id)
    return await build_sync_payload(
        session,
        player,
        mw,
        state,
        companions,
        now=now,
        gold_now=gold_now,
        xp_now=xp_now,
        unlocked=unlocked,
        show_cutover=show_cutover,
        living_cards=living_cards,
        pq_party=pq_party,
    )


async def build_sync_payload(
    session: AsyncSession,
    player: m.Player,
    mw: m.MainWaifu | None,
    state: m.DelveState | None,
    companions: list[m.DelveCompanion],
    *,
    now: datetime,
    gold_now: int,
    xp_now: int,
    unlocked: bool,
    show_cutover: bool = False,
    living_cards: list[m.CompanionCard] | None = None,
    pq_party: Any = None,
) -> dict[str, Any]:
    started = bool(state and state.t_origin)
    ov = int(mw.level or 1) if mw is not None else 1
    cap_g, cap_x = await _caps(session, ov)
    pq_d_max = None
    pq_fields: dict[str, Any] = {"pq_enabled": False}
    pq_layer = 1
    t_eff = 30
    if pq_party is not None:
        from waifu_bot.game.delve_pq import d_max_of, party_power
        from waifu_bot.game.delve_pq_layer import d_max_eff
        from waifu_bot.services.delve_pq import pq_payload_fields

        pq_layer = int(getattr(pq_party, "layer", 2) or 2)
        t_eff = int(getattr(pq_party, "t_eff", 30) or 30)
        pq_d_max = d_max_eff(pq_party.mercs, depth=int(pq_party.last_d or 0)) if pq_layer >= 2 else d_max_of(party_power(pq_party.mercs))
        pq_fields = pq_payload_fields(pq_party)
    frame = None
    if started and state is not None:
        frame = build_frame(
            state,
            companions,
            now=now,
            ov_level=ov,
            d_max=pq_d_max,
            pq_layer=pq_layer,
            t_eff=t_eff,
            pq_event=getattr(pq_party, "last_event", None) if pq_party is not None else None,
            pq_last_d=int(pq_party.last_d) if pq_party is not None else None,
        )
        if not (pq_layer >= 2 and frame.get("event") and frame.get("event", {}).get("phrase")):
            overlay_flavor_phrase(state, frame, companions)
        frame["record"] = int(state.pb_depth or 0)
        frame["title"] = title_for_record(int(state.pb_depth or 0))
    reform_ok = False
    reform_reason = None
    if state is not None and started:
        if int(state.sprite_count or 0) >= SPRITE_CAP:
            reform_ok = False
            reform_reason = "sprite_cap"
        elif not reform_ready(state.last_reform_at, now):
            reform_ok = False
            reform_reason = "cooldown"
        else:
            reform_ok = True
    gold_today = int(state.gold_granted_today or 0) if state else 0
    xp_today = int(state.xp_granted_today or 0) if state else 0
    from waifu_bot.services.companion_living import living_preview_rows

    seated = list(living_cards or [])
    merc_by_slot: dict[int, Any] = {}
    if pq_party is not None:
        from waifu_bot.services.delve_pq import merc_public

        merc_by_slot = {int(m.slot): merc_public(m) for m in pq_party.mercs if m.slot}
    return {
        "started": started,
        "unlocked": unlocked,
        "copy": COPY,
        "gold_cap_day": cap_g,
        "xp_cap_day": cap_x,
        "gold_granted_total": int(state.gold_granted_total or 0) if state else 0,
        "xp_granted_total": int(state.xp_granted_total or 0) if state else 0,
        "gold_granted_now": int(gold_now),
        "xp_granted_now": int(xp_now),
        "gold_today": gold_today,
        "xp_today": xp_today,
        "floor_gold_pct": floor_pct(gold_today, cap_g),
        "floor_xp_pct": floor_pct(xp_today, cap_x),
        "player_gold": int(player.gold or 0),
        "t_origin": state.t_origin.isoformat() if state and state.t_origin else None,
        "spine_seed": int(state.spine_seed or 0) if state else 0,
        "pb_depth": int(state.pb_depth or 0) if state else 0,
        "title": title_for_record(int(state.pb_depth or 0)) if state else None,
        "title_id": int(state.title_id or 0) if state else 0,
        "frame": frame,
        "journal": list(state.journal_json or []) if state else [],
        "companions": [companion_out(c, now=now, pq=merc_by_slot.get(int(c.slot))) for c in companions],
        **pq_fields,
        "living_count": len(seated),
        "living_preview": living_preview_rows(seated),
        "sprite_count": int(state.sprite_count or 0) if state else 0,
        "sprite_cap": SPRITE_CAP,
        "reform_ready": reform_ok,
        "reform_reason": reform_reason,
        "reform_cd_days": REFORM_CD_DAYS,
        "stances": list(STANCES.values()),
        "tempers": list(TEMPERS.values()),
        "palettes": [
            {"id": p["id"], "label": p["label"], "shaft": p["shaft"], "accent": p["accent"]}
            for p in PALETTES
        ],
        "shaft_biomes": [shaft_art_for_depth(int(b["band"])) for b in SHAFT_BIOMES],
        "constants": {
            "D0": D0,
            "alpha": ALPHA,
            "t0": T0_SEC,
            "t_up": T_UP_SEC,
            "depth_exp": DEPTH_EXP,
            "ceiling_tail_hours": CEILING_TAIL_HOURS,
            "ceiling_tail_k": CEILING_TAIL_K,
            "ceiling_tail_exp": CEILING_TAIL_EXP,
        },
        "name_suggestions": [pick_companion_name(int(player.id), slot, exclude=[]) for slot in (1, 2, 3)],
        "legacy_names": (state.legacy_names_json if state else None) or [],
        "legacy_seen": False if show_cutover else (bool(state.legacy_seen) if state else True),
        "former_gladiator": bool(state.former_gladiator) if state else False,
        "migration_from_chronicle": bool(state.migration_from_chronicle) if state else False,
        "has_main_waifu": mw is not None,
        "waifu_name": mw.name if mw else None,
        "ov_level": ov,
    }


def _validate_party(companions: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    if size not in (1, 2, 3):
        raise DelveError("invalid_party_size")
    if len(companions) != size:
        raise DelveError("companions_size_mismatch")
    tempers: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(companions, start=1):
        stance = str(raw.get("stance") or raw.get("role") or "").strip()
        temper = str(raw.get("temper") or raw.get("motive") or "").strip()
        name = str(raw.get("name") or "").strip()[:48]
        if stance not in VALID_STANCES:
            raise DelveError("invalid_stance")
        if temper not in VALID_TEMPERS:
            raise DelveError("invalid_temper")
        if temper in tempers:
            raise DelveError("duplicate_temper")
        tempers.add(temper)
        if not name:
            raise DelveError("name_required")
        cloak = str(raw.get("cloak_color") or "").strip() or None
        if cloak and cloak not in CLOAK_COLORS:
            cloak = None
        out.append(
            {
                "slot": i,
                "name": name,
                "stance": stance,
                "temper": temper,
                "cloak_color": cloak,
                "keep_portrait": bool(raw.get("keep_portrait")),
            }
        )
    return out


async def start_delve(
    session: AsyncSession,
    player_id: int,
    *,
    size: int | None = None,
    companions: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or _now()
    mw = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id)))
    ).scalar_one_or_none()
    if mw is None:
        raise DelveError("main_waifu_required", 400)
    if not await is_unlocked(session, player_id, mw):
        raise DelveError("not_unlocked", 403)
    from waifu_bot.services.companion_living import list_living_cards, sync_card_to_delve

    cards = await list_living_cards(session, player_id)
    _ = (size, companions)
    if not cards:
        raise DelveError("need_hire", 400)
    state = await get_state_for_update(session, player_id)
    if state is None:
        state = m.DelveState(player_id=int(player_id), gold_granted_total=0, xp_granted_total=0, sprite_count=0)
        session.add(state)
        await session.flush()
        state = await get_state_for_update(session, player_id) or state
    if state.t_origin is not None:
        raise DelveError("already_started", 409)
    n = len(cards)
    if int(state.sprite_count or 0) + n > SPRITE_CAP:
        raise DelveError("sprite_cap", 400)
    living_slots = {int(c.slot) for c in cards if c.slot}
    existing = await list_companions(session, player_id)
    for row in existing:
        if int(row.slot) not in living_slots:
            await session.delete(row)
    await session.flush()
    for card in cards:
        await sync_card_to_delve(session, card)
    state.t_origin = now
    state.last_grant_ts = now
    state.last_pq_ts = now
    state.run_origin = now
    state.spine_seed = int(player_id) ^ int(now.timestamp())
    state.pq_seed = int(state.spine_seed)
    state.pq_last_cycle = 0
    state.pq_last_d = 0
    state.sprite_count = int(state.sprite_count or 0) + n
    state.pb_depth = 0
    state.committed_palette = seed_palette_id(int(state.spine_seed))
    state.pending_tint = None
    state.journal_json = []
    await session.flush()
    try:
        from waifu_bot.services.event_log import log_event

        await log_event(session, int(player_id), "delve_started", {"started": True, "size": n})
    except Exception:
        pass
    return await grant_and_sync(session, player_id, now=now)


async def reform_delve(
    session: AsyncSession,
    player_id: int,
    *,
    size: int,
    companions: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or _now()
    parsed = _validate_party(companions, int(size))
    state = await get_state_for_update(session, player_id)
    if state is None or state.t_origin is None:
        raise DelveError("not_started", 400)
    if not reform_ready(state.last_reform_at, now):
        raise DelveError("reform_cooldown", 429)
    n = len(parsed)
    if int(state.sprite_count or 0) + n > SPRITE_CAP:
        raise DelveError("sprite_cap", 400)
    old = await list_companions(session, player_id)
    old_by_slot = {int(row.slot): row for row in old}
    for row in old:
        await session.delete(row)
    await session.flush()
    for spec in parsed:
        session.add(
            m.DelveCompanion(
                player_id=int(player_id),
                slot=int(spec["slot"]),
                name=spec["name"],
                stance=spec["stance"],
                temper=spec["temper"],
                cloak_color=spec.get("cloak_color"),
                image_path=_portrait_path_for_slot(
                    int(player_id),
                    int(spec["slot"]),
                    old_by_slot.get(int(spec["slot"])),
                    keep_file=bool(spec.get("keep_portrait")),
                ),
                gold_earned=0,
                xp_earned=0,
                joined_at=now,
            )
        )
    state.last_reform_at = now
    state.sprite_count = int(state.sprite_count or 0) + n
    await session.flush()
    return await grant_and_sync(session, player_id, now=now)


async def tint_sleeve(session: AsyncSession, player_id: int, palette_id: str) -> dict[str, Any]:
    if palette_id not in PALETTE_IDS:
        raise DelveError("invalid_palette")
    now = _now()
    state = await get_state_for_update(session, player_id)
    if state is None or state.t_origin is None:
        raise DelveError("not_started", 400)
    mw = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(player_id)))
    ).scalar_one_or_none()
    companions = await list_companions(session, player_id)
    frame = build_frame(state, companions, now=now, ov_level=int(mw.level or 1) if mw else 1)
    if not frame.get("on_branch"):
        raise DelveError("not_on_branch", 409)
    allowed = {s["id"] for s in frame["sleeves"]}
    if palette_id not in allowed:
        raise DelveError("palette_not_on_sleeves", 400)
    state.committed_palette = palette_id
    state.pending_tint = palette_id
    await session.flush()
    return await grant_and_sync(session, player_id, now=now, skip_grant=True)


async def grant_batch(session: AsyncSession, *, limit: int = 200) -> int:
    """Hourly cron: catch-up gold/XP. No theater LLM."""
    now = _now()
    rows = (
        await session.execute(
            select(m.DelveState)
            .where(m.DelveState.t_origin.is_not(None))
            .order_by(m.DelveState.player_id.asc())
            .limit(int(limit))
        )
    ).scalars().all()
    n = 0
    for state in rows:
        player = await session.get(m.Player, int(state.player_id))
        if player is None:
            continue
        locked = await get_state_for_update(session, int(state.player_id))
        if locked is None:
            continue
        mw = (
            await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == int(locked.player_id)))
        ).scalar_one_or_none()
        gold, xp = await grant_tap(session, player, mw, locked, now=now)
        comps = await list_companions(session, int(locked.player_id))
        if gold or xp:
            attribute_party_grant(comps, gold, xp)
            n += 1
        if locked.t_origin is not None:
            try:
                from waifu_bot.services.companion_living import list_living_cards
                from waifu_bot.services.delve_pq import resolve_pq
                from waifu_bot.services.game_config_service import get_game_config_map
                from waifu_bot.game.delve_pq import d_max_of, party_power

                cards = await list_living_cards(session, int(locked.player_id))
                cfg = await get_game_config_map(session)
                pq_party = await resolve_pq(session, locked, cards, comps, now=now, cfg=cfg)
                pq_d_max = d_max_of(party_power(pq_party.mercs)) if pq_party else None
                pq_layer = int(getattr(pq_party, "layer", 2) or 2) if pq_party else 1
                t_eff = int(getattr(pq_party, "t_eff", 30) or 30) if pq_party else 30
            except Exception:
                logger.exception("delve pq batch failed player=%s", locked.player_id)
                pq_d_max = None
                pq_layer = 1
                t_eff = 30
                pq_party = None
            frame = build_frame(
                locked,
                comps,
                now=now,
                ov_level=int(mw.level or 1) if mw else 1,
                d_max=pq_d_max,
                pq_layer=pq_layer,
                t_eff=t_eff,
                pq_last_d=int(pq_party.last_d) if pq_party is not None else None,
            )
            _apply_theater(locked, frame, comps)
    return n

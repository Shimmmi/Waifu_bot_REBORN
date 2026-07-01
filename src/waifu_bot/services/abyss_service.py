"""Abyss (Бездна) orchestration service.

Owns the persistent per-player progress row, floor generation (monsters,
modifiers, bosses), session lifecycle (enter/exit/resume), the daily checkpoint
limit (MSK), Grace selection and the public status payload.

Combat itself lives in :mod:`waifu_bot.services.abyss_combat`, which reuses the
floor-generation helpers exported here.
"""
from __future__ import annotations

import logging
import math
import random
from datetime import date, datetime, timedelta, timezone

try:  # stdlib on 3.9+
    from zoneinfo import ZoneInfo

    _MSK = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover - fallback if tzdata missing
    _MSK = timezone(timedelta(hours=3))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    AbyssCheckpointBoss,
    AbyssGrace,
    AbyssProgress,
    AbyssWeeklyLeaderboard,
    DungeonProgress,
    DungeonRun,
    MainWaifu,
    MonsterAffix,
    MonsterTemplate,
    Player,
    PlayerMonsterCodex,
)
from waifu_bot.services import abyss_rewards as ar
from waifu_bot.services.game_config_service import (
    cfg_float,
    cfg_int,
    get_game_config_map,
)

logger = logging.getLogger(__name__)

# Behaviour flags introduced by the Abyss (ТЗ §10); only spawn on deep floors.
ABYSS_EXCLUSIVE_FLAGS = frozenset({"GRACE_STEAL", "ABYSS_MIRROR", "ANTI_REGEN", "CHAOS_DMG"})


# ---------------------------------------------------------------------------
# Time helpers (MSK / UTC+3)
# ---------------------------------------------------------------------------

def msk_now() -> datetime:
    return datetime.now(_MSK)


def msk_today() -> date:
    return msk_now().date()


def week_start_msk(now: datetime | None = None) -> date:
    """Monday (ISO) of the current MSK week."""
    d = (now or msk_now()).date()
    return d - timedelta(days=d.weekday())


# ---------------------------------------------------------------------------
# Progress access
# ---------------------------------------------------------------------------

async def get_progress(session: AsyncSession, player_id: int) -> AbyssProgress | None:
    return await session.scalar(
        select(AbyssProgress).where(AbyssProgress.player_id == player_id)
    )


async def get_or_create_progress(session: AsyncSession, player_id: int) -> AbyssProgress:
    progress = await get_progress(session, player_id)
    if progress is None:
        progress = AbyssProgress(player_id=player_id)
        session.add(progress)
        await session.flush()
    return progress


async def get_progress_for_update(session: AsyncSession, player_id: int) -> AbyssProgress | None:
    """Row-locked progress (SELECT ... FOR UPDATE) to avoid race conditions."""
    return await session.scalar(
        select(AbyssProgress).where(AbyssProgress.player_id == player_id).with_for_update()
    )


async def get_waifu(session: AsyncSession, player_id: int) -> MainWaifu | None:
    return await session.scalar(select(MainWaifu).where(MainWaifu.player_id == player_id))


async def has_active_solo_run(session: AsyncSession, player_id: int) -> bool:
    run = await session.scalar(
        select(DungeonRun.id).where(
            DungeonRun.player_id == player_id, DungeonRun.status == "active"
        ).limit(1)
    )
    if run is not None:
        return True
    prog = await session.scalar(
        select(DungeonProgress.id).where(
            DungeonProgress.player_id == player_id, DungeonProgress.is_active.is_(True)
        ).limit(1)
    )
    return prog is not None


async def has_active_abyss_session(session: AsyncSession, player_id: int) -> bool:
    active = await session.scalar(
        select(AbyssProgress.session_active).where(
            AbyssProgress.player_id == player_id,
            AbyssProgress.session_active.is_(True),
        ).limit(1)
    )
    return active is True


# ---------------------------------------------------------------------------
# Daily limit + session timeout
# ---------------------------------------------------------------------------

def reset_daily_if_needed(progress: AbyssProgress) -> bool:
    """Reset the daily checkpoint counter when the MSK date changed."""
    today = msk_today()
    if progress.last_checkpoint_date != today:
        progress.checkpoints_today = 0
        progress.last_checkpoint_date = today
        return True
    return False


def daily_limit_remaining(cfg: dict[str, str], progress: AbyssProgress) -> int:
    limit = cfg_int(cfg, "abyss_daily_checkpoint_limit", 3)
    return max(0, limit - int(progress.checkpoints_today or 0))


def under_daily_limit(cfg: dict[str, str], progress: AbyssProgress) -> bool:
    return daily_limit_remaining(cfg, progress) > 0


def limit_resets_at_iso() -> str:
    """ISO datetime of the next MSK midnight (when the daily limit resets)."""
    now = msk_now()
    tomorrow = (now + timedelta(days=1)).date()
    reset = datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=_MSK)
    return reset.isoformat()


async def maybe_timeout_session(
    session: AsyncSession, cfg: dict[str, str], progress: AbyssProgress
) -> bool:
    """Auto-exit an abandoned session whose updated_at is older than the timeout."""
    if not progress.session_active:
        return False
    hours = cfg_int(cfg, "abyss_session_timeout_hours", 24)
    updated = progress.updated_at
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - updated > timedelta(hours=hours):
        _reset_block_on_exit(progress)
        return True
    return False


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

async def check_access(
    session: AsyncSession,
    cfg: dict[str, str],
    player: Player,
    waifu: MainWaifu | None,
) -> tuple[bool, str | None]:
    """Return (is_available, unavailable_reason)."""
    if waifu is None:
        return False, "Создайте основную вайфу"
    min_level = cfg_int(cfg, "abyss_min_waifu_level", 10)
    if int(waifu.level or 1) < min_level:
        return False, f"Достигните {min_level}-го уровня ОВ"
    if int(player.max_act or 1) < 2:
        return False, "Пройдите последнее подземелье Акта 1"
    if await has_active_solo_run(session, player.id):
        return False, "Сначала завершите активное подземелье"
    return True, None


# ---------------------------------------------------------------------------
# Monster / floor generation
# ---------------------------------------------------------------------------

def _monster_level_for_floor(floor: int) -> int:
    return max(1, min(60, math.ceil(floor / 2)))


def _act_for_floor(floor: int) -> int:
    return max(1, min(5, math.ceil(floor / 20)))


async def _pick_template_for_biome(
    session: AsyncSession, tags: list[str], rng: random.Random
) -> MonsterTemplate | None:
    """Pick a weighted random monster template whose tags overlap the biome."""
    res = await session.execute(select(MonsterTemplate))
    templates: list[MonsterTemplate] = list(res.scalars().all())
    if not templates:
        return None
    tagset = {t.lower() for t in tags}

    def tmpl_tags(t: MonsterTemplate) -> set[str]:
        raw = t.tags or []
        if isinstance(raw, dict):
            raw = list(raw.keys())
        out: set[str] = set()
        for x in raw or []:
            out.add(str(x).lower())
        if t.family:
            out.add(str(t.family).lower())
        return out

    matched = [t for t in templates if tmpl_tags(t) & tagset]
    pool = matched or templates
    weights = [max(1, int(getattr(t, "weight", 100) or 100)) for t in pool]
    return rng.choices(pool, weights=weights)[0]


async def _roll_elite(
    session: AsyncSession,
    cfg: dict[str, str],
    monster: dict,
    floor: int,
    rng: random.Random,
) -> None:
    """Roll elite affixes for an ordinary monster, applying stat multipliers in-place.

    For MVP only the stat/name effects are applied; runtime affix behaviour
    (REFLECT/CURSE/...) for ordinary elites is deferred to a later stage.
    """
    chance = ar.calc_abyss_elite_chance(cfg, floor)
    if rng.random() >= chance:
        return

    res = await session.execute(select(MonsterAffix))
    all_affixes: list[MonsterAffix] = list(res.scalars().all())
    family = (monster.get("family") or "").lower()

    tier2_floor = cfg_int(cfg, "abyss_affix_tier2_floor", 21)
    tier3_floor = cfg_int(cfg, "abyss_affix_tier3_floor", 51)
    max_tier = 1
    if floor >= tier2_floor:
        max_tier = 2
    if floor >= tier3_floor:
        max_tier = 3

    eligible: list[MonsterAffix] = []
    for a in all_affixes:
        if a.allowed_families and family not in [str(x).lower() for x in a.allowed_families]:
            continue
        if a.forbidden_families and family in [str(x).lower() for x in a.forbidden_families]:
            continue
        if a.tier is not None and int(a.tier) > max_tier:
            continue
        # Эксклюзивные Бездна-аффиксы (§10) появляются только с глубоких этажей.
        if a.behavior_flag in ABYSS_EXCLUSIVE_FLAGS and floor < tier3_floor:
            continue
        eligible.append(a)
    if not eligible:
        return

    r = rng.random()
    if r < 0.60:
        n, color = 1, "blue"
    elif r < 0.88:
        n, color = 2, "blue"
    elif r < 0.98:
        n, color = 3, "gold"
    else:
        n, color = 4, "red"

    chosen = _pick_affixes(eligible, n, rng)
    if not chosen:
        return

    hp_mult = dmg_mult = gold_mult = exp_mult = 1.0
    for a in chosen:
        if a.hp_mult:
            hp_mult *= float(a.hp_mult)
        if a.dmg_mult:
            dmg_mult *= float(a.dmg_mult)
        if a.gold_mult:
            gold_mult *= float(a.gold_mult)
        if a.exp_mult:
            exp_mult *= float(a.exp_mult)

    monster["max_hp"] = max(1, round(monster["max_hp"] * hp_mult))
    monster["current_hp"] = monster["max_hp"]
    monster["damage"] = max(1, round(monster["damage"] * dmg_mult))
    monster["gold_min"] = max(1, round(monster["gold_min"] * gold_mult))
    monster["gold_max"] = max(1, round(monster["gold_max"] * gold_mult))
    monster["exp_reward"] = max(1, round(monster["exp_reward"] * exp_mult))

    prefixes = [a.name for a in chosen if a.type == "prefix"]
    suffixes = [a.name for a in chosen if a.type == "suffix"]
    base_name = monster["name"]
    name = (" ".join(prefixes + [base_name])).strip() if prefixes else base_name
    if suffixes:
        name += "".join(suffixes)
    monster["name"] = name
    monster["is_elite"] = True
    monster["elite_color"] = color
    monster["applied_affix_ids"] = [a.id for a in chosen]
    # Runtime behaviour hooks consumed by abyss_combat (§10 Бездна-аффиксы).
    behaviors = [
        {"flag": a.behavior_flag, "params": dict(a.behavior_params or {})}
        for a in chosen
        if a.behavior_flag
    ]
    if behaviors:
        monster["affix_behaviors"] = behaviors


def _pick_affixes(eligible: list[MonsterAffix], n: int, rng: random.Random) -> list[MonsterAffix]:
    pool = list(eligible)
    rng.shuffle(pool)
    chosen: list[MonsterAffix] = []
    groups: set[str] = set()
    behavioral_suffix = 0
    chosen_ids: set[int] = set()
    for a in pool:
        if len(chosen) >= n:
            break
        if a.affix_group in groups:
            continue
        if a.category == "behavior" and a.type == "suffix":
            if behavioral_suffix >= 1:
                continue
        if a.incompatible_with and any(g in groups for g in a.incompatible_with):
            continue
        chosen.append(a)
        chosen_ids.add(a.id)
        groups.add(a.affix_group)
        if a.category == "behavior" and a.type == "suffix":
            behavioral_suffix += 1
    return chosen


async def _pick_echo_identity(
    session: AsyncSession, player_id: int, rng: random.Random
) -> MonsterTemplate | None:
    """Pick a campaign monster the player has actually slain, for an ECHO floor.

    Visual-only: the echo keeps normal Abyss-scaled stats but wears the identity
    (name/slug/emoji) of a foe from the player's codex, preferring higher tiers.
    """
    res = await session.execute(
        select(MonsterTemplate)
        .join(PlayerMonsterCodex, PlayerMonsterCodex.monster_template_id == MonsterTemplate.id)
        .where(PlayerMonsterCodex.player_id == player_id, PlayerMonsterCodex.kills > 0)
        .order_by(MonsterTemplate.tier.desc(), PlayerMonsterCodex.kills.desc())
        .limit(12)
    )
    cands = list(res.scalars().all())
    return rng.choice(cands) if cands else None


async def build_normal_monster(
    session: AsyncSession,
    cfg: dict[str, str],
    floor: int,
    modifier: str | None,
    rng: random.Random | None = None,
    *,
    player_id: int | None = None,
) -> dict:
    rng = rng or random
    tags = ar.get_abyss_biome_tags(floor)
    tmpl = await _pick_template_for_biome(session, tags, rng)

    hp_base = cfg_int(cfg, "abyss_monster_hp_base", 200)
    dmg_base = cfg_int(cfg, "abyss_monster_dmg_base", 30)
    exp_base = cfg_int(cfg, "abyss_monster_exp_base", 50)
    gold_base = cfg_int(cfg, "abyss_gold_base", 20)

    hp = ar.calc_abyss_monster_hp(cfg, hp_base, floor)
    dmg = ar.calc_abyss_monster_dmg(cfg, dmg_base, floor)
    exp = ar.calc_abyss_monster_exp(cfg, exp_base, floor)
    gold_min, gold_max = ar.calc_abyss_gold(cfg, gold_base, floor)

    # RAGE modifier doubles monster damage.
    if modifier == "RAGE":
        dmg = max(1, round(dmg * cfg_float(cfg, "abyss_modifier_rage_dmg", 2.0)))

    name = tmpl.name if tmpl else "Тварь Бездны"
    echo_id = None
    if modifier == "ECHO":
        if player_id is not None:
            echo_id = await _pick_echo_identity(session, player_id, rng)
        if echo_id is not None:
            tmpl = echo_id  # adopt the slain foe's visual identity
            name = f"Эхо: {echo_id.name}"
        else:
            name = f"Эхо: {name}"

    monster = {
        "name": name,
        "family": (tmpl.family if tmpl else None),
        "slug": (tmpl.slug if tmpl else None),
        "emoji": (tmpl.emoji if tmpl else None),
        "tier": int(getattr(tmpl, "tier", 1) or 1) if tmpl else 1,
        "template_id": int(tmpl.id) if tmpl else None,
        "level": _monster_level_for_floor(floor),
        "is_boss": False,
        "is_elite": False,
        "elite_color": None,
        "max_hp": hp,
        "current_hp": hp,
        "damage": dmg,
        "exp_reward": exp,
        "gold_min": gold_min,
        "gold_max": gold_max,
        "applied_affix_ids": [],
        "special_mechanic": None,
        "mechanic_params": {},
        "mechanic_state": {},
    }
    await _roll_elite(session, cfg, monster, floor, rng)
    return monster


async def build_boss_monster(
    session: AsyncSession, cfg: dict[str, str], floor: int
) -> dict:
    boss = await session.scalar(
        select(AbyssCheckpointBoss).where(AbyssCheckpointBoss.floor_number == floor)
    )
    if boss is None:
        # Deepest defined boss as a template for floors beyond the seeded range.
        boss = await session.scalar(
            select(AbyssCheckpointBoss).order_by(AbyssCheckpointBoss.floor_number.desc()).limit(1)
        )

    if boss is None:
        # Absolute fallback: a beefed-up normal monster.
        m = await build_normal_monster(session, cfg, floor, None)
        m["name"] = f"Страж этажа {floor}"
        m["is_boss"] = True
        m["max_hp"] = m["current_hp"] = max(1, m["max_hp"] * 5)
        m["damage"] = max(1, m["damage"] * 2)
        return m

    hp = ar.calc_abyss_monster_hp(cfg, boss.base_hp, floor)
    dmg = ar.calc_abyss_monster_dmg(cfg, boss.base_dmg, floor)
    exp = ar.calc_abyss_monster_exp(cfg, boss.base_exp, floor)
    exp = round(exp * cfg_float(cfg, "abyss_checkpoint_exp_mult", 3.0))

    mechanic_params = _normalize_boss_mechanics(dict(boss.mechanic_params or {}))

    gold_base = cfg_int(cfg, "abyss_gold_base", 20)
    g_min, g_max = ar.calc_abyss_gold(cfg, gold_base, floor)
    boss_mult = cfg_float(cfg, "abyss_gold_boss_mult", 3.0)
    g_min = max(1, round(g_min * boss_mult))
    g_max = max(1, round(g_max * boss_mult))

    return {
        "name": boss.name,
        "family": boss.family,
        "slug": boss.slug,
        "emoji": None,
        "tier": 5,
        "template_id": None,
        "level": _monster_level_for_floor(floor),
        "is_boss": True,
        "is_elite": False,
        "elite_color": None,
        "max_hp": hp,
        "current_hp": hp,
        "damage": dmg,
        "exp_reward": exp,
        "gold_min": g_min,
        "gold_max": g_max,
        "applied_affix_ids": [],
        "special_mechanic": boss.special_mechanic,
        "mechanic_params": mechanic_params,
        "mechanic_state": {},
        "warning_text": boss.warning_text,
        "description": boss.description,
    }


def _normalize_boss_mechanics(params: dict) -> dict:
    """Expand high-level COMBINED flags into concrete, runtime-handled params.

    The combat engine reads individual keys (reflect_chance / revive_hp_pct /
    copies / stone_skin_max / phase_2_at). The deepest bosses are seeded with
    umbrella flags (``all_mechanics``, ``modifier_every_n``) — fill in working
    defaults so their mechanics actually fire.
    """
    if params.get("all_mechanics"):
        params.setdefault("reflect_chance", 0.20)
        params.setdefault("reflect_pct", 0.25)
        params.setdefault("revive_hp_pct", 0.5)
        params.setdefault("copies", 2)
        params.setdefault("copy_hp_pct", 0.4)
        params.setdefault("copy_dmg_pct", 0.4)
        params.setdefault("phase_2_at", 0.5)
        params.setdefault("rage_dmg_mult", 1.4)
    if params.get("modifier_every_n"):
        # Cycling between affixes per N messages is future polish; ensure the
        # boss at least reflects and enrages so the fight is non-trivial.
        params.setdefault("reflect_chance", 0.25)
        params.setdefault("reflect_pct", 0.25)
        params.setdefault("phase_2_at", 0.5)
        params.setdefault("rage_dmg_mult", 1.5)
    return params


def expire_grace_if_needed(progress: AbyssProgress, floor: int) -> None:
    if progress.active_grace_id is None:
        return
    if progress.grace_expires_at_floor and floor > int(progress.grace_expires_at_floor):
        progress.active_grace_id = None
        progress.grace_expires_at_floor = None


async def generate_floor(
    session: AsyncSession,
    cfg: dict[str, str],
    progress: AbyssProgress,
    floor: int,
    rng: random.Random | None = None,
) -> None:
    """Set up the given floor: monster(s), modifier, max-floor / leaderboard."""
    rng = rng or random
    progress.current_floor = floor
    if floor > int(progress.max_floor_reached or 0):
        progress.max_floor_reached = floor
        await _update_weekly_leaderboard(session, progress.player_id, floor)

    expire_grace_if_needed(progress, floor)

    if ar.is_checkpoint(floor):
        progress.current_floor_modifier = None
        progress.modifier_params = None
        progress.floor_monsters_remaining = 1
        progress.current_monster = await build_boss_monster(session, cfg, floor)
        return

    modifier: str | None = None
    if ar.should_assign_modifier(cfg, floor, int(progress.last_modifier_floor or 0), rng):
        modifier = ar.pick_modifier(cfg, rng)
        if modifier:
            progress.last_modifier_floor = floor
    progress.current_floor_modifier = modifier
    progress.modifier_params = None
    progress.floor_monsters_remaining = cfg_int(cfg, "abyss_monsters_per_floor", 3)
    progress.current_monster = await build_normal_monster(
        session, cfg, floor, modifier, rng, player_id=progress.player_id
    )


async def _update_weekly_leaderboard(
    session: AsyncSession, player_id: int, floor: int
) -> None:
    ws = week_start_msk()
    stmt = (
        pg_insert(AbyssWeeklyLeaderboard)
        .values(player_id=player_id, week_start=ws, max_floor=floor)
        .on_conflict_do_update(
            index_elements=["player_id", "week_start"],
            set_={"max_floor": floor, "updated_at": datetime.utcnow()},
            where=AbyssWeeklyLeaderboard.max_floor < floor,
        )
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Block reset (exit / death-exit)
# ---------------------------------------------------------------------------

def _reset_block_on_exit(progress: AbyssProgress) -> dict:
    """Roll back the current block to the last checkpoint. Returns lost info."""
    floors_lost = max(0, int(progress.current_floor or 0) - int(progress.current_checkpoint or 0))
    progress.session_active = False
    progress.session_started_at = None
    progress.current_floor = int(progress.current_checkpoint or 0)
    progress.current_monster = None
    progress.floor_monsters_remaining = None
    progress.current_floor_modifier = None
    progress.modifier_params = None
    progress.pending_grace_choices = None
    progress.revive_scrolls_used_this_block = 0
    return {"floors_lost": floors_lost, "checkpoint_restored_to": int(progress.current_checkpoint or 0)}


# ---------------------------------------------------------------------------
# Grace
# ---------------------------------------------------------------------------

async def generate_grace_choices(
    session: AsyncSession, cfg: dict[str, str], floor: int, rng: random.Random | None = None
) -> list[int]:
    rng = rng or random
    count = cfg_int(cfg, "abyss_grace_choices_count", 3)
    res = await session.execute(
        select(AbyssGrace).where(
            AbyssGrace.is_active.is_(True),
            AbyssGrace.min_floor <= floor,
        )
    )
    available = [g for g in res.scalars().all() if g.max_floor is None or g.max_floor >= floor]
    if not available:
        return []
    chosen = rng.sample(available, min(count, len(available)))
    return [g.id for g in chosen]


async def get_active_grace(session: AsyncSession, progress: AbyssProgress) -> AbyssGrace | None:
    if progress.active_grace_id is None:
        return None
    return await session.get(AbyssGrace, int(progress.active_grace_id))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

async def _affix_chips(session: AsyncSession, affix_ids: list[int] | None) -> list[dict]:
    if not affix_ids:
        return []
    res = await session.execute(select(MonsterAffix).where(MonsterAffix.id.in_(affix_ids)))
    return [{"id": a.id, "name": a.name, "type": a.type} for a in res.scalars().all()]


async def serialize_monster(session: AsyncSession, monster: dict | None) -> dict | None:
    if not monster:
        return None
    return {
        "name": monster.get("name"),
        "hp_current": int(monster.get("current_hp") or 0),
        "hp_max": int(monster.get("max_hp") or 0),
        "level": int(monster.get("level") or 1),
        "is_elite": bool(monster.get("is_elite")),
        "is_boss": bool(monster.get("is_boss")),
        "elite_color": monster.get("elite_color"),
        "affixes": await _affix_chips(session, monster.get("applied_affix_ids")),
        "family": monster.get("family"),
        "slug": monster.get("slug"),
        "emoji": monster.get("emoji"),
        "special_mechanic": monster.get("special_mechanic"),
        "warning_text": monster.get("warning_text"),
    }


def _grace_payload(grace: AbyssGrace, expires_at_floor: int | None = None) -> dict:
    out = {
        "id": grace.id,
        "name": grace.name,
        "description": grace.description,
        "icon": grace.icon,
        "effect_label": grace.effect_label,
    }
    if expires_at_floor is not None:
        out["expires_at_floor"] = int(expires_at_floor)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class AbyssService:
    """High-level Abyss operations used by API routes and the bot handler."""

    async def get_status(self, session: AsyncSession, player_id: int) -> dict:
        cfg = await get_game_config_map(session)
        player = await session.get(Player, player_id)
        waifu = await get_waifu(session, player_id)
        progress = await get_or_create_progress(session, player_id)

        timed_out = await maybe_timeout_session(session, cfg, progress)
        reset_daily_if_needed(progress)

        is_available, reason = await check_access(session, cfg, player, waifu)

        active_grace = await get_active_grace(session, progress)
        grace_payload = None
        if active_grace:
            grace_payload = _grace_payload(active_grace, progress.grace_expires_at_floor)
            grace_payload["description"] = active_grace.description

        next_checkpoint = ((int(progress.current_floor or 0) // 10) + 1) * 10

        await session.commit()

        modifier = progress.current_floor_modifier
        return {
            "is_available": bool(is_available),
            "unavailable_reason": reason,
            "session_active": bool(progress.session_active),
            "current_floor": int(progress.current_floor or 0),
            "max_floor_reached": int(progress.max_floor_reached or 0),
            "current_checkpoint": int(progress.current_checkpoint or 0),
            "next_checkpoint": next_checkpoint,
            "abyss_shards": int(progress.abyss_shards or 0),
            "checkpoints_today": int(progress.checkpoints_today or 0),
            "daily_limit": cfg_int(cfg, "abyss_daily_checkpoint_limit", 3),
            "limit_resets_at": limit_resets_at_iso(),
            "active_grace": grace_payload,
            "current_floor_modifier": modifier,
            "modifier_label": ar.modifier_label(modifier),
            "modifier_description": ar.MODIFIER_DESCRIPTIONS.get(modifier) if modifier else None,
            "pending_grace_choices": await self._serialize_pending_graces(session, progress),
            "waifu_hp": int(waifu.current_hp or 0) if waifu else 0,
            "waifu_max_hp": int(waifu.max_hp or 0) if waifu else 0,
            "waifu_unconscious": bool(waifu and int(waifu.current_hp or 0) <= 0),
            "current_monster": await serialize_monster(session, progress.current_monster),
            "session_timed_out": bool(timed_out),
        }

    async def _serialize_pending_graces(
        self, session: AsyncSession, progress: AbyssProgress
    ) -> list[dict] | None:
        ids = progress.pending_grace_choices
        if not ids:
            return None
        res = await session.execute(select(AbyssGrace).where(AbyssGrace.id.in_(ids)))
        by_id = {g.id: g for g in res.scalars().all()}
        out = []
        for gid in ids:
            g = by_id.get(gid)
            if g:
                out.append({
                    "id": g.id,
                    "name": g.name,
                    "description": g.description,
                    "icon": g.icon,
                    "effect_label": g.effect_label,
                })
        return out

    async def enter(self, session: AsyncSession, player_id: int) -> dict:
        cfg = await get_game_config_map(session)
        player = await session.get(Player, player_id)
        waifu = await get_waifu(session, player_id)
        progress = await get_progress_for_update(session, player_id)
        if progress is None:
            progress = await get_or_create_progress(session, player_id)
            progress = await get_progress_for_update(session, player_id)

        await maybe_timeout_session(session, cfg, progress)
        reset_daily_if_needed(progress)

        # Already in a session → idempotent: just report current floor.
        if progress.session_active:
            await session.commit()
            return await self._enter_payload(session, progress, already=True)

        is_available, reason = await check_access(session, cfg, player, waifu)
        if not is_available:
            await session.commit()
            return {"success": False, "error": "NOT_AVAILABLE", "reason": reason}
        if waifu and int(waifu.current_hp or 0) <= 0:
            await session.commit()
            return {"success": False, "error": "UNCONSCIOUS"}

        begin_floor = int(progress.current_floor or 0) + 1
        progress.session_active = True
        progress.session_started_at = datetime.now(timezone.utc)
        progress.revive_scrolls_used_this_block = 0
        progress.pending_grace_choices = None
        await generate_floor(session, cfg, progress, begin_floor)

        if player is not None:
            player.last_combat_action_at = datetime.now(timezone.utc)

        await session.commit()
        return await self._enter_payload(session, progress)

    async def _enter_payload(
        self, session: AsyncSession, progress: AbyssProgress, *, already: bool = False
    ) -> dict:
        monster = await serialize_monster(session, progress.current_monster)
        modifier = progress.current_floor_modifier
        return {
            "success": True,
            "already_in_session": already,
            "floor": int(progress.current_floor or 0),
            "modifier": modifier,
            "modifier_label": ar.modifier_label(modifier),
            "is_checkpoint": ar.is_checkpoint(int(progress.current_floor or 0)),
            "first_monster": monster,
        }

    async def exit_abyss(self, session: AsyncSession, player_id: int) -> dict:
        progress = await get_progress_for_update(session, player_id)
        if progress is None or not progress.session_active:
            await session.commit()
            return {"success": False, "error": "NOT_IN_SESSION"}
        info = _reset_block_on_exit(progress)
        await session.commit()
        return {
            "success": True,
            "floors_lost": info["floors_lost"],
            "checkpoint_restored_to": info["checkpoint_restored_to"],
            "rewards_kept": {
                "shards_total": int(progress.abyss_shards or 0),
            },
        }

    async def choose_grace(self, session: AsyncSession, player_id: int, grace_id: int) -> dict:
        cfg = await get_game_config_map(session)
        progress = await get_progress_for_update(session, player_id)
        if progress is None or not progress.pending_grace_choices:
            await session.commit()
            return {"success": False, "error": "NO_PENDING_GRACE"}
        if int(grace_id) not in [int(x) for x in progress.pending_grace_choices]:
            await session.commit()
            return {"success": False, "error": "INVALID_GRACE"}

        grace = await session.get(AbyssGrace, int(grace_id))
        if grace is None:
            await session.commit()
            return {"success": False, "error": "INVALID_GRACE"}

        floor = int(progress.current_floor or 0)
        progress.active_grace_id = grace.id
        progress.grace_expires_at_floor = floor + 10
        progress.pending_grace_choices = None

        # Advance to the next floor now that the Grace is chosen.
        await generate_floor(session, cfg, progress, floor + 1)
        await session.commit()
        return {
            "success": True,
            "grace": _grace_payload(grace, progress.grace_expires_at_floor),
            "next_floor": int(progress.current_floor or 0),
        }

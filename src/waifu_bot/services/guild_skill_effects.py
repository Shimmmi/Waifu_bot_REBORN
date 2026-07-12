"""Resolved guild skill bonuses for a player (via their guild)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Guild, GuildLevelThreshold, GuildMember, GuildSkillDefinition, GuildSkillLevelRow

GUILD_SKILL_PARAM_LABELS: dict[str, str] = {
    "gd_party_damage_pct": "Боевой клич",
    "raid_attack_flat": "Боевое братство",
    "raid_boss_damage_pct": "Осадная тактика",
    "raid_completion_reward_pct": "Воля к победе",
    "damage_per_online_member_pct": "Дух гильдии",
    "raid_gxp_multiplier": "Нерушимые узы",
    "max_hp_pct": "Живучесть",
    "raid_monster_damage_reduction_pct": "Военная хитрость",
    "monster_gold_pct": "Торговый пакт",
    "dungeon_exp_pct": "Военная дисциплина",
    "bank_slots_bonus": "Гильдейский склад",
    "item_drop_pct": "Острый глаз",
    "tavern_heal_discount_pct": "Экономия сил",
    "tavern_hire_discount_pct": "Мастерство найма",
    "global_reward_pct": "Легенда гильдии",
    "chat_reward_pct": "Светская гильдия",
}

_STACK_PCT = {
    "gd_party_damage_pct",
    "monster_gold_pct",
    "dungeon_exp_pct",
    "max_hp_pct",
    "global_reward_pct",
    "chat_reward_pct",
    "item_drop_pct",
}


@dataclass
class GuildSkillContribution:
    param: str
    name: str
    value: float


def _skill_label(param: str, fallback_name: str | None = None) -> str:
    return GUILD_SKILL_PARAM_LABELS.get(param) or (fallback_name or param)


def _format_pct_value(v: float) -> str:
    pct = abs(v) * 100 if abs(v) <= 1 else v
    shown = pct if pct % 1 else int(pct)
    return f"+{shown}%"


def pct_bonus_lines_ru(contributions: list[GuildSkillContribution]) -> list[str]:
    return [f"{c.name} ({_format_pct_value(c.value)})" for c in contributions if c.value]


def format_guild_bonus_suffix_ru(lines: list[str]) -> str:
    if not lines:
        return ""
    return " (" + ", ".join(lines) + ")"


def guild_reward_bonus_dicts(contributions: list[GuildSkillContribution]) -> list[dict]:
    return [
        {"param": c.param, "name": c.name, "pct": round(float(c.value), 6)}
        for c in contributions
        if c.value
    ]


def apply_guild_solo_reward_mults(
    gfx: dict[str, float],
) -> tuple[float, float, list[GuildSkillContribution]]:
    """Returns (gold_mult_factor, exp_mult_factor, contributions for logging)."""
    gold_contribs: list[GuildSkillContribution] = []
    exp_contribs: list[GuildSkillContribution] = []
    gold_add = 0.0
    exp_add = 0.0
    for param in ("monster_gold_pct", "global_reward_pct"):
        v = float(gfx.get(param, 0) or 0)
        if v:
            gold_add += v
            gold_contribs.append(
                GuildSkillContribution(param=param, name=_skill_label(param), value=v)
            )
    for param in ("dungeon_exp_pct", "global_reward_pct"):
        v = float(gfx.get(param, 0) or 0)
        if v:
            exp_add += v
            exp_contribs.append(
                GuildSkillContribution(param=param, name=_skill_label(param), value=v)
            )
    seen: set[str] = set()
    merged: list[GuildSkillContribution] = []
    for c in gold_contribs + exp_contribs:
        if c.param in seen:
            continue
        seen.add(c.param)
        merged.append(c)
    return 1.0 + gold_add, 1.0 + exp_add, merged


async def _levels_map(session: AsyncSession, guild_id: int) -> dict[int, int]:
    q = await session.execute(
        select(GuildSkillLevelRow).where(GuildSkillLevelRow.guild_id == guild_id)
    )
    return {r.skill_definition_id: int(r.current_level or 0) for r in q.scalars()}


async def guild_skill_contributions(
    session: AsyncSession,
    player_id: int,
    *,
    params: set[str] | None = None,
) -> list[GuildSkillContribution]:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem:
        return []
    return await guild_skill_contributions_for_guild(session, int(mem.guild_id), params=params)


async def guild_skill_contributions_for_guild(
    session: AsyncSession,
    guild_id: int,
    *,
    params: set[str] | None = None,
) -> list[GuildSkillContribution]:
    guild = await session.get(Guild, guild_id)
    if not guild:
        return []
    thr = await session.get(GuildLevelThreshold, int(guild.level))
    skill_tier_unlock = int(thr.skill_tier_unlock) if thr else 1
    lv_map = await _levels_map(session, guild_id)
    defs = (
        await session.execute(select(GuildSkillDefinition).order_by(GuildSkillDefinition.sort_order))
    ).scalars().all()
    out: list[GuildSkillContribution] = []
    glvl = int(guild.level)
    for d in defs:
        key = str(d.effect_param)
        if params is not None and key not in params:
            continue
        if glvl < int(d.guild_level_req):
            continue
        if int(d.tier) > skill_tier_unlock:
            continue
        cl = lv_map.get(int(d.id), 0)
        if cl <= 0:
            continue
        vals = list(d.effect_per_level or [])
        idx = min(cl, 3) - 1
        if idx < 0 or idx >= len(vals):
            continue
        try:
            v = float(vals[idx])
        except (TypeError, ValueError):
            continue
        if not v:
            continue
        out.append(GuildSkillContribution(param=key, name=_skill_label(key, d.name), value=v))
    return out


async def effect_values_for_guild(session: AsyncSession, guild_id: int) -> dict[str, float]:
    contribs = await guild_skill_contributions_for_guild(session, guild_id)
    out: dict[str, float] = {}
    for c in contribs:
        key = c.param
        if key in _STACK_PCT:
            out[key] = out.get(key, 0.0) + c.value
        else:
            out[key] = out.get(key, 0.0) + c.value
    return out


async def effective_max_bank_items(session: AsyncSession, guild_id: int, base: int) -> int:
    fx = await effect_values_for_guild(session, guild_id)
    bonus = int(fx.get("bank_slots_bonus", 0) or 0)
    return max(0, int(base) + bonus)


def apply_price_discount_pct(cost: int, discount_pct: float) -> int:
    if cost <= 0 or discount_pct <= 0:
        return int(cost)
    return max(1, int(round(int(cost) * (1.0 - float(discount_pct)))))


def apply_raid_gxp_guild_bonuses(base_gxp: int, gfx: dict[str, float]) -> int:
    """Apply Нерушимые узы (×mult) and Воля к победе (+pct) to raid GXP."""
    gxp = max(0, int(base_gxp))
    if gxp <= 0:
        return 0
    mult = float(gfx.get("raid_gxp_multiplier", 0) or 0)
    if mult > 0:
        gxp = max(1, int(round(gxp * mult)))
    pct = float(gfx.get("raid_completion_reward_pct", 0) or 0)
    if pct > 0:
        gxp = max(1, int(round(gxp * (1.0 + pct))))
    return gxp


async def count_guild_active_members(
    session: AsyncSession,
    guild_id: int,
    *,
    within_hours: float = 24.0,
) -> int:
    """Guild members with last_active within the given window (for Дух гильдии)."""
    from datetime import datetime, timedelta, timezone

    from waifu_bot.db.models import Player

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=float(within_hours))
    pids = (
        await session.execute(
            select(GuildMember.player_id).where(GuildMember.guild_id == int(guild_id))
        )
    ).scalars().all()
    cnt = 0
    for pid in pids:
        pl = await session.get(Player, int(pid))
        if not pl or not pl.last_active:
            continue
        la = pl.last_active
        la_utc = la.replace(tzinfo=timezone.utc) if la.tzinfo is None else la.astimezone(timezone.utc)
        if la_utc >= cutoff:
            cnt += 1
    return cnt


async def effect_values_for_player(session: AsyncSession, player_id: int) -> dict[str, float]:
    """effect_param -> additive contribution for stacking params (pct) or last-wins for scalars."""
    contribs = await guild_skill_contributions(session, player_id)
    out: dict[str, float] = {}
    for c in contribs:
        key = c.param
        if key in _STACK_PCT:
            out[key] = out.get(key, 0.0) + c.value
        else:
            out[key] = out.get(key, 0.0) + c.value
    return out


async def gd_party_damage_multiplier(session: AsyncSession, player_id: int) -> float:
    fx = await effect_values_for_player(session, player_id)
    return 1.0 + float(fx.get("gd_party_damage_pct", 0.0))


async def monster_gold_multiplier(session: AsyncSession, player_id: int) -> float:
    fx = await effect_values_for_player(session, player_id)
    return 1.0 + float(fx.get("monster_gold_pct", 0.0)) + float(fx.get("global_reward_pct", 0.0))


async def dungeon_exp_multiplier(session: AsyncSession, player_id: int) -> float:
    fx = await effect_values_for_player(session, player_id)
    return 1.0 + float(fx.get("dungeon_exp_pct", 0.0)) + float(fx.get("global_reward_pct", 0.0))

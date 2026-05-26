"""Resolved guild skill bonuses for a player (via their guild)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Guild, GuildLevelThreshold, GuildMember, GuildSkillDefinition, GuildSkillLevelRow


async def _levels_map(session: AsyncSession, guild_id: int) -> dict[int, int]:
    q = await session.execute(
        select(GuildSkillLevelRow).where(GuildSkillLevelRow.guild_id == guild_id)
    )
    return {r.skill_definition_id: int(r.current_level or 0) for r in q.scalars()}


async def effect_values_for_player(session: AsyncSession, player_id: int) -> dict[str, float]:
    """effect_param -> additive contribution for stacking params (pct) or last-wins for scalars."""
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem:
        return {}
    guild_id = int(mem.guild_id)
    guild = await session.get(Guild, guild_id)
    if not guild:
        return {}
    thr = await session.get(GuildLevelThreshold, int(guild.level))
    skill_tier_unlock = int(thr.skill_tier_unlock) if thr else 1

    lv_map = await _levels_map(session, guild_id)
    defs = (
        await session.execute(select(GuildSkillDefinition).order_by(GuildSkillDefinition.sort_order))
    ).scalars().all()
    out: dict[str, float] = {}
    glvl = int(guild.level)
    stack_pct = {
        "gd_party_damage_pct",
        "monster_gold_pct",
        "dungeon_exp_pct",
        "max_hp_pct",
        "global_reward_pct",
        "chat_reward_pct",
    }
    for d in defs:
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
        key = str(d.effect_param)
        if key in stack_pct:
            out[key] = out.get(key, 0.0) + v
        else:
            out[key] = out.get(key, 0.0) + v
    return out


async def gd_party_damage_multiplier(session: AsyncSession, player_id: int) -> float:
    fx = await effect_values_for_player(session, player_id)
    return 1.0 + float(fx.get("gd_party_damage_pct", 0.0))


async def monster_gold_multiplier(session: AsyncSession, player_id: int) -> float:
    fx = await effect_values_for_player(session, player_id)
    return 1.0 + float(fx.get("monster_gold_pct", 0.0))


async def dungeon_exp_multiplier(session: AsyncSession, player_id: int) -> float:
    fx = await effect_values_for_player(session, player_id)
    return 1.0 + float(fx.get("dungeon_exp_pct", 0.0))

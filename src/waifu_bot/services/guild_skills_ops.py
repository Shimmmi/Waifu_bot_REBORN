"""Guild skill tree: spend OPG, reset (leader only)."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Guild, GuildMember, GuildSkillDefinition, GuildSkillLevelRow, Player
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map


async def guild_skills_snapshot(session: AsyncSession, player_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem:
        return {"in_guild": False}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"in_guild": False}
    defs = (await session.execute(select(GuildSkillDefinition).order_by(GuildSkillDefinition.sort_order))).scalars().all()
    levels = (
        await session.execute(select(GuildSkillLevelRow).where(GuildSkillLevelRow.guild_id == guild.id))
    ).scalars().all()
    lm = {r.skill_definition_id: r.current_level for r in levels}
    avail = int(guild.skill_points_total) - int(guild.skill_points_spent)
    return {
        "in_guild": True,
        "is_leader": mem.is_leader,
        "is_officer": mem.is_officer,
        "guild_level": guild.level,
        "skill_points_total": guild.skill_points_total,
        "skill_points_spent": guild.skill_points_spent,
        "skill_points_available": max(0, avail),
        "definitions": [
            {
                "id": d.id,
                "name": d.name,
                "tier": d.tier,
                "effect_param": d.effect_param,
                "effect_per_level": list(d.effect_per_level or []),
                "guild_level_req": d.guild_level_req,
                "cost_sp": int(d.cost_sp),
                "cost_per_upgrade": int(d.cost_per_upgrade),
                "current_level": int(lm.get(d.id, 0)),
            }
            for d in defs
        ],
    }


async def guild_skill_upgrade(session: AsyncSession, player_id: int, skill_definition_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem or not mem.is_leader:
        return {"error": "leader_only"}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"error": "no_guild"}
    dfn = await session.get(GuildSkillDefinition, skill_definition_id)
    if not dfn or guild.level < int(dfn.guild_level_req):
        return {"error": "locked"}
    row = (
        await session.execute(
            select(GuildSkillLevelRow).where(
                GuildSkillLevelRow.guild_id == guild.id,
                GuildSkillLevelRow.skill_definition_id == skill_definition_id,
            )
        )
    ).scalar_one_or_none()
    cur = int(row.current_level) if row else 0
    if cur >= 3:
        return {"error": "max_level"}
    cost = int(dfn.cost_sp) if cur == 0 else int(dfn.cost_per_upgrade)
    avail = int(guild.skill_points_total) - int(guild.skill_points_spent)
    if avail < cost:
        return {"error": "no_skill_points"}
    if not row:
        row = GuildSkillLevelRow(guild_id=guild.id, skill_definition_id=skill_definition_id, current_level=0)
        session.add(row)
        await session.flush()
    row.current_level = cur + 1
    guild.skill_points_spent = int(guild.skill_points_spent) + cost
    from waifu_bot.services.guild_activity import log_skill_upgrade

    await log_skill_upgrade(session, guild.id, player_id, dfn.name)
    await session.commit()
    return {"success": True, "new_level": row.current_level, "spent": guild.skill_points_spent}


async def guild_skill_reset(session: AsyncSession, player_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem or not mem.is_leader:
        return {"error": "leader_only"}
    guild = await session.get(Guild, mem.guild_id)
    player = await session.get(Player, player_id)
    if not guild or not player:
        return {"error": "not_found"}
    cfg = await get_game_config_map(session)
    mult = cfg_int(cfg, "guild_skill.reset_gold_per_level", 500)
    cost = max(1, int(guild.level) * mult)
    if int(player.gold or 0) < cost:
        return {"error": "insufficient_gold", "required": cost}
    player.gold -= cost
    await session.execute(delete(GuildSkillLevelRow).where(GuildSkillLevelRow.guild_id == guild.id))
    guild.skill_points_spent = 0
    await session.commit()
    return {"success": True, "gold_spent": cost}

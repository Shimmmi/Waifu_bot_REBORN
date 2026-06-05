"""Guild skill tree: spend OPG, reset (leader only)."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    Guild,
    GuildLevelThreshold,
    GuildMember,
    GuildSkillDefinition,
    GuildSkillLevelRow,
    Player,
)
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map


def _upgrade_cost(dfn: GuildSkillDefinition, cur: int) -> int:
    if cur >= 3:
        return 0
    return int(dfn.cost_sp) if cur == 0 else int(dfn.cost_per_upgrade)


def _effective_leader(mem: GuildMember, member_count: int) -> bool:
    return bool(mem.is_leader) or int(member_count) == 1


def _skill_upgrade_gate(
    *,
    guild: Guild,
    is_leader: bool,
    dfn: GuildSkillDefinition,
    cur: int,
    skill_tier_unlock: int,
    avail: int,
) -> tuple[bool, str | None, int]:
    cost = _upgrade_cost(dfn, cur)
    if not is_leader:
        return False, "leader_only", cost
    if cur >= 3:
        return False, "max_level", cost
    if int(guild.level) < int(dfn.guild_level_req):
        return False, "locked", cost
    if int(dfn.tier) > int(skill_tier_unlock):
        return False, "tier_locked", cost
    if avail < cost:
        return False, "no_skill_points", cost
    return True, None, cost


async def _ensure_guild_leader(session: AsyncSession, mem: GuildMember) -> bool:
    if mem.is_leader:
        return True
    from waifu_bot.services.guild_leader_integrity import ensure_guild_has_leader

    if await ensure_guild_has_leader(session, int(mem.guild_id)):
        await session.refresh(mem)
    if mem.is_leader:
        return True
    cnt = await session.scalar(
        select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == mem.guild_id)
    )
    if int(cnt or 0) == 1:
        mem.is_leader = True
        await session.flush()
        return True
    return False


async def guild_skills_snapshot(session: AsyncSession, player_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem:
        return {"in_guild": False}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"in_guild": False}
    from waifu_bot.services.guild_leader_integrity import ensure_guild_has_leader

    if await ensure_guild_has_leader(session, int(guild.id)):
        await session.refresh(mem)
    member_count = int(
        await session.scalar(
            select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == guild.id)
        )
        or 0
    )
    thr = await session.get(GuildLevelThreshold, int(guild.level))
    skill_tier_unlock = int(thr.skill_tier_unlock) if thr else 1
    defs = (await session.execute(select(GuildSkillDefinition).order_by(GuildSkillDefinition.sort_order))).scalars().all()
    levels = (
        await session.execute(select(GuildSkillLevelRow).where(GuildSkillLevelRow.guild_id == guild.id))
    ).scalars().all()
    lm = {r.skill_definition_id: r.current_level for r in levels}
    avail = int(guild.skill_points_total) - int(guild.skill_points_spent)
    is_leader = _effective_leader(mem, member_count)
    definitions: list[dict] = []
    for d in defs:
        cur = int(lm.get(d.id, 0))
        can_up, block_reason, cost = _skill_upgrade_gate(
            guild=guild,
            is_leader=is_leader,
            dfn=d,
            cur=cur,
            skill_tier_unlock=skill_tier_unlock,
            avail=max(0, avail),
        )
        definitions.append(
            {
                "id": d.id,
                "name": d.name,
                "tier": d.tier,
                "effect_param": d.effect_param,
                "effect_per_level": list(d.effect_per_level or []),
                "guild_level_req": d.guild_level_req,
                "cost_sp": int(d.cost_sp),
                "cost_per_upgrade": int(d.cost_per_upgrade),
                "sort_order": int(d.sort_order or 0),
                "current_level": cur,
                "upgrade_cost": cost,
                "can_upgrade": can_up,
                "upgrade_block_reason": block_reason,
            }
        )
    return {
        "in_guild": True,
        "is_leader": is_leader,
        "is_officer": mem.is_officer,
        "guild_level": guild.level,
        "skill_tier_unlock": skill_tier_unlock,
        "skill_points_total": guild.skill_points_total,
        "skill_points_spent": guild.skill_points_spent,
        "skill_points_available": max(0, avail),
        "definitions": definitions,
    }


async def guild_skill_upgrade(session: AsyncSession, player_id: int, skill_definition_id: int) -> dict:
    mem = (await session.execute(select(GuildMember).where(GuildMember.player_id == player_id))).scalar_one_or_none()
    if not mem:
        return {"error": "leader_only"}
    if not await _ensure_guild_leader(session, mem):
        return {"error": "leader_only"}
    guild = await session.get(Guild, mem.guild_id)
    if not guild:
        return {"error": "no_guild"}
    dfn = await session.get(GuildSkillDefinition, skill_definition_id)
    if not dfn:
        return {"error": "locked"}
    thr = await session.get(GuildLevelThreshold, int(guild.level))
    skill_tier_unlock = int(thr.skill_tier_unlock) if thr else 1
    row = (
        await session.execute(
            select(GuildSkillLevelRow).where(
                GuildSkillLevelRow.guild_id == guild.id,
                GuildSkillLevelRow.skill_definition_id == skill_definition_id,
            )
        )
    ).scalar_one_or_none()
    cur = int(row.current_level) if row else 0
    avail = int(guild.skill_points_total) - int(guild.skill_points_spent)
    can_up, block_reason, cost = _skill_upgrade_gate(
        guild=guild,
        is_leader=True,
        dfn=dfn,
        cur=cur,
        skill_tier_unlock=skill_tier_unlock,
        avail=avail,
    )
    if not can_up:
        err = block_reason or "locked"
        payload: dict = {"error": err}
        if err == "no_skill_points":
            payload["required"] = cost
        return payload
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
    if not mem or not await _ensure_guild_leader(session, mem):
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

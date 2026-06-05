"""Ensure each guild has exactly one leader (founder preferred when repairing)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Guild, GuildMember


async def _guild_members(session: AsyncSession, guild_id: int) -> list[GuildMember]:
    return list(
        (
            await session.execute(
                select(GuildMember)
                .where(GuildMember.guild_id == guild_id)
                .order_by(GuildMember.joined_at.asc(), GuildMember.id.asc())
            )
        ).scalars().all()
    )


def _pick_leader_member(
    members: list[GuildMember],
    *,
    founder_player_id: int | None,
    prefer_player_id: int | None = None,
) -> GuildMember | None:
    if not members:
        return None
    if prefer_player_id is not None:
        for mem in members:
            if int(mem.player_id) == int(prefer_player_id):
                return mem
    if founder_player_id is not None:
        for mem in members:
            if int(mem.player_id) == int(founder_player_id):
                return mem
    return members[0]


async def _apply_leader(
    session: AsyncSession,
    guild_id: int,
    new_leader: GuildMember,
    *,
    actor_player_id: int | None,
) -> None:
    for mem in await _guild_members(session, guild_id):
        should_lead = int(mem.player_id) == int(new_leader.player_id)
        mem.is_leader = should_lead
        if should_lead:
            mem.is_officer = False
        elif mem.is_leader:
            mem.is_leader = False
    await session.flush()
    if actor_player_id is not None:
        from waifu_bot.services.guild_activity import log_member_rank_change

        await log_member_rank_change(
            session,
            guild_id,
            int(actor_player_id),
            int(new_leader.player_id),
            "Глава",
        )


async def ensure_guild_has_leader(session: AsyncSession, guild_id: int) -> bool:
    """Repair missing or duplicate leaders. Returns True if DB rows were changed."""
    members = await _guild_members(session, guild_id)
    if not members:
        return False

    leaders = [m for m in members if m.is_leader]
    if len(leaders) == 1:
        return False

    guild = await session.get(Guild, guild_id)
    founder_id = int(guild.founder_player_id) if guild and guild.founder_player_id else None

    if len(leaders) > 1:
        keep = _pick_leader_member(leaders, founder_player_id=founder_id)
        if keep is None:
            keep = leaders[0]
        for mem in members:
            mem.is_leader = int(mem.player_id) == int(keep.player_id)
            if mem.is_leader:
                mem.is_officer = False
        await session.flush()
        return True

    # Zero leaders: promote founder if present, else earliest joined member.
    pick = _pick_leader_member(members, founder_player_id=founder_id)
    if pick is None:
        return False
    pick.is_leader = True
    pick.is_officer = False
    await session.flush()
    return True


async def restore_founder_leadership(
    session: AsyncSession,
    guild_id: int,
    *,
    actor_player_id: int | None = None,
) -> dict:
    """Force leadership to founder_player_id when still a member."""
    guild = await session.get(Guild, guild_id)
    if not guild:
        return {"error": "guild_not_found"}
    if not guild.founder_player_id:
        return {"error": "founder_not_set"}

    founder_id = int(guild.founder_player_id)
    members = await _guild_members(session, guild_id)
    founder_mem = next((m for m in members if int(m.player_id) == founder_id), None)
    if not founder_mem:
        return {"error": "founder_not_in_guild"}

    previous_leader_id = None
    for mem in members:
        if mem.is_leader:
            previous_leader_id = int(mem.player_id)
            break

    if previous_leader_id == founder_id and founder_mem.is_leader:
        return {
            "success": True,
            "previous_leader_id": previous_leader_id,
            "new_leader_id": founder_id,
            "changed": False,
        }

    await _apply_leader(
        session,
        guild_id,
        founder_mem,
        actor_player_id=actor_player_id or founder_id,
    )
    return {
        "success": True,
        "previous_leader_id": previous_leader_id,
        "new_leader_id": founder_id,
        "changed": True,
    }


async def leader_count(session: AsyncSession, guild_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(GuildMember)
            .where(GuildMember.guild_id == guild_id, GuildMember.is_leader.is_(True))
        )
        or 0
    )

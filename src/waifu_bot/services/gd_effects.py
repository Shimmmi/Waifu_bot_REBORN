"""GD v1: persist combat effects in gd_active_effects (single source of truth)."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GDActiveEffect


def _append_fx(fx_list: list[GDActiveEffect] | None, row: GDActiveEffect) -> None:
    if fx_list is not None:
        fx_list.append(row)


async def purge_expired_before_round(session: AsyncSession, cycle_id: int, round_num: int) -> None:
    """Remove effects that ended before this round (expires_round < round_num)."""
    await session.execute(
        delete(GDActiveEffect).where(
            GDActiveEffect.cycle_id == cycle_id,
            GDActiveEffect.expires_round < round_num,
        )
    )


async def delete_monster_targeted_effects(session: AsyncSession, cycle_id: int) -> None:
    """On trash wave cleared: remove all monster-target debuffs/buffs."""
    await session.execute(
        delete(GDActiveEffect).where(
            GDActiveEffect.cycle_id == cycle_id,
            GDActiveEffect.target_type == "monster",
        )
    )


async def load_effects(session: AsyncSession, cycle_id: int, round_num: int) -> list[GDActiveEffect]:
    """Effects still active during round_num."""
    r = await session.execute(
        select(GDActiveEffect).where(
            GDActiveEffect.cycle_id == cycle_id,
            GDActiveEffect.expires_round >= round_num,
        )
    )
    return list(r.scalars().all())


async def add_effect(
    session: AsyncSession,
    cycle_id: int,
    target_type: str,
    target_id: int,
    effect_type: str,
    effect_value: float,
    expires_round: int,
    source_user_id: int | None = None,
    applied_round: int = 0,
    fx_list: list[GDActiveEffect] | None = None,
) -> GDActiveEffect:
    row = GDActiveEffect(
        cycle_id=cycle_id,
        target_type=target_type,
        target_id=target_id,
        effect_type=effect_type,
        effect_value=effect_value,
        expires_round=expires_round,
        applied_round=applied_round,
        source_user_id=source_user_id,
    )
    session.add(row)
    _append_fx(fx_list, row)
    return row

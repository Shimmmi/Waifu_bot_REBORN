"""Compact client snapshots + stage account debug."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.game.economy import ECONOMY_ACTIVITY, ECONOMY_TELEGRAM
from waifu_bot.services.client_snapshots import get_or_build_client_snapshot

router = APIRouter(tags=["client-snapshot"])


@router.get("/client-snapshot")
async def client_snapshot(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    force: bool = Query(False),
):
    try:
        return await get_or_build_client_snapshot(session, player_id, force=force)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/debug/account/{target_player_id}")
async def debug_account(
    target_player_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Stage/dev only: inspect identity + main_waifu + inventory bag counts."""
    env = (settings.environment or "").strip().lower()
    if env not in ("stage", "dev", "testing"):
        raise HTTPException(status_code=404, detail="not_found")
    # Allow self-debug always; admins can inspect others.
    if target_player_id != player_id and player_id not in (settings.admin_ids or []):
        raise HTTPException(status_code=403, detail="forbidden")

    player = (
        await session.execute(
            select(m.Player)
            .options(selectinload(m.Player.main_waifu))
            .where(m.Player.id == target_player_id)
        )
    ).scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="player_not_found")

    links = (
        await session.execute(
            select(m.PlayerIdentityLink).where(m.PlayerIdentityLink.player_id == target_player_id)
        )
    ).scalars().all()

    async def _inv_count(economy: str) -> int:
        n = await session.scalar(
            select(func.count())
            .select_from(m.InventoryItem)
            .where(
                m.InventoryItem.player_id == target_player_id,
                m.InventoryItem.economy == economy,
            )
        )
        return int(n or 0)

    activity = await session.get(m.ActivityInputState, target_player_id)
    mw = player.main_waifu
    return {
        "player_id": player.id,
        "username": player.username,
        "gold": int(player.gold or 0),
        "current_act": int(player.current_act or 1),
        "max_act": int(player.max_act or 1),
        "has_main_waifu": mw is not None,
        "main_waifu": (
            {"id": mw.id, "name": mw.name, "level": int(mw.level or 1)} if mw else None
        ),
        "identity_links": [
            {"provider": ln.provider, "external_id": ln.external_id} for ln in links
        ],
        "inventory_counts": {
            ECONOMY_TELEGRAM: await _inv_count(ECONOMY_TELEGRAM),
            ECONOMY_ACTIVITY: await _inv_count(ECONOMY_ACTIVITY),
        },
        "activity_input": {
            "buffer_units": int(activity.buffer_units or 0) if activity else 0,
            "last_counter": int(activity.last_counter) if activity and activity.last_counter is not None else None,
            "units_accepted_today": int(activity.units_accepted_today or 0) if activity else 0,
            "day_utc": activity.day_utc if activity else None,
            "last_claim_at": activity.last_claim_at.isoformat() if activity and activity.last_claim_at else None,
        },
        "note": (
            "Staging DB is separate from prod. Telegram OIDC uses Player.id = telegram user id; "
            "missing main_waifu means character was never created on this DB."
        ),
    }

"""REST API for the Abyss (Бездна) mode.

Combat itself runs through the bot message handler, so there is no `/attack`
endpoint here — these routes drive the lobby, session lifecycle, Grace choice
and (stage 1) the leaderboard / shards shop / revive scroll.
"""
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.services import abyss_service as absvc
from waifu_bot.services.abyss_service import AbyssService
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/abyss", tags=["abyss"])

abyss_service = AbyssService()


class GraceChooseBody(BaseModel):
    grace_id: int


class ShopBuyBody(BaseModel):
    item_id: int


# ---------------------------------------------------------------------------
# Stage 0
# ---------------------------------------------------------------------------

@router.get("/status")
async def abyss_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await abyss_service.get_status(session, player_id)


@router.post("/enter")
async def abyss_enter(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await abyss_service.enter(session, player_id)


@router.post("/exit")
async def abyss_exit(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await abyss_service.exit_abyss(session, player_id)


@router.post("/grace/choose")
async def abyss_grace_choose(
    body: GraceChooseBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await abyss_service.choose_grace(session, player_id, int(body.grace_id))


# ---------------------------------------------------------------------------
# Stage 1: leaderboard, shop, revive
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def abyss_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    ws = absvc.week_start_msk()
    rows = (
        await session.execute(
            select(m.AbyssWeeklyLeaderboard, m.Player)
            .join(m.Player, m.Player.id == m.AbyssWeeklyLeaderboard.player_id, isouter=True)
            .where(m.AbyssWeeklyLeaderboard.week_start == ws)
            .order_by(m.AbyssWeeklyLeaderboard.max_floor.desc())
            .limit(limit)
        )
    ).all()

    entries = []
    my_rank = None
    for idx, (lb, player) in enumerate(rows, start=1):
        name = None
        if player is not None:
            name = player.username or player.first_name or f"Игрок {player.id}"
        is_me = int(lb.player_id) == int(player_id)
        if is_me:
            my_rank = idx
        entries.append({
            "rank": idx,
            "player_id": int(lb.player_id),
            "name": name or f"Игрок {lb.player_id}",
            "max_floor": int(lb.max_floor or 0),
            "is_me": is_me,
        })

    if my_rank is None:
        mine = await session.scalar(
            select(m.AbyssWeeklyLeaderboard).where(
                m.AbyssWeeklyLeaderboard.week_start == ws,
                m.AbyssWeeklyLeaderboard.player_id == player_id,
            )
        )
        if mine is not None:
            higher = await session.scalar(
                select(m.AbyssWeeklyLeaderboard.id).where(
                    m.AbyssWeeklyLeaderboard.week_start == ws,
                    m.AbyssWeeklyLeaderboard.max_floor > int(mine.max_floor or 0),
                ).order_by(m.AbyssWeeklyLeaderboard.id)
            )
            # Count higher entries properly.
            from sqlalchemy import func as _f

            cnt = await session.scalar(
                select(_f.count()).select_from(m.AbyssWeeklyLeaderboard).where(
                    m.AbyssWeeklyLeaderboard.week_start == ws,
                    m.AbyssWeeklyLeaderboard.max_floor > int(mine.max_floor or 0),
                )
            )
            my_rank = int(cnt or 0) + 1

    return {"week_start": ws.isoformat(), "entries": entries, "my_rank": my_rank}


@router.get("/shop")
async def abyss_shop(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    progress = await absvc.get_or_create_progress(session, player_id)
    max_floor = int(progress.max_floor_reached or 0)
    shards = int(progress.abyss_shards or 0)
    rows = (
        await session.execute(
            select(m.AbyssShardsShopItem)
            .where(m.AbyssShardsShopItem.is_active.is_(True))
            .order_by(m.AbyssShardsShopItem.cost_shards)
        )
    ).scalars().all()
    items = []
    for it in rows:
        unlocked = max_floor >= int(it.min_floor_req or 0)
        items.append({
            "id": it.id,
            "name": it.name,
            "description": it.description,
            "icon": it.icon,
            "item_type": it.item_type,
            "cost_shards": int(it.cost_shards),
            "min_floor_req": int(it.min_floor_req or 0),
            "unlocked": unlocked,
            "affordable": unlocked and shards >= int(it.cost_shards),
        })
    await session.commit()
    return {"abyss_shards": shards, "items": items}


@router.post("/shop/buy")
async def abyss_shop_buy(
    body: ShopBuyBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    progress = await absvc.get_progress_for_update(session, player_id)
    if progress is None:
        await session.commit()
        return {"success": False, "error": "NO_PROGRESS"}
    item = await session.get(m.AbyssShardsShopItem, int(body.item_id))
    if item is None or not item.is_active:
        await session.commit()
        return {"success": False, "error": "INVALID_ITEM"}
    if int(progress.max_floor_reached or 0) < int(item.min_floor_req or 0):
        await session.commit()
        return {"success": False, "error": "LOCKED"}
    if int(progress.abyss_shards or 0) < int(item.cost_shards):
        await session.commit()
        return {"success": False, "error": "INSUFFICIENT_SHARDS"}

    progress.abyss_shards = int(progress.abyss_shards or 0) - int(item.cost_shards)
    await session.commit()
    return {
        "success": True,
        "abyss_shards": int(progress.abyss_shards or 0),
        "purchased": {"id": item.id, "name": item.name, "item_type": item.item_type},
    }


@router.post("/revive")
async def abyss_revive(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    cfg = await get_game_config_map(session)
    progress = await absvc.get_progress_for_update(session, player_id)
    if progress is None or not progress.session_active:
        await session.commit()
        return {"success": False, "error": "NOT_IN_SESSION"}
    waifu = await absvc.get_waifu(session, player_id)
    if waifu is None:
        await session.commit()
        return {"success": False, "error": "NO_WAIFU"}
    if int(waifu.current_hp or 0) > 0:
        await session.commit()
        return {"success": False, "error": "NOT_UNCONSCIOUS"}

    max_uses = cfg_int(cfg, "abyss_revive_scroll_max_per_block", 1)
    if int(progress.revive_scrolls_used_this_block or 0) >= max_uses:
        await session.commit()
        return {"success": False, "error": "LIMIT_REACHED"}

    cost = cfg_int(cfg, "abyss_revive_scroll_cost", 50)
    if int(progress.abyss_shards or 0) < cost:
        await session.commit()
        return {"success": False, "error": "INSUFFICIENT_SHARDS", "cost": cost}

    progress.abyss_shards = int(progress.abyss_shards or 0) - cost
    progress.revive_scrolls_used_this_block = int(progress.revive_scrolls_used_this_block or 0) + 1
    from datetime import datetime, timezone

    waifu.current_hp = int(waifu.max_hp or 0)
    waifu.hp_updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {
        "success": True,
        "abyss_shards": int(progress.abyss_shards or 0),
        "waifu_hp": int(waifu.current_hp or 0),
        "waifu_max_hp": int(waifu.max_hp or 0),
    }

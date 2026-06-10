import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.api.deps import get_db, get_player_id, require_admin
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from waifu_bot.services.shop import ShopService, shop_size_for_act
from waifu_bot.services.gamble import GambleService
from waifu_bot.services.expedition_events_ai import generate_shop_merchant_line
from waifu_bot.services.llm_client import has_llm_configured
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map
from waifu_bot.services.passive_skills import apply_passive_buy_price
from waifu_bot.services.item_art import enrich_items_with_image_urls
from waifu_bot.services.inventory_payload import build_inventory_payloads
from waifu_bot.game.msk_time import msk_next_midnight_utc_iso

logger = logging.getLogger(__name__)

router = APIRouter()

shop_service = ShopService()
gamble_service = GambleService()


def _to_item(item: m.Item) -> schemas.ItemOut:
    return schemas.ItemOut(
        id=item.id,
        name=item.name,
        rarity=item.rarity,
        tier=item.tier,
        level=item.level,
        item_type=item.item_type,
        damage=item.damage,
        attack_speed=item.attack_speed,
        weapon_type=item.weapon_type,
        attack_type=item.attack_type,
        base_value=item.base_value,
        is_legendary=item.is_legendary,
        affixes=item.affixes,
    )


@router.get("/shop/inventory", tags=["shop"])
async def get_shop_inventory(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    size = shop_size_for_act(act)
    items = await shop_service.get_shop_inventory(session, act, size=size, player_id=player_id)
    await session.commit()
    return schemas.ShopInventoryResponse(
        items=items, count=len(items), size=size, refresh_at=msk_next_midnight_utc_iso()
    )


@router.post("/shop/merchant-line", tags=["shop"])
async def get_shop_merchant_line(
    request: Request,
    _: int = Depends(get_player_id),
):
    """
    Generate AI merchant recommendation line for current shop assortment (OpenRouter).
    Логи: смотри [shop merchant-line] в логах приложения.
    """
    payload = await request.json()
    item_name = str(payload.get("name") or "предмет")
    item_level = int(payload.get("level") or 1)
    item_rarity = str(payload.get("rarity") or "обычная")
    item_bonuses = str(payload.get("bonuses") or "").strip()
    line_context = str(payload.get("context") or "buy").strip().lower()
    text = await generate_shop_merchant_line(
        item_name=item_name,
        item_level=item_level,
        item_rarity=item_rarity,
        item_bonuses=item_bonuses,
        context=line_context,
    )
    out = {"text": text}
    if text is None:
        if not has_llm_configured():
            out["error"] = "OPENROUTER_API_KEY или ROUTERAI_API_KEY не задан в .env"
        else:
            out["error"] = "LLM не вернул текст (см. логи приложения [shop merchant-line])"
    return out


@router.post("/shop/buy", tags=["shop"])
async def buy_item(
    act: int = Query(..., ge=1, le=5),
    slot: int = Query(..., ge=1, le=12),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.buy_item(session, player_id, act, slot)
    if result.get("error"):
        err = result["error"]
        if err == "insufficient_gold":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Недостаточно золота. Нужно {result.get('required')}, у вас {result.get('have')}",
            )
        if err == "no_waifu":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Сначала создайте вайфу")
        if err == "already_purchased":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_purchased")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оффер не найден")
    return result


@router.post("/shop/buy-protection-stone", tags=["shop"])
async def buy_protection_stone(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(m.Player, player_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    cfg = await get_game_config_map(session)
    price = int(cfg_float(cfg, "enchant.stone_shop_price", 5000))
    price = await apply_passive_buy_price(session, player_id, price)
    if int(player.gold or 0) < price:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"insufficient_gold need {price} have {int(player.gold or 0)}",
        )
    player.gold = int(player.gold or 0) - price
    player.protection_stones = int(getattr(player, "protection_stones", 0) or 0) + 1
    await session.commit()
    return {
        "success": True,
        "gold_remaining": player.gold,
        "protection_stones": player.protection_stones,
        "price_paid": price,
    }


@router.post("/shop/sell", tags=["shop"])
async def sell_item(
    inventory_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.sell_item(session, player_id, inventory_item_id)
    if result.get("item_id"):
        item = await session.get(m.Item, result["item_id"])
        if item:
            result["item"] = _to_item(item)
    return schemas.BuySellResponse(**result)


@router.post("/shop/gamble", tags=["shop"])
async def gamble(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.gamble(session, player_id, act)
    if result.get("success") and result.get("inventory_item_id") is not None:
        iid = int(result["inventory_item_id"])
        try:
            inv = await session.get(
                m.InventoryItem,
                iid,
                options=[
                    selectinload(m.InventoryItem.item),
                    selectinload(m.InventoryItem.affixes),
                ],
            )
            if inv is None:
                logger.warning(
                    "shop/gamble: inventory_items.id=%s not found after commit (player_id=%s)",
                    iid,
                    player_id,
                )
            elif int(inv.player_id) != int(player_id):
                logger.warning(
                    "shop/gamble: item %s belongs to player %s, expected %s",
                    iid,
                    inv.player_id,
                    player_id,
                )
            else:
                rows = await build_inventory_payloads(session, [inv])
                item_payload = rows[0] if rows else {}
                try:
                    await enrich_items_with_image_urls(session, [item_payload])
                except Exception:
                    pass
                result["item"] = item_payload
        except Exception:
            logger.exception("shop/gamble: failed to build item payload for inventory_items.id=%s", iid)
    return result


@router.get("/shop/gamble/offers", tags=["shop"])
async def gamble_offers(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    offers = await gamble_service.get_personal_offers(session, player_id, act)
    return {"offers": offers, "size": GambleService.SIZE, "refresh_at": msk_next_midnight_utc_iso()}


@router.post("/shop/gamble/buy", tags=["shop"])
async def gamble_buy_slot(
    act: int = Query(..., ge=1, le=5),
    slot: int = Query(..., ge=1, le=12),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await gamble_service.buy_slot(session, player_id, act, slot)
    if result.get("error") == "insufficient_gold":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Недостаточно золота. Нужно {result.get('required')}, у вас {result.get('have')}",
        )
    if result.get("error") == "already_purchased":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already_purchased")
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="offer_not_found")
    if result.get("success") and result.get("inventory_item_id") is not None:
        iid = int(result["inventory_item_id"])
        try:
            inv = await session.get(
                m.InventoryItem,
                iid,
                options=[
                    selectinload(m.InventoryItem.item),
                    selectinload(m.InventoryItem.affixes),
                ],
            )
            if inv and int(inv.player_id) == int(player_id):
                rows = await build_inventory_payloads(session, [inv])
                item_payload = rows[0] if rows else {}
                try:
                    await enrich_items_with_image_urls(session, [item_payload])
                except Exception:
                    pass
                result["item"] = item_payload
        except Exception:
            logger.exception("shop/gamble/buy: failed to build item payload for id=%s", iid)
    return result


@router.post("/shop/refresh", tags=["shop"])
async def refresh_shop_inventory(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    _: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    size = shop_size_for_act(act)
    offers = await shop_service.refresh_offers(session, player_id, act, size=size)
    return {"refreshed": len(offers)}


@router.get("/shop/refresh", tags=["shop"])
async def refresh_shop_inventory_get(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    _: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    size = shop_size_for_act(act)
    offers = await shop_service.refresh_offers(session, player_id, act, size=size)
    return {"refreshed": len(offers)}

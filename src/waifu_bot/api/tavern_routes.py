import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.game.constants import TAVERN_HIRE_COST, TAVERN_SLOTS_PER_DAY
from waifu_bot.services.expedition_events_ai import generate_tavern_keeper_banter
from waifu_bot.services.narrative import build_narrative_prompt_context
from waifu_bot.services.passive_skills import compute_tavern_hire_price
from waifu_bot.services.tavern import TavernService

logger = logging.getLogger(__name__)

router = APIRouter()

tavern_service = TavernService()


def _tavern_perks_for_response():
    """Список перков для ответа таверны (избегаем 404 от отдельного /expeditions/perks)."""
    from waifu_bot.game.expedition_data import PERKS

    return [
        schemas.ExpeditionPerkOut(id=p.id, name=p.name, counters=list(p.counters), category=p.category)
        for p in PERKS
    ]


def _hired_waifu_in_squad(w: m.HiredWaifu) -> bool:
    pos = getattr(w, "squad_position", None)
    if pos is None:
        return False
    try:
        p = int(pos)
    except (TypeError, ValueError):
        return False
    return 1 <= p <= 6


def _hired_waifu_status(w: m.HiredWaifu) -> Literal["expedition", "wounded", "squad", "ready"]:
    if getattr(w, "expedition_id", None):
        return "expedition"
    max_hp = max(1, int(getattr(w, "max_hp", 65) or 1))
    cur = int(getattr(w, "current_hp", max_hp) or 0)
    if max_hp > 0 and cur / max_hp < 0.3:
        return "wounded"
    if _hired_waifu_in_squad(w):
        return "squad"
    return "ready"


def _to_hired_waifu(w: m.HiredWaifu) -> schemas.HiredWaifuOut:
    image_url = None
    if getattr(w, "image_data", None):
        mime = getattr(w, "image_mime", None) or "image/webp"
        image_url = f"data:{mime};base64,{w.image_data}"
    return schemas.HiredWaifuOut(
        id=w.id,
        name=w.name,
        race=w.race,
        class_=w.class_,
        rarity=w.rarity,
        level=w.level,
        experience=w.experience,
        power=getattr(w, "power", None),
        perks=getattr(w, "perks", None),
        bio=getattr(w, "bio", None),
        perk_upgrade_points=getattr(w, "perk_upgrade_points", 0),
        exp_current=getattr(w, "exp_current", 0),
        perk_levels=dict(getattr(w, "perk_levels", None) or {}),
        squad_position=w.squad_position,
        expedition_id=getattr(w, "expedition_id", None),
        in_squad=_hired_waifu_in_squad(w),
        status=_hired_waifu_status(w),
        image_url=image_url,
        current_hp=getattr(w, "current_hp", 65),
        max_hp=getattr(w, "max_hp", 65),
    )


@router.get("/tavern/available", response_model=schemas.TavernAvailableResponse, tags=["tavern"])
async def tavern_available(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        slots = await tavern_service.get_available_waifus(session, player_id)
    except SQLAlchemyError:
        slots = []
    hire_price = int(await compute_tavern_hire_price(session, player_id, TAVERN_HIRE_COST))
    out = []
    for s in slots:
        out.append(
            schemas.TavernHireSlotOut(
                slot=int(s.slot),
                available=s.hired_at is None,
                price=hire_price,
                hired_waifu_id=int(s.hired_waifu_id) if s.hired_waifu_id is not None else None,
            )
        )
    remaining = sum(1 for s in slots if s.hired_at is None)
    return schemas.TavernAvailableResponse(
        slots=out,
        remaining=int(remaining),
        total=int(TAVERN_SLOTS_PER_DAY),
        price=hire_price,
        perks=_tavern_perks_for_response(),
    )


@router.post("/tavern/keeper-banter", tags=["tavern"])
async def tavern_keeper_banter(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """ИИ-реплика тавернщика (слухи, быт); тот же канон, что у каравана."""
    player = await session.get(m.Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="player_not_found")
    narrative_context = await build_narrative_prompt_context(session, player_id)
    hired_n = await session.scalar(
        select(func.count()).select_from(m.HiredWaifu).where(m.HiredWaifu.player_id == player_id)
    )
    tavern_facts = {"hired_waifus_total": int(hired_n or 0)}
    text = await generate_tavern_keeper_banter(
        current_act=int(player.current_act or 1),
        max_act=int(player.max_act or 1),
        gold=int(player.gold or 0),
        narrative_context=narrative_context,
        tavern_facts=tavern_facts,
    )
    out: dict = {"text": text}
    if text is None:
        if not getattr(settings, "openrouter_api_key", None):
            out["error"] = "OPENROUTER_API_KEY не задан в .env"
        else:
            out["error"] = "OpenRouter не вернул текст (см. логи [tavern keeper])"
    return out


@router.post("/tavern/hire", tags=["tavern"])
async def tavern_hire(
    slot: Optional[int] = Query(None, ge=1, le=4),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.hire_waifu(session, player_id, slot=slot)
    err = result.get("error")
    if err:
        if err == "insufficient_gold":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Недостаточно золота. Нужно {result.get('required')}, у вас {result.get('have')}",
            )
        if err == "reserve_full":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Запас переполнен")
        if err == "slot_taken":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот слот найма уже использован")
        if err == "slot_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Слоты найма не найдены")
        if err == "invalid_slot":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный слот")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return schemas.TavernActionResponse(**result)


@router.get("/tavern/squad", tags=["tavern"])
async def tavern_squad(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        squad = await tavern_service.get_squad(session, player_id)
        await session.commit()
        return {"squad": [_to_hired_waifu(w) for w in squad]}
    except Exception:
        logger.exception("tavern_squad failed for player %s", player_id)
        return {"squad": []}


@router.get("/tavern/reserve", tags=["tavern"])
async def tavern_reserve(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        reserve = await tavern_service.get_reserve(session, player_id)
        await session.commit()
        return {"reserve": [_to_hired_waifu(w) for w in reserve]}
    except Exception:
        logger.exception("tavern_reserve failed for player %s", player_id)
        return {"reserve": []}


@router.post("/tavern/squad/add", tags=["tavern"])
async def tavern_squad_add(
    waifu_id: int,
    slot: Optional[int] = Query(None, ge=1, le=6),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.add_to_squad(session, player_id, waifu_id, slot)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return schemas.TavernActionResponse(**result)


@router.post("/tavern/squad/remove", tags=["tavern"])
async def tavern_squad_remove(
    waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.remove_from_squad(session, player_id, waifu_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return schemas.TavernActionResponse(**result)


@router.post("/tavern/heal", tags=["tavern"])
async def tavern_heal(
    hired_waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.heal_waifu(session, player_id, hired_waifu_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.post("/tavern/upgrade-perk", tags=["tavern"])
async def tavern_upgrade_perk(
    waifu_id: int,
    perk_id: str,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Потратить очко улучшения перка на повышение уровня перка наёмницы."""
    result = await tavern_service.upgrade_perk(session, player_id, waifu_id, perk_id)
    err = result.get("error")
    if err:
        if err == "waifu_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Наёмница не найдена")
        if err == "perk_not_owned":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Наёмница не имеет этого перка")
        if err == "perk_unknown":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный перк")
        if err == "perk_max_level":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Перк уже максимального уровня ({result.get('level')})")
        if err == "insufficient_points":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Недостаточно очков: нужно {result.get('need')}, есть {result.get('have')}",
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return result


@router.post("/tavern/dismiss", tags=["tavern"])
async def tavern_dismiss(
    waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Уволить вайфу из запаса. Уровень сохранится для следующей нанятой (ТЗ)."""
    try:
        result = await tavern_service.dismiss_waifu(session, player_id, waifu_id)
    except SQLAlchemyError as e:
        logger.exception("tavern_dismiss failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tavern_storage_unavailable",
        )
    if result.get("error"):
        if result.get("error") == "waifu_in_squad":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("hint", "Сначала снимите вайфу с отряда в запас."),
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    return result

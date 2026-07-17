"""API routes for onboarding tutorial progress."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.services import tutorial as tutorial_svc

logger = logging.getLogger(__name__)

router = APIRouter()


def _state_response(raw: dict) -> schemas.TutorialStateResponse:
    return schemas.TutorialStateResponse(
        version=int(raw.get("version") or tutorial_svc.TUTORIAL_VERSION),
        completed=dict(raw.get("completed") or {}),
        skipped=bool(raw.get("skipped")),
        intro_reward_claimed=bool(raw.get("intro_reward_claimed")),
        shop_kit_claimed=bool(raw.get("shop_kit_claimed")),
    )


@router.get("/tutorial/state", response_model=schemas.TutorialStateResponse, tags=["tutorial"])
async def tutorial_state(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    state = await tutorial_svc.get_tutorial_state(session, player_id)
    return _state_response(state)


@router.post("/tutorial/complete", response_model=schemas.TutorialCompleteResponse, tags=["tutorial"])
async def tutorial_complete(
    body: schemas.TutorialStepRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    step_id = (body.step_id or "").strip()
    if not step_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="step_id_required")
    try:
        state, gold_reward = await tutorial_svc.complete_tutorial_step(session, player_id, step_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await session.commit()
    return schemas.TutorialCompleteResponse(
        tutorial=_state_response(state),
        gold_reward=gold_reward,
    )


@router.post("/tutorial/skip", response_model=schemas.TutorialStateResponse, tags=["tutorial"])
async def tutorial_skip(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    state = await tutorial_svc.skip_all_tutorials(session, player_id)
    await session.commit()
    return _state_response(state)


@router.post("/tutorial/reset", response_model=schemas.TutorialStateResponse, tags=["tutorial"])
async def tutorial_reset(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    state = await tutorial_svc.reset_tutorial_progress(session, player_id)
    await session.commit()
    return _state_response(state)


@router.post(
    "/tutorial/provision",
    response_model=schemas.TutorialProvisionResponse,
    tags=["tutorial"],
)
async def tutorial_provision(
    body: schemas.TutorialProvisionRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    kit_id = (body.kit_id or "").strip()
    if not kit_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="kit_id_required")
    try:
        result = await tutorial_svc.provision_tutorial_kit(session, player_id, kit_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await session.commit()
    return schemas.TutorialProvisionResponse(
        tutorial=_state_response(result["tutorial"]),
        gold_granted=int(result.get("gold_granted") or 0),
        dust_granted=int(result.get("dust_granted") or 0),
        sell_item_id=result.get("sell_item_id"),
        buy_hint=result.get("buy_hint"),
        already_claimed=bool(result.get("already_claimed")),
    )

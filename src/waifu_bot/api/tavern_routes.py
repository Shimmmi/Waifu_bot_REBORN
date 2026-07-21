import asyncio
import logging
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.game.constants import TAVERN_SLOTS_PER_DAY
from waifu_bot.services.expedition_events_ai import generate_tavern_keeper_banter
from waifu_bot.services.llm_client import has_text_llm_configured
from waifu_bot.services.narrative import build_narrative_prompt_context
from waifu_bot.services.tavern import TavernService, compute_effective_tavern_hire_price

logger = logging.getLogger(__name__)

router = APIRouter()

tavern_service = TavernService()


def _hired_waifu_in_squad(w: m.HiredWaifu) -> bool:
    pos = getattr(w, "squad_position", None)
    if pos is None:
        return False
    try:
        p = int(pos)
    except (TypeError, ValueError):
        return False
    return 1 <= p <= 6


def _hired_waifu_status(
    w: m.HiredWaifu, *, now=None
) -> Literal["expedition", "wounded", "squad", "ready", "healing"]:
    from datetime import datetime, timezone

    from waifu_bot.game.expedition_overhaul import is_healing

    now = now or datetime.now(tz=timezone.utc)
    if getattr(w, "expedition_id", None):
        return "expedition"
    if is_healing(w, now):
        return "healing"
    from waifu_bot.services.hired_waifu_state import effective_hired_hp

    cur, max_hp = effective_hired_hp(w, now)
    if max_hp > 0 and cur / max_hp < 0.3:
        return "wounded"
    if _hired_waifu_in_squad(w):
        return "squad"
    return "ready"


from waifu_bot.api.hired_waifu_media import hired_waifu_portrait_url


def _to_hired_waifu(w: m.HiredWaifu) -> schemas.HiredWaifuOut:
    from datetime import datetime, timezone

    from waifu_bot.services.expedition import exp_to_next_level_hired
    from waifu_bot.services.hired_waifu_state import hired_roster_payload

    now = datetime.now(tz=timezone.utc)
    hp_data = hired_roster_payload(w, now)
    image_url = hired_waifu_portrait_url(w)
    return schemas.HiredWaifuOut(
        id=w.id,
        name=w.name,
        race=w.race,
        class_=w.class_,
        rarity=w.rarity,
        level=w.level,
        experience=w.experience,
        power=hp_data.get("power") or getattr(w, "power", None),
        perks=getattr(w, "perks", None),
        bio=getattr(w, "bio", None),
        perk_upgrade_points=getattr(w, "perk_upgrade_points", 0),
        exp_current=getattr(w, "exp_current", 0),
        exp_to_next=exp_to_next_level_hired(max(1, int(w.level or 1))),
        perk_levels=dict(getattr(w, "perk_levels", None) or {}),
        squad_position=w.squad_position,
        expedition_id=getattr(w, "expedition_id", None),
        in_squad=_hired_waifu_in_squad(w),
        status=_hired_waifu_status(w, now=now),
        image_url=image_url,
        current_hp=hp_data["current_hp"],
        max_hp=hp_data["max_hp"],
        healing=bool(hp_data.get("healing")),
        heal_complete_at=hp_data.get("heal_complete_at"),
        eligible=bool(hp_data.get("eligible", True)),
    )


@router.get("/tavern/available", response_model=schemas.TavernAvailableResponse, tags=["tavern"])
async def tavern_available(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        slots, hire_price = await asyncio.gather(
            tavern_service.get_available_waifus(session, player_id),
            compute_effective_tavern_hire_price(session, player_id),
        )
    except SQLAlchemyError:
        slots = []
        hire_price = int(await compute_effective_tavern_hire_price(session, player_id))
    hire_price = int(hire_price)
    first_hire_free = hire_price == 0
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
        first_hire_free=first_hire_free,
    )


@router.get("/tavern/bgm/chats", tags=["tavern"])
async def tavern_bgm_chats(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Group chats where both the player and bot are present (for BGM player chat picker)."""
    from waifu_bot.services.tavern_audio import list_bgm_chats_for_player

    try:
        return await list_bgm_chats_for_player(session, player_id)
    except SQLAlchemyError:
        logger.exception("tavern_bgm_chats failed for player %s", player_id)
        return {"chats": [], "hint": "Не удалось загрузить список чатов."}


@router.get("/tavern/bgm/tracks", tags=["tavern"])
async def tavern_bgm_tracks(
    chat_id: Optional[int] = Query(None),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Cached group-chat audio tracks for tavern BGM (all chats or one chat)."""
    from waifu_bot.services.tavern_audio import list_tracks_for_player, list_tracks_for_player_chat

    try:
        if chat_id is not None:
            tracks = await list_tracks_for_player_chat(session, player_id, int(chat_id))
            if tracks is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="chat_not_allowed")
            return {"tracks": tracks}
        tracks = await list_tracks_for_player(session, player_id)
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_tracks failed for player %s", player_id)
        tracks = []
    return {"tracks": tracks}


class TavernBgmCreatePlaylistIn(BaseModel):
    chat_id: int
    name: str = Field(min_length=1, max_length=128)


class TavernBgmUpdatePlaylistIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    shuffle: bool | None = None
    repeat: str | None = None


class TavernBgmSetTracksIn(BaseModel):
    track_ids: list[int] = Field(default_factory=list)


class TavernBgmAddTrackIn(BaseModel):
    track_id: int


@router.get("/tavern/bgm/playlists", tags=["tavern"])
async def tavern_bgm_playlists(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import list_playlists_for_player

    try:
        return await list_playlists_for_player(session, player_id)
    except SQLAlchemyError:
        logger.exception("tavern_bgm_playlists failed for player %s", player_id)
        return {"playlists": [], "active_playlist_id": None}


@router.get("/tavern/bgm/playlists/active", tags=["tavern"])
async def tavern_bgm_active_playlist(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import get_active_playlist

    try:
        playlist = await get_active_playlist(session, player_id)
        return {"playlist": playlist}
    except SQLAlchemyError:
        logger.exception("tavern_bgm_active_playlist failed for player %s", player_id)
        return {"playlist": None}


@router.get("/tavern/bgm/playlists/{playlist_id}", tags=["tavern"])
async def tavern_bgm_playlist_detail(
    playlist_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import get_playlist_with_tracks

    try:
        playlist = await get_playlist_with_tracks(session, player_id, int(playlist_id))
        if playlist is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist_not_found")
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_playlist_detail failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.post("/tavern/bgm/playlists", tags=["tavern"])
async def tavern_bgm_create_playlist(
    body: TavernBgmCreatePlaylistIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import create_playlist

    try:
        playlist = await create_playlist(session, player_id, body.chat_id, body.name)
        if playlist is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="chat_not_allowed")
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_create_playlist failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.patch("/tavern/bgm/playlists/{playlist_id}", tags=["tavern"])
async def tavern_bgm_update_playlist(
    playlist_id: int,
    body: TavernBgmUpdatePlaylistIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import update_playlist

    try:
        playlist = await update_playlist(
            session,
            player_id,
            int(playlist_id),
            name=body.name,
            shuffle=body.shuffle,
            repeat=body.repeat,
        )
        if playlist is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist_not_found")
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_update_playlist failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.delete("/tavern/bgm/playlists/{playlist_id}", tags=["tavern"])
async def tavern_bgm_delete_playlist(
    playlist_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import delete_playlist

    try:
        ok = await delete_playlist(session, player_id, int(playlist_id))
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist_not_found")
        return {"ok": True}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_delete_playlist failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.put("/tavern/bgm/playlists/{playlist_id}/tracks", tags=["tavern"])
async def tavern_bgm_set_playlist_tracks(
    playlist_id: int,
    body: TavernBgmSetTracksIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import set_playlist_tracks

    try:
        playlist = await set_playlist_tracks(
            session, player_id, int(playlist_id), body.track_ids
        )
        if playlist is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="playlist_not_found_or_invalid_track",
            )
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_set_playlist_tracks failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.post("/tavern/bgm/playlists/{playlist_id}/tracks", tags=["tavern"])
async def tavern_bgm_add_playlist_track(
    playlist_id: int,
    body: TavernBgmAddTrackIn,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import add_track_to_playlist

    try:
        playlist = await add_track_to_playlist(
            session, player_id, int(playlist_id), body.track_id
        )
        if playlist is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="playlist_not_found_or_invalid_track",
            )
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_add_playlist_track failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.delete("/tavern/bgm/playlists/{playlist_id}/tracks/{track_id}", tags=["tavern"])
async def tavern_bgm_remove_playlist_track(
    playlist_id: int,
    track_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import remove_track_from_playlist

    try:
        playlist = await remove_track_from_playlist(
            session, player_id, int(playlist_id), int(track_id)
        )
        if playlist is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist_not_found")
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_remove_playlist_track failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.post("/tavern/bgm/playlists/{playlist_id}/activate", tags=["tavern"])
async def tavern_bgm_activate_playlist(
    playlist_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import set_active_playlist

    try:
        playlist = await set_active_playlist(session, player_id, int(playlist_id))
        if playlist is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist_not_found")
        return {"playlist": playlist}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("tavern_bgm_activate_playlist failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


@router.post("/tavern/bgm/upload", tags=["tavern"])
async def tavern_bgm_upload(
    file: UploadFile = File(...),
    chat_id: int = Form(...),
    duration: int | None = Form(default=None),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.tavern_audio import upload_chat_audio_from_web

    raw = await file.read()
    try:
        return await upload_chat_audio_from_web(
            session,
            player_id,
            int(chat_id),
            raw,
            file.filename,
            file.content_type,
            duration,
        )
    except ValueError as e:
        code = str(e)
        if code == "file_too_large":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": code},
            ) from e
        if code in ("chat_not_allowed", "empty_file", "invalid_audio_type"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code) from e
    except SQLAlchemyError:
        logger.exception("tavern_bgm_upload failed for player %s", player_id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="db_error") from None


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
        if not has_text_llm_configured():
            out["error"] = "ROUTERAI_API_KEY не задан в .env"
        else:
            out["error"] = "LLM не вернул текст (см. логи [tavern keeper])"
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


@router.get("/tavern/hired-waifus/{waifu_id}/portrait", tags=["tavern"])
async def hired_waifu_portrait(
    waifu_id: int,
    request: Request,
    variant: str = Query("full", description="full | thumb"),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Binary portrait for a hired waifu (avoids base64 in JSON list responses).

    Source portraits are stored at up to ~2 MB; we downscale/recode to webp and
    cache the result so the tavern squad page stays light. ``variant=thumb``
    returns a small list thumbnail, ``variant=full`` a larger detail image.
    """
    from fastapi.concurrency import run_in_threadpool

    from waifu_bot.services import portrait_render

    waifu = await session.get(m.HiredWaifu, waifu_id)
    if not waifu or int(waifu.player_id) != int(player_id):
        raise HTTPException(status_code=404, detail="Waifu not found")
    raw = getattr(waifu, "image_data", None)
    if not raw:
        raise HTTPException(status_code=404, detail="Portrait not available")

    variant = portrait_render.normalize_variant(variant)
    generated_at = getattr(waifu, "image_generated_at", None)
    version = generated_at.isoformat() if generated_at else str(len(raw))
    cache_key = f"{waifu_id}:{version}"
    etag = f'"{cache_key}:{variant}"'

    # Cheap revalidation: unchanged portrait + variant -> 304, no body transfer.
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=604800"})

    try:
        body, content_type = await run_in_threadpool(
            portrait_render.render_portrait, raw, variant=variant, cache_key=cache_key
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Invalid portrait data") from exc

    return Response(
        content=body,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=604800",
            "ETag": etag,
        },
    )


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
    """Deprecated: starts Rest (heal-over-time). Prefer auto-Rest after Operations."""
    result = await tavern_service.heal_waifu(session, player_id, hired_waifu_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    result["deprecated"] = True
    result["note"] = "Use auto-Rest after Operations; Arena is not blocked by Rest."
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

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.services import player_mail_service as mail_svc
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


class MailSendBody(BaseModel):
    recipient_player_id: int
    body_text: str | None = None
    gold_amount: int = 0
    inventory_item_id: int | None = None


def _mail_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    status_code = status.HTTP_400_BAD_REQUEST
    if code in ("mail_not_found",):
        status_code = status.HTTP_404_NOT_FOUND
    elif code in ("not_same_guild", "cannot_mail_self"):
        status_code = status.HTTP_403_FORBIDDEN
    return HTTPException(status_code=status_code, detail=code)


@router.get("/mail/inbox", tags=["mail"])
async def mail_inbox(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await mail_svc.list_inbox(session, player_id, limit=limit, offset=offset)


@router.get("/mail/unread-count", tags=["mail"])
async def mail_unread_count(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    count = await mail_svc.unread_count(session, player_id)
    return {"count": count}


@router.get("/mail/badge", tags=["mail"])
async def mail_badge(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await mail_svc.mail_badge(session, player_id)


@router.get("/mail/sent", tags=["mail"])
async def mail_sent(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return await mail_svc.list_sent(session, player_id, limit=limit, offset=offset)


@router.get("/mail/{mail_id}", tags=["mail"])
async def mail_detail(
    mail_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await mail_svc.get_mail(session, player_id, mail_id)
    except ValueError as e:
        raise _mail_error(e) from e


@router.post("/mail/send", tags=["mail"])
async def mail_send(
    body: MailSendBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await mail_svc.send_mail(
            session,
            player_id,
            int(body.recipient_player_id),
            body_text=body.body_text,
            gold_amount=int(body.gold_amount or 0),
            inventory_item_id=body.inventory_item_id,
        )
    except ValueError as e:
        raise _mail_error(e) from e


@router.post("/mail/{mail_id}/claim", tags=["mail"])
async def mail_claim(
    mail_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        return await mail_svc.claim_mail(session, player_id, mail_id)
    except ValueError as e:
        raise _mail_error(e) from e


@router.delete("/mail/{mail_id}", tags=["mail"])
async def mail_delete(
    mail_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        await mail_svc.delete_mail(session, player_id, mail_id)
        return {"success": True}
    except ValueError as e:
        raise _mail_error(e) from e

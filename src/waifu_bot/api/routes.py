import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from waifu_bot.core.config import settings
from waifu_bot.services.webhook import process_update

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_webhook_secret(x_webhook_secret: str = Header(..., alias="X-Webhook-Secret")) -> None:
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid secret")


@router.post("/webhook", tags=["telegram"])
async def telegram_webhook(request: Request, _: None = Depends(verify_webhook_secret)) -> dict:
    body = await request.json()
    await process_update(body)
    return {"ok": True}


@router.get("/sse/ping", tags=["sse"])
async def sse_ping() -> dict:
    return {"pong": True}


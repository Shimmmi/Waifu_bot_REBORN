"""410 Gone for legacy expedition / tavern hire / arena routes when Chronicle is on."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from waifu_bot.services.delve_flag import is_expedition_v3_enabled

LEGACY_EXACT = frozenset(
    {
        "/api/expeditions/catalog",
        "/api/expeditions/roster",
        "/api/expeditions/slots",
        "/api/expeditions/daily-slots",
        "/api/expeditions/active",
        "/api/expeditions/preview",
        "/api/expeditions/start",
        "/api/expeditions/claim",
        "/api/expeditions/perks",
        "/api/expeditions/affixes",
        "/api/expeditions/perks-v2",
        "/api/operations/perks",
        "/api/operations/board",
        "/api/operations/assist",
        "/api/tavern/available",
        "/api/tavern/hire",
        "/api/tavern/squad",
        "/api/tavern/reserve",
        "/api/tavern/heal",
        "/api/tavern/dismiss",
        "/api/tavern/upgrade-perk",
        "/api/tavern/keeper-banter",
        "/api/tavern/merc-status",
        "/api/tavern/debut-legendary",
        "/api/tavern/lineup",
        "/api/tavern/fodder-stars",
        "/api/tavern/convert-manual",
        "/api/tavern/apply-manual",
        "/api/tavern/perks",
        "/api/tavern/exchange",
        "/api/tavern/codex",
        "/api/arena/status",
        "/api/arena/opponents",
        "/api/arena/attack",
        "/api/arena/history",
    }
)

LEGACY_PREFIXES = (
    "/api/expeditions/",
    "/api/operations/",
    "/api/arena/",
    "/api/tavern/squad/",
    "/api/tavern/hired-waifus/",
    "/api/tavern/exchange/",
    "/api/tavern/gear/",
    "/api/tavern/debut",
)

KEEP_PREFIXES = ("/api/tavern/bgm", "/api/tavern/living")

CHRONICLE_PREFIXES = ("/api/chronicle",)

GONE = {
    "error": "expedition_legacy_removed",
    "redirect": "/webapp/dungeons.html?tab=expedition",
}


def is_legacy_expedition_path(path: str) -> bool:
    if any(path.startswith(p) for p in KEEP_PREFIXES):
        return False
    if path in LEGACY_EXACT:
        return True
    if path.startswith("/api/expeditions/") or path.startswith("/api/operations/") or path.startswith("/api/arena/"):
        return True
    for prefix in LEGACY_PREFIXES:
        if path.startswith(prefix):
            return True
    if path.startswith("/api/tavern/") and not path.startswith("/api/tavern/bgm") and not path.startswith("/api/tavern/living"):
        # leftover hire/squad endpoints
        if path in LEGACY_EXACT or any(path.startswith(p) for p in LEGACY_PREFIXES):
            return True
    if any(path == p or path.startswith(p + "/") for p in CHRONICLE_PREFIXES):
        return True
    return False


class ExpeditionLegacyGoneMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if is_expedition_v3_enabled() and is_legacy_expedition_path(request.url.path):
            return JSONResponse(status_code=410, content=GONE)
        return await call_next(request)

from pathlib import Path

import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from waifu_bot.api.routes import router as api_router
from waifu_bot.core.config import settings
from waifu_bot.core.logging import setup_logging
from waifu_bot.db.session import get_session, init_engine
from waifu_bot.services.webhook import setup_webhook, start_polling, stop_polling, get_update_mode, log_bot_identity
from waifu_bot.services.background import start_all_background_tasks, cancel_all_background_tasks

logger = logging.getLogger(__name__)


class ArmoryCORSMiddleware(BaseHTTPMiddleware):
    """Strict CORS for /api/armory/*; permissive elsewhere."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/armory"):
            origin = request.headers.get("origin")
            allowed = {settings.armory_public_origin.rstrip("/")}
            if origin and origin.rstrip("/") not in allowed:
                if request.method == "OPTIONS":
                    return JSONResponse(status_code=403, content={"detail": "cors forbidden"})
            response = await call_next(request)
            if origin and origin.rstrip("/") in allowed:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
                if request.method == "OPTIONS":
                    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            return response
        return await call_next(request)


async def _run_startup_diagnostics() -> None:
    """Log warnings for common misconfiguration issues at startup."""
    try:
        from sqlalchemy import select, func
        from waifu_bot.db.models import GDDungeonTemplate, GDCycle

        admin_ids = settings.admin_ids
        logger.info(
            "Startup diagnostics: ADMIN_IDS=%s, environment=%s",
            admin_ids or "(empty — GD admin commands available only to GD_V1_MANUAL_TEST_USER_IDS)",
            settings.environment,
        )

        async for session in get_session():
            tpl_count = await session.scalar(
                select(func.count()).select_from(GDDungeonTemplate)
            )
            if not tpl_count:
                logger.warning(
                    "STARTUP CHECK: gd_dungeon_templates table is EMPTY — "
                    "/gd_join will always fail. Run: python scripts/seed_gd_content.py"
                )
            else:
                logger.info("Startup diagnostics: gd_dungeon_templates=%d", tpl_count)

            stuck = (
                await session.execute(
                    select(GDCycle.id, GDCycle.chat_id, GDCycle.status)
                    .where(GDCycle.status == "active")
                )
            ).all()
            if stuck:
                for row in stuck:
                    logger.info(
                        "STARTUP CHECK: active GD cycle id=%s chat_id=%s — group messages "
                        "are buffered for the GD round AND still deal solo damage. "
                        "Use /gd_v1_test_reset or UPDATE gd_cycle SET status='done' to end it.",
                        row[0], row[1],
                    )
            break
    except Exception:
        logger.exception("Startup diagnostics failed (non-fatal)")


def create_app() -> FastAPI:
    setup_logging()

    webapp_dir = Path(__file__).resolve().parent / "webapp"
    static_dir = Path(__file__).resolve().parents[2] / "static"

    app = FastAPI(
        title="Waifu Bot REBORN",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ArmoryCORSMiddleware)

    app.include_router(api_router, prefix="/api")

    if webapp_dir.exists():
        app.mount("/webapp", StaticFiles(directory=str(webapp_dir), html=True), name="webapp")
        _favicon = webapp_dir / "favicon.ico"
        if _favicon.is_file():

            @app.get("/favicon.ico", include_in_schema=False)
            async def _root_favicon() -> FileResponse:
                return FileResponse(_favicon, media_type="image/x-icon")

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir), html=False), name="static")

    armory_dir = static_dir / "armory"
    if armory_dir.is_dir():
        assets_dir = armory_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/armory/assets", StaticFiles(directory=str(assets_dir)), name="armory_assets")

        @app.get("/armory", include_in_schema=False)
        @app.get("/armory/{full_path:path}", include_in_schema=False)
        async def armory_spa(full_path: str = "") -> FileResponse:
            if full_path:
                candidate = (armory_dir / full_path).resolve()
                if str(candidate).startswith(str(armory_dir.resolve())) and candidate.is_file():
                    return FileResponse(candidate)
            index = armory_dir / "index.html"
            if index.is_file():
                return FileResponse(index)
            return FileResponse(armory_dir / "index.html")

    @app.on_event("startup")
    async def _startup() -> None:
        init_engine()

        asyncio.create_task(_run_startup_diagnostics())
        asyncio.create_task(log_bot_identity())

        if settings.environment not in ("dev", "testing"):
            mode = get_update_mode()
            logger.info("Telegram update mode: %s", mode)

            if mode == "polling":
                async def _start_poll() -> None:
                    try:
                        await start_polling()
                    except Exception as e:
                        logger.exception(
                            "Failed to start polling: %s: %s", type(e).__name__, e,
                        )
                asyncio.create_task(_start_poll())
            else:
                async def _run() -> None:
                    try:
                        await setup_webhook()
                    except Exception as e:
                        logger.warning(
                            "Telegram webhook setup failed (бот не получит апдейты до исправления). %s: %s",
                            type(e).__name__,
                            e,
                        )
                asyncio.create_task(_run())

        mode = (settings.background_mode or "inline").lower()
        if mode in ("inline", "dual"):
            start_all_background_tasks()
        else:
            logger.info("BACKGROUND_MODE=%s — inline asyncio loops disabled in API", mode)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await stop_polling()
        await cancel_all_background_tasks()

    @app.get("/health", tags=["infra"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


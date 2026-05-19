from pathlib import Path

import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from waifu_bot.api.routes import router as api_router
from waifu_bot.core.config import settings
from waifu_bot.core.logging import setup_logging
from waifu_bot.db.session import get_session, init_engine
from waifu_bot.services.webhook import setup_webhook, start_polling, stop_polling, get_update_mode, log_bot_identity
from waifu_bot.services.background import start_all_background_tasks, cancel_all_background_tasks

logger = logging.getLogger(__name__)


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
                    logger.warning(
                        "STARTUP CHECK: active GD cycle id=%s chat_id=%s — "
                        "solo damage in this chat is BLOCKED while cycle is active. "
                        "Use /gd_v1_test_reset or UPDATE gd_cycle SET status='done'",
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: tighten in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

        start_all_background_tasks()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await stop_polling()
        await cancel_all_background_tasks()

    @app.get("/health", tags=["infra"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


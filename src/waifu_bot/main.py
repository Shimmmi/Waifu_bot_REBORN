from pathlib import Path

import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from waifu_bot.api.routes import router as api_router
from waifu_bot.core.config import settings
from waifu_bot.core.logging import setup_logging
from waifu_bot.core import redis as redis_core
from waifu_bot.db.session import get_session, init_engine
from waifu_bot.game.constants import GD_SAVE_INTERVAL_SECONDS, GD_REGRESSION_INTERVAL_SECONDS
from waifu_bot.services.webhook import setup_webhook
from waifu_bot.services.combat import CombatService
from waifu_bot.services.group_dungeon import GroupDungeonService

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    setup_logging()

    webapp_dir = Path(__file__).resolve().parent / "webapp"

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

    @app.on_event("startup")
    async def _startup() -> None:
        init_engine()  # ensure DB is ready before first webhook
        if settings.environment != "dev":
            async def _run() -> None:
                try:
                    await setup_webhook()
                except Exception:
                    logger.exception("Failed to setup Telegram webhook on startup")

            asyncio.create_task(_run())

        # GD background: save every 30s, regression every 90s
        async def _gd_background_loop() -> None:
            init_engine()
            redis_client = redis_core.get_redis()
            combat_service = CombatService(redis_client=redis_client)
            gd_service = GroupDungeonService(redis_client=redis_client, combat_service=combat_service)
            tick_count = 0
            while True:
                await asyncio.sleep(GD_SAVE_INTERVAL_SECONDS)
                tick_count += 1
                run_regression = (tick_count * GD_SAVE_INTERVAL_SECONDS % GD_REGRESSION_INTERVAL_SECONDS) < GD_SAVE_INTERVAL_SECONDS
                try:
                    async for session in get_session():
                        await gd_service.run_background_tick(session, run_regression=run_regression)
                        break
                except Exception:
                    logger.exception("GD background tick failed")

        asyncio.create_task(_gd_background_loop())

    @app.get("/health", tags=["infra"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


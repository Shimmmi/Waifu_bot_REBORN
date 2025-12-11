from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from waifu_bot.api.routes import router as api_router
from waifu_bot.core.config import settings
from waifu_bot.core.logging import setup_logging


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

    @app.get("/health", tags=["infra"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


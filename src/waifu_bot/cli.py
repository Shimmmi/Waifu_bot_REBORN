"""CLI utilities for Waifu Bot."""
import os
import asyncio
import typer

from waifu_bot.services.webhook import setup_webhook
from waifu_bot.db.session import init_engine
from alembic.config import Config
from alembic import command

app = typer.Typer(help="Waifu Bot CLI")


def _set_env(env: str) -> None:
    """Set APP_ENV before loading config (for run --env)."""
    os.environ["APP_ENV"] = env


@app.command()
def webhook():
    """Set Telegram webhook."""
    asyncio.run(setup_webhook())


@app.command()
def migrate(revision: str = "head"):
    """Run Alembic migrations."""
    init_engine()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, revision)


@app.command()
def run(
    env: str = typer.Option("dev", "--env", "-e", help="APP_ENV: production, testing, dev, stage"),
):
    """Run the application (FastAPI). Sets APP_ENV before loading config."""
    _set_env(env)
    import uvicorn
    from waifu_bot.core.config import settings
    uvicorn.run(
        "waifu_bot.main:app",
        host=settings.host,
        port=settings.port,
        reload=(settings.environment == "dev"),
    )


if __name__ == "__main__":
    app()


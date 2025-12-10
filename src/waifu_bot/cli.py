"""CLI utilities for Waifu Bot."""
import asyncio
import typer

from waifu_bot.services.webhook import setup_webhook
from waifu_bot.db.session import init_engine
from alembic.config import Config
from alembic import command

app = typer.Typer(help="Waifu Bot CLI")


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


if __name__ == "__main__":
    app()


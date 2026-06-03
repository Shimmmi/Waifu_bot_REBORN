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
def migrate(revision: str = "heads"):
    """Run Alembic migrations."""
    init_engine()
    cfg = Config("alembic.ini")
    command.upgrade(cfg, revision)


@app.command("backfill-group-chats")
def backfill_group_chats():
    """Populate bot_group_chats from historical chat_id sources + Telegram API."""
    init_engine()

    async def _run() -> None:
        from waifu_bot.db.session import get_session
        from waifu_bot.services.bot_group_chats import backfill_bot_group_chats
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        async for session in get_session():
            result = await backfill_bot_group_chats(session, bot)
            typer.echo(result)
            break

    asyncio.run(_run())


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


@app.command()
def scheduler(
    env: str = typer.Option("production", "--env", "-e", help="APP_ENV"),
):
    """Run Dramatiq tick scheduler (BACKGROUND_MODE=worker|dual)."""
    _set_env(env)
    from waifu_bot.worker.scheduler import run_scheduler

    asyncio.run(run_scheduler())


@app.command()
def worker(
    queue: str = typer.Option("default", "--queue", "-Q", help="Dramatiq queue: default|llm"),
    processes: int = typer.Option(1, "--processes", "-p"),
    threads: int = typer.Option(4, "--threads", "-t"),
    env: str = typer.Option("production", "--env", "-e"),
):
    """Run Dramatiq worker process."""
    import os
    import subprocess
    import sys

    _set_env(env)
    os.environ.setdefault("PYTHONPATH", os.path.join(os.getcwd(), "src"))
    if queue == "llm":
        os.environ["WORKER_ROLE"] = "llm"
    else:
        os.environ["WORKER_ROLE"] = "gameplay"
    cmd = [
        sys.executable,
        "-m",
        "dramatiq",
        "waifu_bot.worker.actors",
        "--processes",
        str(processes),
        "--threads",
        str(threads),
        "-Q",
        queue,
    ]
    typer.echo(" ".join(cmd))
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    app()

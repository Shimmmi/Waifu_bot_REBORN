"""Enqueue Dramatiq tick actors on interval (BACKGROUND_MODE=worker|dual)."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def _poll_spec(name: str, interval_sec: float, skip_in_dev: bool) -> None:
    from waifu_bot.core.config import settings
    from waifu_bot.worker.actors.gameplay import TICK_ACTORS

    actor = TICK_ACTORS.get(name)
    if actor is None:
        logger.warning("scheduler: no actor for tick %s", name)
        return
    while True:
        await asyncio.sleep(interval_sec)
        if skip_in_dev and settings.environment in ("dev", "testing"):
            continue
        try:
            actor.send()
        except Exception:
            logger.exception("scheduler enqueue failed tick=%s", name)


async def run_scheduler() -> None:
    from waifu_bot.core.config import settings
    from waifu_bot.services.background_ticks import get_background_tick_registry

    # Ensure actors are registered
    import waifu_bot.worker.actors  # noqa: F401

    mode = (settings.background_mode or "inline").lower()
    if mode not in ("worker", "dual"):
        logger.error("scheduler requires BACKGROUND_MODE=worker or dual, got %s", mode)
        return

    registry = get_background_tick_registry()
    logger.info("Starting background scheduler (%d ticks, mode=%s)", len(registry), mode)
    await asyncio.gather(
        *[
            _poll_spec(spec.name, spec.interval_sec, spec.skip_in_dev)
            for spec in registry
        ]
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()

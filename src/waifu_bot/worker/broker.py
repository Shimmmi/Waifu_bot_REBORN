"""Dramatiq Redis broker with result backend for LLM offload."""
from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend


def configure_broker() -> RedisBroker:
    from waifu_bot.core.config import settings

    result_backend = RedisBackend(url=settings.redis_url)
    broker = RedisBroker(url=settings.redis_url)
    broker.add_middleware(Results(backend=result_backend))
    dramatiq.set_broker(broker)
    return broker


# Configure on import so actors register against this broker.
redis_broker = configure_broker()

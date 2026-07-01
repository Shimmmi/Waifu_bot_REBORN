"""Run async tick/LLM coroutines from sync Dramatiq actors."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)

"""LLM queue actors (OpenRouter via existing client, no offload recursion)."""
from __future__ import annotations

import logging
from typing import Any

import dramatiq
import httpx

from waifu_bot.worker.asyncio_bridge import run_async

logger = logging.getLogger(__name__)


@dramatiq.actor(
    queue_name="llm",
    actor_name="llm_post_chat_completions",
    max_retries=0,
    time_limit=180_000,
)
def llm_post_chat_completions_task(
    payload: dict[str, Any],
    caller: str,
    use_image_model: bool = False,
) -> dict[str, Any]:
    """Execute LLM HTTP call in llm worker process."""

    async def _run_full() -> dict[str, Any]:
        from waifu_bot.services.llm_client import (
            FALLBACK_HTTP_STATUSES,
            llm_provider_chain,
            _post_chat_completions_locked,
        )

        chain = llm_provider_chain()
        if not chain:
            raise RuntimeError("no LLM provider configured")
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await _post_chat_completions_locked(
                client,
                payload,
                caller=caller,
                use_image_model=use_image_model,
                fallback_set=set(FALLBACK_HTTP_STATUSES),
                chain=chain,
            )
        return {
            "status_code": r.status_code,
            "content": r.content,
            "headers": dict(r.headers),
        }

    return run_async(_run_full())

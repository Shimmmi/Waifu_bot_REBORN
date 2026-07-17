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
    store_results=True,
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
            provider_chain_for_request,
            _post_chat_completions_locked,
        )

        chain = provider_chain_for_request(use_image_model=use_image_model)
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


@dramatiq.actor(
    queue_name="llm",
    actor_name="llm_fusion_generate",
    max_retries=0,
    time_limit=300_000,
    store_results=True,
)
def llm_fusion_generate_task(
    preset: str,
    messages: list[dict[str, Any]],
    caller: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout_sec: float | None = None,
    post_process_rhythm: bool | None = None,
    rhythm_length_hint: str = "2–4 предложения",
    rhythm_preserve_html: bool = False,
) -> dict[str, Any]:
    """Execute full preset generation (including fusion) in llm worker process."""

    async def _run_full() -> dict[str, Any]:
        from waifu_bot.services.ai_service import generate_core

        text = await generate_core(
            preset=preset,
            messages=messages,
            caller=caller,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=timeout_sec,
            post_process_rhythm=post_process_rhythm,
            rhythm_length_hint=rhythm_length_hint,
            rhythm_preserve_html=rhythm_preserve_html,
        )
        return {"ok": text is not None, "text": text}

    try:
        return run_async(_run_full())
    except Exception as exc:
        logger.exception("llm_fusion_generate_task failed caller=%s", caller)
        return {"ok": False, "error": str(exc), "text": None}

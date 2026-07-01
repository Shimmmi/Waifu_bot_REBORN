"""Unified AI generation API with RouterAI preset routing."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from waifu_bot.core.config import settings
from waifu_bot.services.ai_fusion import run_fusion, run_fusion_roles
from waifu_bot.services.ai_narrative_rewrite import (
    _extract_openrouter_assistant_text,
    _openrouter_text_extra,
    rhythm_rewrite_narrative,
    strip_code_fence,
    strip_markdown_prose,
)
from waifu_bot.services.ai_presets import (
    FusionPreset,
    FusionRolesPreset,
    PresetDefaults,
    SinglePreset,
    resolve_preset,
)
from waifu_bot.services.llm_client import (
    _get_fusion_semaphore,
    has_text_llm_configured,
    post_chat_completions_routerai,
    should_offload_llm,
)

logger = logging.getLogger(__name__)

def _build_messages(
    prompt: str | list[dict[str, Any]],
    *,
    system: str | None,
) -> list[dict[str, Any]]:
    if isinstance(prompt, list):
        return list(prompt)
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _extract_user_prompt(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
    return ""


def _sanitize_single_output(raw: str) -> str | None:
    text = strip_code_fence(raw)
    if not text:
        return None
    return strip_markdown_prose(text) or text.strip()


async def _generate_via_worker(
    *,
    preset: str,
    messages: list[dict[str, Any]],
    caller: str,
    max_tokens: int | None,
    temperature: float | None,
    timeout_sec: float | None,
    post_process_rhythm: bool | None,
    rhythm_length_hint: str,
    rhythm_preserve_html: bool,
) -> str | None:
    import asyncio

    import waifu_bot.worker.actors  # noqa: F401
    from waifu_bot.worker.actors.llm import llm_fusion_generate_task

    message = llm_fusion_generate_task.send(
        preset,
        messages,
        caller,
        max_tokens,
        temperature,
        timeout_sec,
        post_process_rhythm,
        rhythm_length_hint,
        rhythm_preserve_html,
    )
    result = await asyncio.to_thread(message.get_result, block=True, timeout=300_000)
    if not result.get("ok"):
        logger.warning("LLM fusion worker (%s): %s", caller, result.get("error"))
        return None
    text = result.get("text")
    return text if isinstance(text, str) and text.strip() else None


async def _generate_single(
    preset_cfg: SinglePreset,
    messages: list[dict[str, Any]],
    *,
    defaults: PresetDefaults,
    caller: str,
    client: httpx.AsyncClient,
    max_tokens: int | None,
    temperature: float | None,
) -> str | None:
    payload = {
        "messages": messages,
        "max_tokens": max_tokens or defaults.max_tokens,
        "temperature": temperature if temperature is not None else defaults.temperature,
        **_openrouter_text_extra(),
    }
    model = preset_cfg.model
    response = await post_chat_completions_routerai(
        client, payload, model=model, caller=caller, use_fusion_semaphore=False,
    )
    if not response.is_success and preset_cfg.fallback_model:
        response = await post_chat_completions_routerai(
            client,
            payload,
            model=preset_cfg.fallback_model,
            caller=f"{caller}-fallback",
            use_fusion_semaphore=False,
        )
    if not response.is_success:
        return None
    try:
        data = response.json()
    except Exception:
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    raw = _extract_openrouter_assistant_text(choices[0])
    return _sanitize_single_output(raw) if raw else None


async def generate(
    prompt: str | list[dict[str, Any]],
    *,
    preset: str | None = None,
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    caller: str = "ai-generate",
    timeout_sec: float | None = None,
    post_process_rhythm: bool | None = None,
    rhythm_length_hint: str = "2–4 предложения",
    rhythm_preserve_html: bool = False,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """
    Generate text via RouterAI preset (single / fusion / fusion_roles).
    Returns None when LLM is not configured or generation fails.
    """
    if not has_text_llm_configured():
        return None

    preset_name = preset or settings.ai_default_preset
    preset_cfg, defaults = resolve_preset(preset_name)
    effective_timeout = timeout_sec if timeout_sec is not None else defaults.timeout_sec
    messages = _build_messages(prompt, system=system)

    mode = getattr(preset_cfg, "mode", "single")
    if should_offload_llm(caller):
        return await _generate_via_worker(
            preset=preset_name,
            messages=messages,
            caller=caller,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_sec=effective_timeout,
            post_process_rhythm=post_process_rhythm,
            rhythm_length_hint=rhythm_length_hint,
            rhythm_preserve_html=rhythm_preserve_html,
        )

    async def _run(c: httpx.AsyncClient) -> str | None:
        if isinstance(preset_cfg, SinglePreset):
            text = await _generate_single(
                preset_cfg,
                messages,
                defaults=defaults,
                caller=caller,
                client=c,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif isinstance(preset_cfg, FusionPreset):
            async with _get_fusion_semaphore():
                text = await run_fusion(
                    preset_cfg,
                    messages,
                    defaults=defaults,
                    caller=caller,
                    client=c,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        elif isinstance(preset_cfg, FusionRolesPreset):
            async with _get_fusion_semaphore():
                text = await run_fusion_roles(
                    preset_cfg,
                    _extract_user_prompt(messages),
                    defaults=defaults,
                    caller=caller,
                    client=c,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        else:
            return None

        if not text:
            return None

        do_rhythm = post_process_rhythm
        if do_rhythm is None and isinstance(preset_cfg, SinglePreset):
            do_rhythm = preset_cfg.post_process == "rhythm_rewrite"

        if do_rhythm:
            return await rhythm_rewrite_narrative(
                text,
                caller=caller,
                length_hint=rhythm_length_hint,
                preserve_html=rhythm_preserve_html,
            )
        return text

    if client is not None:
        return await _run(client)

    async with httpx.AsyncClient(timeout=effective_timeout) as c:
        return await _run(c)


async def generate_core(
    *,
    preset: str,
    messages: list[dict[str, Any]],
    caller: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout_sec: float | None = None,
    post_process_rhythm: bool | None = None,
    rhythm_length_hint: str = "2–4 предложения",
    rhythm_preserve_html: bool = False,
) -> str | None:
    """Worker-safe entry: preset + messages without offload recursion."""
    if not has_text_llm_configured():
        return None

    preset_cfg, defaults = resolve_preset(preset)
    effective_timeout = timeout_sec if timeout_sec is not None else defaults.timeout_sec

    async with httpx.AsyncClient(timeout=effective_timeout) as client:
        if isinstance(preset_cfg, SinglePreset):
            text = await _generate_single(
                preset_cfg,
                messages,
                defaults=defaults,
                caller=caller,
                client=client,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        elif isinstance(preset_cfg, FusionPreset):
            async with _get_fusion_semaphore():
                text = await run_fusion(
                    preset_cfg,
                    messages,
                    defaults=defaults,
                    caller=caller,
                    client=client,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        elif isinstance(preset_cfg, FusionRolesPreset):
            async with _get_fusion_semaphore():
                text = await run_fusion_roles(
                    preset_cfg,
                    _extract_user_prompt(messages),
                    defaults=defaults,
                    caller=caller,
                    client=client,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
        else:
            return None

        if not text:
            return None

        do_rhythm = post_process_rhythm
        if do_rhythm is None and isinstance(preset_cfg, SinglePreset):
            do_rhythm = preset_cfg.post_process == "rhythm_rewrite"

        if do_rhythm:
            return await rhythm_rewrite_narrative(
                text,
                caller=caller,
                length_hint=rhythm_length_hint,
                preserve_html=rhythm_preserve_html,
            )
        return text

"""RouterAI fusion orchestration: parallel experts + judge synthesis."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from waifu_bot.services.ai_narrative_rewrite import (
    _extract_openrouter_assistant_text,
    _openrouter_text_extra,
    looks_like_meta_analysis,
    strip_code_fence,
    strip_markdown_prose,
)
from waifu_bot.services.ai_presets import (
    FusionPreset,
    FusionRolesPreset,
    PresetDefaults,
)
from waifu_bot.services.llm_client import post_chat_completions_routerai

logger = logging.getLogger(__name__)


@dataclass
class ExpertResult:
    label: str
    model: str
    text: str | None
    error: str | None = None


def _sanitize_output(raw: str) -> str | None:
    text = strip_code_fence(raw)
    if not text:
        return None
    text = strip_markdown_prose(text)
    if not text or looks_like_meta_analysis(text):
        return None
    return text


def _response_text(response: httpx.Response) -> str | None:
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
    return _sanitize_output(raw) if raw else None


def _best_expert_fallback(results: list[ExpertResult]) -> str | None:
    candidates = [r.text for r in results if r.text]
    if not candidates:
        return None
    return max(candidates, key=len)


async def _call_model(
    client: httpx.AsyncClient,
    *,
    model: str,
    messages: list[dict],
    defaults: PresetDefaults,
    caller: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str | None:
    payload = {
        "messages": messages,
        "max_tokens": max_tokens or defaults.max_tokens,
        "temperature": temperature if temperature is not None else defaults.temperature,
        **_openrouter_text_extra(),
    }
    response = await post_chat_completions_routerai(
        client,
        payload,
        model=model,
        caller=caller,
        use_fusion_semaphore=False,
    )
    return _response_text(response)


async def _run_expert(
    client: httpx.AsyncClient,
    *,
    label: str,
    model: str,
    messages: list[dict],
    defaults: PresetDefaults,
    caller: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> ExpertResult:
    try:
        text = await _call_model(
            client,
            model=model,
            messages=messages,
            defaults=defaults,
            caller=f"{caller}-{label}",
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if text:
            return ExpertResult(label=label, model=model, text=text)
        return ExpertResult(label=label, model=model, text=None, error="empty response")
    except Exception as exc:
        logger.warning("Fusion expert %s (%s) failed: %s", label, model, exc)
        return ExpertResult(label=label, model=model, text=None, error=str(exc))


def _build_judge_user_prompt(results: list[ExpertResult], judge_prompt: str) -> str:
    parts = [judge_prompt.strip(), "", "Ответы экспертов:"]
    for idx, result in enumerate(results, start=1):
        parts.append(f"\n--- Эксперт {idx} ({result.label}, {result.model}) ---")
        if result.text:
            parts.append(result.text)
        elif result.error:
            parts.append(f"[ошибка: {result.error}]")
        else:
            parts.append("[пустой ответ]")
    parts.append("\nВерни только финальный ответ без meta-анализа.")
    return "\n".join(parts)


async def run_fusion(
    preset: FusionPreset,
    messages: list[dict],
    *,
    defaults: PresetDefaults,
    caller: str,
    client: httpx.AsyncClient,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str | None:
    """Parallel experts with identical messages, then judge synthesis."""
    user_content = ""
    system_content = ""
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "user" and isinstance(content, str):
            user_content = content
        elif role == "system" and isinstance(content, str):
            system_content = content

    expert_messages: list[dict] = []
    if system_content:
        expert_messages.append({"role": "system", "content": system_content})
    expert_messages.append({"role": "user", "content": user_content})

    if preset.parallel_experts:
        tasks = [
            _run_expert(
                client,
                label=f"expert-{idx}",
                model=model,
                messages=expert_messages,
                defaults=defaults,
                caller=caller,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            for idx, model in enumerate(preset.experts, start=1)
        ]
        results = list(await asyncio.gather(*tasks))
    else:
        results = []
        for idx, model in enumerate(preset.experts, start=1):
            results.append(
                await _run_expert(
                    client,
                    label=f"expert-{idx}",
                    model=model,
                    messages=expert_messages,
                    defaults=defaults,
                    caller=caller,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            )

    if not any(r.text for r in results):
        logger.warning("Fusion %s: all experts failed", caller)
        return None

    judge_user = _build_judge_user_prompt(results, preset.judge_prompt)
    judge_messages = [{"role": "user", "content": judge_user}]
    judge_text = await _call_model(
        client,
        model=preset.judge,
        messages=judge_messages,
        defaults=defaults,
        caller=f"{caller}-judge",
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if judge_text:
        return judge_text
    logger.warning("Fusion %s: judge failed, using best expert fallback", caller)
    return _best_expert_fallback(results)


async def run_fusion_roles(
    preset: FusionRolesPreset,
    user_prompt: str,
    *,
    defaults: PresetDefaults,
    caller: str,
    client: httpx.AsyncClient,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str | None:
    """Role-specific experts, then judge synthesis (architect preset)."""
    tasks = [
        _run_expert(
            client,
            label=role_name,
            model=role.model,
            messages=[
                {"role": "system", "content": role.system},
                {"role": "user", "content": user_prompt},
            ],
            defaults=defaults,
            caller=caller,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        for role_name, role in preset.roles.items()
    ]
    results = list(await asyncio.gather(*tasks))

    if not any(r.text for r in results):
        logger.warning("Fusion roles %s: all experts failed", caller)
        return None

    judge_user = _build_judge_user_prompt(
        results,
        preset.judge.system,
    )
    judge_messages = [
        {"role": "system", "content": preset.judge.system},
        {"role": "user", "content": judge_user},
    ]
    judge_text = await _call_model(
        client,
        model=preset.judge.model,
        messages=judge_messages,
        defaults=defaults,
        caller=f"{caller}-judge",
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if judge_text:
        return judge_text
    logger.warning("Fusion roles %s: judge failed, using best expert fallback", caller)
    return _best_expert_fallback(results)

"""OpenRouter + RouterAI chat completions with 402 fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import httpx

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_HTTP_STATUSES: tuple[int, ...] = (402,)


@dataclass(frozen=True)
class LlmProvider:
    name: str
    base_url: str
    api_key: str
    text_model: str
    image_model: str


def chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def llm_request_headers(api_key: str) -> dict[str, str]:
    referer = str(getattr(settings, "public_base_url", "https://waifu-bot.reborn")).rstrip("/")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Referer": referer,
        "HTTP-Referer": referer,
        "X-Title": "Waifu Bot",
    }


def _openrouter_provider() -> LlmProvider | None:
    key = (getattr(settings, "openrouter_api_key", None) or "").strip()
    if not key:
        return None
    return LlmProvider(
        name="openrouter",
        base_url=settings.openrouter_base_url,
        api_key=key,
        text_model=settings.openrouter_model,
        image_model=settings.openrouter_model_image,
    )


def _routerai_provider() -> LlmProvider | None:
    key = (getattr(settings, "routerai_api_key", None) or "").strip()
    if not key:
        return None
    text = getattr(settings, "routerai_model", None) or settings.openrouter_model
    image = getattr(settings, "routerai_model_image", None) or settings.openrouter_model_image
    return LlmProvider(
        name="routerai",
        base_url=settings.routerai_base_url,
        api_key=key,
        text_model=text,
        image_model=image,
    )


def llm_provider_chain() -> list[LlmProvider]:
    chain: list[LlmProvider] = []
    or_prov = _openrouter_provider()
    if or_prov:
        chain.append(or_prov)
    ra_prov = _routerai_provider()
    if ra_prov and (not or_prov or ra_prov.api_key != or_prov.api_key):
        chain.append(ra_prov)
    elif ra_prov and not or_prov:
        chain.append(ra_prov)
    return chain


def has_llm_configured() -> bool:
    return bool(llm_provider_chain())


def primary_provider() -> LlmProvider | None:
    chain = llm_provider_chain()
    return chain[0] if chain else None


def _payload_with_model(payload: dict, provider: LlmProvider, *, use_image_model: bool) -> dict:
    """OpenRouter: model из payload. RouterAI: подставить ROUTERAI_MODEL* если заданы."""
    out = dict(payload)
    if provider.name != "routerai":
        if use_image_model and not out.get("model"):
            out["model"] = provider.image_model
        return out
    if use_image_model and getattr(settings, "routerai_model_image", None):
        out["model"] = settings.routerai_model_image
    elif not use_image_model and getattr(settings, "routerai_model", None):
        out["model"] = settings.routerai_model
    elif use_image_model and not out.get("model"):
        out["model"] = provider.image_model
    return out


async def post_chat_completions(
    client: httpx.AsyncClient,
    payload: dict,
    *,
    caller: str,
    use_image_model: bool = False,
    fallback_on: Sequence[int] = FALLBACK_HTTP_STATUSES,
) -> httpx.Response:
    """
    POST /chat/completions через цепочку провайдеров.
    При статусе из fallback_on и наличии следующего провайдера — retry.
    """
    chain = llm_provider_chain()
    if not chain:
        raise RuntimeError("post_chat_completions called without any LLM provider configured")

    fallback_set = set(fallback_on)
    last: httpx.Response | None = None

    for idx, provider in enumerate(chain):
        body = _payload_with_model(payload, provider, use_image_model=use_image_model)
        url = chat_completions_url(provider.base_url)
        last = await client.post(url, headers=llm_request_headers(provider.api_key), json=body)
        has_next = idx < len(chain) - 1
        if last.status_code in fallback_set and has_next:
            logger.warning(
                "LLM %s: provider=%s HTTP %s, trying fallback %s",
                caller,
                provider.name,
                last.status_code,
                chain[idx + 1].name,
            )
            continue
        if not last.is_success and last.status_code not in fallback_set:
            logger.warning(
                "LLM %s: provider=%s HTTP %s body=%s",
                caller,
                provider.name,
                last.status_code,
                (last.text or "")[:400],
            )
        return last

    assert last is not None
    return last


def openrouter_url_for_compat() -> str:
    """URL первого провайдера в цепочке (для обратной совместимости импортов)."""
    prov = primary_provider()
    if prov:
        return chat_completions_url(prov.base_url)
    return chat_completions_url("https://openrouter.ai/api/v1")


def openrouter_headers_for_compat() -> dict[str, str]:
    """Заголовки первого провайдера (для обратной совместимости)."""
    prov = primary_provider()
    if prov:
        return llm_request_headers(prov.api_key)
    return llm_request_headers("")

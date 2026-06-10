#!/usr/bin/env python3
"""Generate legendary item display names via OpenRouter / RouterAI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import httpx

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.legendary_name_llm import (  # noqa: E402
    CURATED_SKIP,
    build_system_prompt,
    build_user_prompt,
    collect_used_names,
    load_names_out,
    parse_names_response,
    save_names_out,
)
from lib.legendary_static_affix_llm import load_legendary_templates  # noqa: E402
from waifu_bot.core.config import settings  # noqa: E402
from waifu_bot.services.ai_narrative_rewrite import _extract_openrouter_assistant_text, _openrouter_text_extra  # noqa: E402
from waifu_bot.services.llm_client import (  # noqa: E402
    LlmProvider,
    _openrouter_provider,
    _routerai_provider,
    chat_completions_url,
    has_llm_configured,
    llm_provider_chain,
    llm_request_headers,
    post_chat_completions,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUT = ROOT / "scripts/data/legendary_item_names_ru.json"


def _resolve_provider(name: str) -> list[LlmProvider]:
    if name == "openrouter":
        p = _openrouter_provider()
        return [p] if p else []
    if name == "routerai":
        p = _routerai_provider()
        return [p] if p else []
    return llm_provider_chain()


def _resolve_model(cli_model: str | None, provider: LlmProvider) -> str:
    if cli_model:
        return cli_model.strip()
    if provider.name == "routerai" and getattr(settings, "routerai_model", None):
        return str(settings.routerai_model)
    return settings.openrouter_model


def _response_text(r: httpx.Response) -> str:
    if not r.is_success:
        raise RuntimeError(f"LLM HTTP {r.status_code}: {(r.text or '')[:400]}")
    data = r.json()
    choices = data.get("choices") or []
    text = _extract_openrouter_assistant_text(choices[0]) if choices else ""
    if not text:
        raise RuntimeError("empty LLM response")
    return text


async def _request_batch(
    client: httpx.AsyncClient,
    *,
    model: str,
    system: str,
    user: str,
    providers: list[LlmProvider] | None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 4000,
        "temperature": 0.85,
        **_openrouter_text_extra(),
    }
    if providers is None:
        return _response_text(await post_chat_completions(client, payload, caller="legendary names"))
    last_err = "LLM failed"
    for prov in providers:
        url = chat_completions_url(prov.base_url)
        r = await client.post(url, headers=llm_request_headers(prov.api_key), json=payload)
        if r.is_success:
            return _response_text(r)
        last_err = f"{prov.name} HTTP {r.status_code}"
    raise RuntimeError(last_err)


async def run(args: argparse.Namespace) -> int:
    templates = load_legendary_templates()
    if args.skip_curated:
        templates = [
            t
            for t in templates
            if (str(t["name"]), int(t["tier"])) not in CURATED_SKIP
        ]
    names = load_names_out(args.out) if args.resume else {}
    used = collect_used_names(names)
    pending = [t for t in templates if str(t["template_id"]) not in names]

    if args.dry_run:
        print(build_system_prompt(list(used)[:20]))
        print(build_user_prompt(pending[:3])[:1500])
        print(f"pending={len(pending)}")
        return 0

    if not pending:
        logger.info("All names present in %s", args.out)
        return 0
    if not has_llm_configured():
        logger.error("LLM API keys not configured")
        return 1

    chain = _resolve_provider(args.provider)
    model = _resolve_model(args.model, chain[0])
    api_providers = None if args.provider == "auto" else chain
    initial_count = len(names)
    pending_count = len(pending)

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i in range(0, len(pending), args.batch_size):
            batch = pending[i : i + args.batch_size]
            ids = [int(t["template_id"]) for t in batch]
            system = build_system_prompt(list(used))
            user = build_user_prompt(batch)
            try:
                raw = await _request_batch(
                    client, model=model, system=system, user=user, providers=api_providers
                )
                parsed = parse_names_response(raw, ids, used)
            except Exception as e:
                logger.warning("batch failed: %s", e)
                continue
            for tid, nm in parsed.items():
                names[str(tid)] = nm
            save_names_out(args.out, names, {"model": model, "source": "llm"})
            if args.delay > 0:
                await asyncio.sleep(args.delay)

    logger.info("Done: %s names -> %s", len(names), args.out)
    if len(names) == initial_count and pending_count > 0:
        logger.error(
            "LLM generated no new names (%s pending); check API keys and billing",
            pending_count,
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--provider", default="auto", choices=("auto", "openrouter", "routerai"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-curated", action="store_true", default=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

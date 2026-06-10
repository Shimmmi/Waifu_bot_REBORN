#!/usr/bin/env python3
"""Generate legendary static affix profiles via OpenRouter / RouterAI."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import httpx

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.legendary_static_affix_llm import (  # noqa: E402
    build_system_prompt,
    build_user_prompt,
    load_affix_catalog_for_tier,
    load_legendary_templates,
    load_profiles_json,
    parse_profiles_response,
    rule_based_profile,
    save_profiles_json,
    validate_profile,
)
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

DEFAULT_OUT = ROOT / "scripts/data/legendary_static_affixes.json"


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
    if not choices:
        raise RuntimeError("LLM returned empty choices")
    text = _extract_openrouter_assistant_text(choices[0])
    if not text:
        raise RuntimeError("LLM returned empty assistant text")
    return text


async def _request_batch(
    client: httpx.AsyncClient,
    *,
    model: str,
    system: str,
    user: str,
    caller: str,
    providers: list[LlmProvider] | None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": min(8000, max(2000, len(user) // 2)),
        "temperature": 0.7,
        **_openrouter_text_extra(),
    }
    if providers is None:
        r = await post_chat_completions(client, payload, caller=caller)
        return _response_text(r)
    last_err = "LLM request failed"
    for prov in providers:
        url = chat_completions_url(prov.base_url)
        r = await client.post(url, headers=llm_request_headers(prov.api_key), json=payload)
        if r.is_success:
            return _response_text(r)
        last_err = f"{prov.name} HTTP {r.status_code}: {(r.text or '')[:400]}"
        logger.warning("%s", last_err)
    raise RuntimeError(last_err)


async def run(args: argparse.Namespace) -> int:
    templates = load_legendary_templates()
    existing = load_profiles_json(args.out) if args.resume else {}
    pending = [t for t in templates if str(t["template_id"]) not in existing]

    if args.dry_run:
        tier = int(pending[0]["tier"]) if pending else 1
        cat = load_affix_catalog_for_tier(tier)
        print(build_system_prompt())
        print(build_user_prompt(pending[: min(3, len(pending))], cat, tier)[:2000])
        print(f"pending={len(pending)}")
        return 0

    if not pending:
        logger.info("All profiles present in %s", args.out)
        return 0

    if not has_llm_configured():
        logger.error("Set OPENROUTER_API_KEY or ROUTERAI_API_KEY in .env")
        return 1

    chain = _resolve_provider(args.provider)
    model = _resolve_model(args.model, chain[0])
    api_providers = None if args.provider == "auto" else chain
    system = build_system_prompt()
    profiles = dict(existing)

    by_tier: dict[int, list[dict]] = defaultdict(list)
    for t in pending:
        by_tier[int(t["tier"])].append(t)

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for tier, tier_items in sorted(by_tier.items()):
            catalog = load_affix_catalog_for_tier(tier)
            cat_ids = {str(c["family_id"]) for c in catalog}
            for i in range(0, len(tier_items), args.batch_size):
                batch = tier_items[i : i + args.batch_size]
                ids = [int(t["template_id"]) for t in batch]
                user = build_user_prompt(batch, catalog, tier)
                raw = await _request_batch(
                    client,
                    model=model,
                    system=system,
                    user=user,
                    caller=f"legendary static affixes T{tier}",
                    providers=api_providers,
                )
                try:
                    parsed = parse_profiles_response(raw, ids)
                except (ValueError, json.JSONDecodeError) as e:
                    logger.warning("LLM parse failed, rule-based fallback: %s", e)
                    parsed = {int(t["template_id"]): rule_based_profile(t) for t in batch}
                for tid, affixes in parsed.items():
                    tpl = next(t for t in batch if int(t["template_id"]) == tid)
                    tpl["_catalog"] = catalog
                    errs = validate_profile(affixes, tpl, cat_ids)
                    if errs:
                        logger.warning("tid %s validation: %s — rule-based", tid, errs)
                        affixes = rule_based_profile(tpl)
                    profiles[str(tid)] = affixes
                save_profiles_json(args.out, profiles, {"model": model, "source": "llm"})
                if args.delay > 0:
                    await asyncio.sleep(args.delay)

    logger.info("Done: %s profiles -> %s", len(profiles), args.out)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--provider", default="auto", choices=("auto", "openrouter", "routerai"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

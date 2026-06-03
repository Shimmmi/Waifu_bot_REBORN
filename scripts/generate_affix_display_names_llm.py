#!/usr/bin/env python3
"""Generate unique RU affix display names via OpenRouter / RouterAI.

    python3 scripts/generate_affix_display_names_llm.py --copy-legacy
    python3 scripts/generate_affix_display_names_llm.py --synthesize-passive
    python3 scripts/generate_affix_display_names_llm.py --only-passive --resume
    python3 scripts/generate_affix_display_names_llm.py --dry-run --batch-families 8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import httpx

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))
sys.path.insert(0, str(SCRIPTS_DIR))

from affix_name_llm import (  # noqa: E402
    build_system_prompt,
    build_user_prompt,
    collect_used_names,
    copy_legacy_names,
    families_for_llm,
    load_affix_catalog,
    load_names_out,
    merge_name_maps,
    parse_names_response,
    save_names_out,
    synthesize_passive_unique_names,
)

from waifu_bot.core.config import settings  # noqa: E402
from waifu_bot.services.ai_narrative_rewrite import (  # noqa: E402
    _extract_openrouter_assistant_text,
    _openrouter_text_extra,
)
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

DEFAULT_OUT = ROOT / "scripts" / "data" / "affix_display_names_ru.json"
DATA_DIR = ROOT / "scripts" / "data"


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
    max_tokens: int,
    caller: str,
    providers: list[LlmProvider] | None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.85,
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
            try:
                return _response_text(r)
            except RuntimeError as e:
                last_err = str(e)
                continue
        last_err = f"{prov.name} HTTP {r.status_code}: {(r.text or '')[:400]}"
        logger.warning("%s", last_err)
    raise RuntimeError(last_err)


async def _generate_batch_with_retry(
    client: httpx.AsyncClient,
    *,
    model: str,
    system: str,
    batch: list[dict],
    caller: str,
    providers: list[LlmProvider] | None,
    used_names: set[str],
) -> dict[str, dict[str, str]]:
    expected = [it["family_id"] for it in batch]
    user = build_user_prompt(batch)
    max_tokens = min(12000, max(1500, 120 * len(batch) * 10))

    for attempt in range(2):
        user_msg = user
        if attempt > 0:
            user_msg = user + "\n\nВерни ТОЛЬКО валидный JSON без markdown."
        raw = await _request_batch(
            client,
            model=model,
            system=system,
            user=user_msg,
            max_tokens=max_tokens,
            caller=caller,
            providers=providers,
        )
        try:
            return parse_names_response(raw, expected, used_names=used_names)
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("batch parse failed (attempt %s): %s", attempt + 1, e)
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


async def run(args: argparse.Namespace) -> int:
    fams, tiers_by_family = load_affix_catalog(DATA_DIR)
    out_path: Path = args.out
    names = load_names_out(out_path) if args.resume else {}

    if args.copy_legacy:
        legacy = copy_legacy_names(fams, tiers_by_family)
        names = merge_name_maps(names, legacy)
        save_names_out(out_path, names, model="legacy", provider="copy-legacy")
        logger.info("copy-legacy: %s families -> %s", len(legacy), out_path)
    if args.synthesize_passive:
        synth = synthesize_passive_unique_names(fams, tiers_by_family)
        names = merge_name_maps(names, synth)
        save_names_out(out_path, names, model="synthesize", provider="deterministic")
        logger.info("synthesize-passive: %s families -> %s", len(synth), out_path)

    if args.provider == "skip":
        logger.info("Provider=skip, done (%s families in %s)", len(names), out_path)
        return 0

    should_llm = bool(args.only_passive or args.only_family) or (
        not args.copy_legacy and not args.synthesize_passive
    )
    if not should_llm:
        logger.info(
            "Skipping LLM. Use --only-passive --resume for API generation, or --provider skip."
        )
        return 0

    pending = families_for_llm(
        fams,
        tiers_by_family,
        only_passive=args.only_passive,
        only_family=args.only_family,
        existing=names if args.resume else None,
    )

    if args.dry_run:
        sample = pending[: args.batch_families]
        used = list(collect_used_names(names))[:30]
        print("=== system (excerpt) ===")
        print(build_system_prompt(used)[:600], "...\n")
        print("=== user (first batch) ===")
        print(build_user_prompt(sample)[:2000])
        print(f"\nPending families: {len(pending)}, batches ~{(len(pending) + args.batch_families - 1) // args.batch_families}")
        return 0

    if not pending:
        logger.info("Nothing pending in %s", out_path)
        return 0

    if not has_llm_configured():
        logger.error("OPENROUTER_API_KEY or ROUTERAI_API_KEY required for LLM generation")
        return 1

    chain = _resolve_provider(args.provider)
    if not chain:
        logger.error("No provider for --provider=%s", args.provider)
        return 1

    prov0 = chain[0]
    model = _resolve_model(args.model, prov0)
    use_chain = args.provider == "auto"
    api_providers = None if use_chain else chain
    used_names = collect_used_names(names)
    forbidden = sorted(used_names)[:80]

    system = build_system_prompt(forbidden)
    batches: list[list[dict]] = []
    for i in range(0, len(pending), args.batch_families):
        batches.append(pending[i : i + args.batch_families])

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for idx, batch in enumerate(batches, start=1):
            fids = [b["family_id"] for b in batch]
            logger.info("Batch %s/%s: %s", idx, len(batches), ", ".join(fids[:4]))
            try:
                parsed = await _generate_batch_with_retry(
                    client,
                    model=model,
                    system=system,
                    batch=batch,
                    caller=f"affix names batch {idx}",
                    providers=api_providers,
                    used_names=used_names,
                )
            except Exception as e:
                logger.error("Batch %s failed: %s", idx, e)
                save_names_out(out_path, names, model=model, provider=args.provider)
                return 1

            names = merge_name_maps(names, parsed)
            forbidden = sorted(collect_used_names(names))[:80]
            system = build_system_prompt(forbidden)
            save_names_out(out_path, names, model=model, provider=args.provider)
            logger.info("Checkpoint: %s families", len(names))

            if idx < len(batches) and args.delay > 0:
                await asyncio.sleep(args.delay)

    logger.info("Done: %s families -> %s", len(names), out_path)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate affix display names via LLM")
    parser.add_argument("--batch-families", type=int, default=8, help="Families per API request")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=("auto", "openrouter", "routerai", "skip"),
        help="LLM provider (skip = only --copy-legacy / --synthesize-passive)",
    )
    parser.add_argument("--copy-legacy", action="store_true", help="Fill from hardcoded affix_display_names")
    parser.add_argument(
        "--synthesize-passive",
        action="store_true",
        help="Deterministic unique passive names (no API)",
    )
    parser.add_argument("--only-passive", action="store_true", help="LLM only passive families")
    parser.add_argument("--only-family", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    if not args.copy_legacy and not args.synthesize_passive and args.provider == "skip":
        args.copy_legacy = True

    if args.batch_families < 1:
        parser.error("--batch-families must be >= 1")

    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

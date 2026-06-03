#!/usr/bin/env python3
"""Generate unique funny flavor_ru for all item_base_templates via OpenRouter / RouterAI.

Run from repo root (.env with OPENROUTER_API_KEY or ROUTERAI_API_KEY and OPENROUTER_MODEL):

    python3 scripts/generate_item_flavor_llm.py
    python3 scripts/generate_item_flavor_llm.py --batch-size 30 --model openrouter/healer-alpha
    python3 scripts/generate_item_flavor_llm.py --resume
    python3 scripts/generate_item_flavor_llm.py --dry-run --batch-size 5

Then apply to DB:

    python3 scripts/seed_item_base_flavor.py
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
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.flavor_llm import (  # noqa: E402
    build_system_prompt,
    build_user_prompt,
    load_world_blurb,
    merge_flavor_maps,
    parse_flavors_response,
)
from lib.item_base_catalog import load_item_base_catalog  # noqa: E402

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

DEFAULT_OUT = ROOT / "scripts" / "data" / "item_base_flavor_ru.json"
NARRATIVE_PATH = ROOT / "scripts" / "data" / "narrative_bible.json"


def _load_existing(out_path: Path) -> dict[str, str]:
    if not out_path.is_file():
        return {}
    try:
        raw = json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if str(v or "").strip()}


def _save_out(out_path: Path, flavors: dict[str, str]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {str(k): flavors[str(k)] for k in sorted(flavors, key=lambda x: int(x))}
    out_path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    providers: list[LlmProvider] | None = None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.9,
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
) -> dict[int, str]:
    expected_ids = [int(it["id"]) for it in batch]
    user = build_user_prompt(batch)
    max_tokens = min(8000, max(1200, 80 * len(batch)))

    for attempt in range(2):
        user_msg = user
        if attempt > 0:
            user_msg = user + "\n\nВерни ТОЛЬКО валидный JSON {\"flavors\": {...}} без markdown."
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
            return parse_flavors_response(raw, expected_ids)
        except ValueError as e:
            logger.warning("batch parse failed (attempt %s): %s", attempt + 1, e)
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


async def run(args: argparse.Namespace) -> int:
    catalog = load_item_base_catalog()
    if not catalog:
        logger.error("Catalog empty — check %s", ROOT / "info/item_base_templates_import.sql")
        return 1

    out_path: Path = args.out
    flavors = _load_existing(out_path) if args.resume else {}

    pending = [it for it in catalog if str(it["id"]) not in flavors]
    if args.resume and not pending:
        logger.info("All %s items already in %s", len(catalog), out_path)
        return 0

    if args.dry_run:
        world = load_world_blurb(NARRATIVE_PATH)
        system = build_system_prompt(world)
        sample = pending[: args.batch_size]
        print("=== system (excerpt) ===")
        print(system[:500], "...\n")
        print("=== user (first batch) ===")
        print(build_user_prompt(sample))
        print(f"\nWould process {len(pending)} items in {(len(pending) + args.batch_size - 1) // args.batch_size} batches")
        return 0

    if not has_llm_configured():
        logger.error(
            "Задайте OPENROUTER_API_KEY или ROUTERAI_API_KEY (и OPENROUTER_MODEL) в .env"
        )
        return 1

    chain = _resolve_provider(args.provider)
    if not chain:
        logger.error("No provider for --provider=%s", args.provider)
        return 1

    prov0 = chain[0]
    model = _resolve_model(args.model, prov0)
    use_chain = args.provider == "auto"
    api_providers = None if use_chain else chain
    chain_names = "auto" if use_chain else ",".join(p.name for p in chain)
    logger.info(
        "Providers=%s model=%s batch_size=%d pending=%d total=%d",
        chain_names,
        model,
        args.batch_size,
        len(pending),
        len(catalog),
    )
    if args.batch_size >= len(catalog):
        logger.warning(
            "batch-size=%d covers full catalog — один большой запрос, возможен обрезанный ответ",
            args.batch_size,
        )

    world = load_world_blurb(NARRATIVE_PATH)
    system = build_system_prompt(world)

    batches: list[list[dict]] = []
    for i in range(0, len(pending), args.batch_size):
        batches.append(pending[i : i + args.batch_size])

    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for idx, batch in enumerate(batches, start=1):
            ids = [it["id"] for it in batch]
            logger.info("Batch %s/%s ids %s..%s", idx, len(batches), ids[0], ids[-1])
            try:
                parsed = await _generate_batch_with_retry(
                    client,
                    model=model,
                    system=system,
                    batch=batch,
                    caller=f"item flavor batch {idx}",
                    providers=api_providers,
                )
            except Exception as e:
                logger.error("Batch %s failed: %s", idx, e)
                _save_out(out_path, flavors)
                logger.info("Checkpoint saved to %s (%s entries)", out_path, len(flavors))
                return 1

            flavors = merge_flavor_maps(flavors, parsed)
            _save_out(out_path, flavors)
            logger.info("Checkpoint: %s flavors written", len(flavors))

            if idx < len(batches) and args.delay > 0:
                await asyncio.sleep(args.delay)

    logger.info("Done: %s flavors -> %s", len(flavors), out_path)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate item flavor_ru via LLM (OpenRouter/RouterAI)")
    parser.add_argument("--batch-size", type=int, default=25, help="Items per API request")
    parser.add_argument("--model", type=str, default=None, help="Override OPENROUTER_MODEL")
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=("auto", "openrouter", "routerai"),
        help="LLM provider (auto = chain with 402 fallback)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print prompt sample, no API")
    parser.add_argument("--resume", action="store_true", help="Skip ids already in --out file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output JSON path")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between batches")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")

    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

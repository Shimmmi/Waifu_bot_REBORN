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
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402

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


async def _request_batch(
    *,
    system: str,
    user: str,
    max_tokens: int,
    caller: str,
    preset: str,
) -> str:
    text = await ai_generate(
        user,
        system=system,
        preset=preset,
        caller=caller,
        max_tokens=max_tokens,
        temperature=0.9,
        timeout_sec=120.0,
        post_process_rhythm=False,
    )
    if not text:
        raise RuntimeError("empty LLM response")
    return text


async def _generate_batch_with_retry(
    *,
    system: str,
    batch: list[dict],
    caller: str,
    preset: str,
) -> dict[int, str]:
    expected_ids = [int(it["id"]) for it in batch]
    user = build_user_prompt(batch)
    max_tokens = min(8000, max(1200, 80 * len(batch)))

    for attempt in range(2):
        user_msg = user
        if attempt > 0:
            user_msg = user + "\n\nВерни ТОЛЬКО валидный JSON {\"flavors\": {...}} без markdown."
        raw = await _request_batch(
            system=system,
            user=user_msg,
            max_tokens=max_tokens,
            caller=caller,
            preset=preset,
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

    if not has_text_llm_configured():
        logger.error("Задайте ROUTERAI_API_KEY в .env")
        return 1

    preset = args.preset or settings.ai_default_preset
    logger.info(
        "preset=%s batch_size=%d pending=%d total=%d",
        preset,
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

    for idx, batch in enumerate(batches, start=1):
        ids = [it["id"] for it in batch]
        logger.info("Batch %s/%s ids %s..%s", idx, len(batches), ids[0], ids[-1])
        try:
            parsed = await _generate_batch_with_retry(
                system=system,
                batch=batch,
                caller=f"item flavor batch {idx}",
                preset=preset,
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
    parser.add_argument("--preset", type=str, default=None, help="AI preset (default: fast)")
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

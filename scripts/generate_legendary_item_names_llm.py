#!/usr/bin/env python3
"""Generate legendary item display names via OpenRouter / RouterAI."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

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
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUT = ROOT / "scripts/data/legendary_item_names_ru.json"


async def _request_batch(
    *,
    system: str,
    user: str,
    preset: str,
) -> str:
    text = await ai_generate(
        user,
        system=system,
        preset=preset,
        caller="legendary names",
        max_tokens=4000,
        temperature=0.85,
        timeout_sec=120.0,
        post_process_rhythm=False,
    )
    if not text:
        raise RuntimeError("empty LLM response")
    return text


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
    if not has_text_llm_configured():
        logger.error("ROUTERAI_API_KEY not configured")
        return 1

    preset = args.preset or settings.ai_preset_balance
    initial_count = len(names)
    pending_count = len(pending)

    for i in range(0, len(pending), args.batch_size):
        batch = pending[i : i + args.batch_size]
        ids = [int(t["template_id"]) for t in batch]
        system = build_system_prompt(list(used))
        user = build_user_prompt(batch)
        try:
            raw = await _request_batch(system=system, user=user, preset=preset)
            parsed = parse_names_response(raw, ids, used)
        except Exception as e:
            logger.warning("batch failed: %s", e)
            continue
        for tid, nm in parsed.items():
            names[str(tid)] = nm
        save_names_out(args.out, names, {"preset": preset, "source": "llm"})
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
    parser.add_argument("--preset", type=str, default=None, help="AI preset (default: expert)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-curated", action="store_true", default=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

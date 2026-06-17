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
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUT = ROOT / "scripts/data/legendary_static_affixes.json"


async def _request_batch(
    *,
    system: str,
    user: str,
    caller: str,
    preset: str,
) -> str:
    text = await ai_generate(
        user,
        system=system,
        preset=preset,
        caller=caller,
        max_tokens=min(8000, max(2000, len(user) // 2)),
        temperature=0.7,
        timeout_sec=120.0,
        post_process_rhythm=False,
    )
    if not text:
        raise RuntimeError("empty LLM response")
    return text


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

    if not has_text_llm_configured():
        logger.error("Set ROUTERAI_API_KEY in .env")
        return 1

    preset = args.preset or settings.ai_preset_balance
    system = build_system_prompt()
    profiles = dict(existing)

    by_tier: dict[int, list[dict]] = defaultdict(list)
    for t in pending:
        by_tier[int(t["tier"])].append(t)

    for tier, tier_items in sorted(by_tier.items()):
        catalog = load_affix_catalog_for_tier(tier)
        cat_ids = {str(c["family_id"]) for c in catalog}
        for i in range(0, len(tier_items), args.batch_size):
            batch = tier_items[i : i + args.batch_size]
            ids = [int(t["template_id"]) for t in batch]
            user = build_user_prompt(batch, catalog, tier)
            raw = await _request_batch(
                system=system,
                user=user,
                caller=f"legendary static affixes T{tier}",
                preset=preset,
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
            save_profiles_json(args.out, profiles, {"preset": preset, "source": "llm"})
            if args.delay > 0:
                await asyncio.sleep(args.delay)

    logger.info("Done: %s profiles -> %s", len(profiles), args.out)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--preset", type=str, default=None, help="AI preset (default: expert)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

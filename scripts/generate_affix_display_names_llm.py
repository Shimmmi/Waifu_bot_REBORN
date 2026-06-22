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

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS_DIR / "lib"))
sys.path.insert(0, str(SCRIPTS_DIR))

from affix_name_llm import (  # noqa: E402
    _name_owner_map,
    build_system_prompt,
    build_user_prompt,
    collect_passive_t1_prefix_names,
    collect_used_names,
    copy_legacy_names,
    families_for_llm,
    load_affix_catalog,
    load_names_out,
    merge_name_maps,
    parse_names_response,
    passive_family_ids,
    save_names_out,
    strip_family_names,
    synthesize_passive_unique_names,
)

from waifu_bot.core.config import settings  # noqa: E402
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUT = ROOT / "scripts" / "data" / "affix_display_names_ru.json"
DATA_DIR = ROOT / "scripts" / "data"


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
        temperature=0.85,
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
    used_names: set[str],
    name_owners: dict[str, str],
    passive_t1_prefix_used: set[str] | None = None,
) -> dict[str, dict[str, str]]:
    expected = [it["family_id"] for it in batch]
    user = build_user_prompt(batch)
    max_tokens = min(12000, max(1500, 120 * len(batch) * 10))

    for attempt in range(3):
        user_msg = user
        if attempt > 0:
            user_msg = user + "\n\nВерни ТОЛЬКО валидный JSON без markdown. Имена не должны повторяться между разными family_id в батче."
        raw = await _request_batch(
            system=system,
            user=user_msg,
            max_tokens=max_tokens,
            caller=caller,
            preset=preset,
        )
        try:
            return parse_names_response(
                raw,
                expected,
                used_names=used_names,
                name_owners=name_owners,
                passive_t1_prefix_used=passive_t1_prefix_used,
            )
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("batch parse failed (attempt %s): %s", attempt + 1, e)
            if attempt == 2:
                raise
    raise RuntimeError("unreachable")


async def run(args: argparse.Namespace) -> int:
    fams, tiers_by_family = load_affix_catalog(DATA_DIR)
    out_path: Path = args.out
    names = load_names_out(out_path) if args.resume else {}

    if args.copy_legacy:
        legacy = copy_legacy_names(fams, tiers_by_family, skip_passive=args.skip_passive)
        names = merge_name_maps(names, legacy)
        save_names_out(out_path, names, model="legacy", provider="copy-legacy")
        logger.info("copy-legacy: %s families -> %s", len(legacy), out_path)
    if args.synthesize_passive:
        synth = synthesize_passive_unique_names(fams, tiers_by_family, existing=names)
        if args.resume:
            synth = {k: v for k, v in synth.items() if k not in names}
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

    if args.only_passive and args.force:
        pfids = passive_family_ids(fams)
        names = strip_family_names(names, pfids)
        logger.info("Stripped %s passive families for regen", len(pfids))
    if args.only_family and args.force:
        names = strip_family_names(names, {args.only_family})

    pending = families_for_llm(
        fams,
        tiers_by_family,
        only_passive=args.only_passive,
        only_family=args.only_family,
        existing=names if args.resume and not args.force else None,
        force_regen=args.force,
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

    if not has_text_llm_configured():
        logger.error("ROUTERAI_API_KEY required for LLM generation")
        return 1

    preset = args.preset or settings.ai_default_preset
    if args.only_passive:
        used_names = collect_used_names(names, family_prefix="p_passive_") | collect_used_names(
            names, family_prefix="s_passive_"
        )
        name_owners = _name_owner_map(
            {fid: per for fid, per in names.items() if "passive" in fid}
        )
        passive_t1 = collect_passive_t1_prefix_names(names)
    else:
        used_names = collect_used_names(names)
        name_owners = _name_owner_map(names)
        passive_t1 = None
    forbidden = sorted(used_names)[:120]

    system = build_system_prompt(forbidden)
    batches: list[list[dict]] = []
    for i in range(0, len(pending), args.batch_families):
        batches.append(pending[i : i + args.batch_families])

    for idx, batch in enumerate(batches, start=1):
        fids = [b["family_id"] for b in batch]
        logger.info("Batch %s/%s: %s", idx, len(batches), ", ".join(fids[:4]))
        try:
            parsed = await _generate_batch_with_retry(
                system=system,
                batch=batch,
                caller=f"affix names batch {idx}",
                preset=preset,
                used_names=used_names,
                name_owners=name_owners,
                passive_t1_prefix_used=passive_t1,
            )
        except Exception as e:
            logger.error("Batch %s failed: %s", idx, e)
            if args.only_passive and args.synthesize_on_failure:
                fids = {b["family_id"] for b in batch}
                subset = [f for f in fams if str(f.get("family_id") or "") in fids]
                synth = synthesize_passive_unique_names(subset, tiers_by_family, existing=names)
                names = merge_name_maps(names, synth)
                save_names_out(out_path, names, model=preset, provider="routerai+synth-fallback")
                logger.info("Synthesize fallback for %s families", len(synth))
                name_owners = _name_owner_map(
                    {fid: per for fid, per in names.items() if "passive" in fid}
                )
                passive_t1 = collect_passive_t1_prefix_names(names)
                used_names = collect_used_names(names, family_prefix="p_passive_") | collect_used_names(
                    names, family_prefix="s_passive_"
                )
                continue
            save_names_out(out_path, names, model=preset, provider="routerai")
            return 1

        names = merge_name_maps(names, parsed)
        name_owners = _name_owner_map(names)
        if args.only_passive:
            used_names = collect_used_names(names, family_prefix="p_passive_") | collect_used_names(
                names, family_prefix="s_passive_"
            )
            passive_t1 = collect_passive_t1_prefix_names(names)
        else:
            used_names = collect_used_names(names)
            passive_t1 = None
        forbidden = sorted(used_names)[:120]
        system = build_system_prompt(forbidden)
        save_names_out(out_path, names, model=preset, provider="routerai")
        logger.info("Checkpoint: %s families", len(names))

        if idx < len(batches) and args.delay > 0:
            await asyncio.sleep(args.delay)

    logger.info("Done: %s families -> %s", len(names), out_path)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate affix display names via LLM")
    parser.add_argument("--batch-families", type=int, default=8, help="Families per API request")
    parser.add_argument("--preset", type=str, default=None, help="AI preset (default: fast)")
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        choices=("auto", "skip"),
        help="skip = only --copy-legacy / --synthesize-passive",
    )
    parser.add_argument("--copy-legacy", action="store_true", help="Fill from hardcoded affix_display_names")
    parser.add_argument(
        "--skip-passive",
        action="store_true",
        help="With --copy-legacy, skip passive families (for LLM regen)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if family already exists in output JSON",
    )
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
    parser.add_argument(
        "--synthesize-on-failure",
        action="store_true",
        help="On LLM batch failure (only-passive), fill with deterministic fallback",
    )
    args = parser.parse_args()

    if not args.copy_legacy and not args.synthesize_passive and args.provider == "skip":
        args.copy_legacy = True

    if args.batch_families < 1:
        parser.error("--batch-families must be >= 1")

    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

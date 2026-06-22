#!/usr/bin/env python3
"""Generate amulet fixed-bonus matrix via RouterAI expert fusion preset."""

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

from lib.amulet_bonus_llm import (  # noqa: E402
    DEFAULT_OUT_JSON,
    DEFAULT_OUT_MD,
    LINE_KEYS,
    build_system_prompt,
    build_user_prompt,
    group_amulets_by_line,
    load_amulet_catalog,
    load_matrix_json,
    merge_catalog_with_profiles,
    normalize_profiles,
    parse_profiles_response,
    render_markdown,
    rule_based_profile,
    save_markdown,
    save_matrix_json,
)
from waifu_bot.core.config import settings  # noqa: E402
from waifu_bot.services.ai_service import generate as ai_generate  # noqa: E402
from waifu_bot.services.llm_client import has_text_llm_configured  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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
        max_tokens=min(8000, max(2000, len(user))),
        temperature=0.7,
        timeout_sec=120.0,
        post_process_rhythm=False,
    )
    if not text:
        raise RuntimeError("empty LLM response")
    return text


def _existing_keys(data: dict) -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    for row in data.get("profiles") or []:
        if "name" in row and "tier" in row and "proposed_bonus_key" in row:
            out.add((str(row["name"]), int(row["tier"])))
        elif "name" in row and "tier" in row and "bonus_key" in row:
            out.add((str(row["name"]), int(row["tier"])))
    return out


async def run(args: argparse.Namespace) -> int:
    catalog = load_amulet_catalog()
    if len(catalog) != 34:
        logger.error("Expected 34 amulets, got %d", len(catalog))
        return 1

    groups = group_amulets_by_line(catalog)
    system = build_system_prompt()

    if args.dry_run:
        print(build_system_prompt()[:1200])
        print("---")
        for line_key in LINE_KEYS:
            batch = groups.get(line_key) or []
            if not batch:
                continue
            print(f"\n# line={line_key} count={len(batch)}")
            print(build_user_prompt(line_key, batch)[:1500])
        print(f"\namulet_count={len(catalog)}")
        return 0

    regenerate_lines = {x.strip() for x in args.lines.split(",") if x.strip()}

    existing_data = load_matrix_json(args.out) if args.resume else {"profiles": []}
    done_keys = _existing_keys(existing_data)
    existing_rows = list(existing_data.get("profiles") or [])

    preset = args.preset or settings.ai_preset_balance
    all_profiles: list[dict] = []

    # Re-use completed rows from resume (skip lines flagged for regeneration)
    if args.resume and existing_rows:
        for row in existing_rows:
            key = (str(row["name"]), int(row["tier"]))
            line_key = str(row.get("line_key") or "")
            if line_key in regenerate_lines:
                continue
            if key in done_keys and row.get("proposed_bonus_key"):
                all_profiles.append(row)

    pending_groups: list[tuple[str, list[dict]]] = []
    for line_key in LINE_KEYS:
        batch = groups.get(line_key) or []
        if line_key in regenerate_lines:
            pending = list(batch)
        else:
            pending = [a for a in batch if (a["name"], a["tier"]) not in done_keys]
        if pending:
            pending_groups.append((line_key, pending))

    if not pending_groups and all_profiles:
        logger.info("All profiles present in %s", args.out)
    elif not pending_groups:
        logger.info("No API calls needed; generating rule-based matrix")
        for line_key in LINE_KEYS:
            for amulet in groups.get(line_key) or []:
                all_profiles.append(
                    merge_catalog_with_profiles([amulet], [rule_based_profile(amulet)])[0]
                )
    else:
        if not has_text_llm_configured():
            logger.warning("ROUTERAI_API_KEY not set — rule-based fallback for all pending")
            for line_key, pending in pending_groups:
                for amulet in pending:
                    prof = rule_based_profile(amulet)
                    all_profiles.append(merge_catalog_with_profiles([amulet], [prof])[0])
        else:
            for line_key, pending in pending_groups:
                used_in_line: set[str] = set()
                for row in all_profiles:
                    if str(row.get("line_key") or "") == line_key:
                        used_in_line.add(
                            str(row.get("proposed_bonus_key") or row.get("bonus_key") or "")
                        )
                chunk_size = max(1, int(args.batch_size))
                for i in range(0, len(pending), chunk_size):
                    chunk = pending[i : i + chunk_size]
                    user = build_user_prompt(line_key, chunk)
                    try:
                        raw = await _request_batch(
                            system=system,
                            user=user,
                            caller=f"amulet bonus matrix {line_key} chunk {i // chunk_size + 1}",
                            preset=preset,
                        )
                        parsed = parse_profiles_response(raw, chunk)
                        normalized = normalize_profiles(parsed, chunk)
                        # Re-validate uniqueness within line including prior chunks
                        for idx, prof in enumerate(normalized):
                            if prof["bonus_key"] in used_in_line:
                                am = next(a for a in chunk if a["name"] == prof["name"])
                                prof = rule_based_profile(am, used_keys=used_in_line)
                                prof["line_key"] = am["line_key"]
                                prof["source"] = "rule_based"
                            used_in_line.add(prof["bonus_key"])
                            normalized[idx] = prof
                        merged = merge_catalog_with_profiles(chunk, normalized)
                        all_profiles.extend(merged)
                        save_matrix_json(
                            args.out,
                            sorted(all_profiles, key=lambda r: (r["line_key"], r["tier"], r["name"])),
                            meta={"preset": preset, "source": "llm", "partial": True},
                        )
                    except Exception as exc:
                        logger.warning(
                            "LLM failed for %s chunk %d: %s — rule-based fallback",
                            line_key,
                            i // chunk_size + 1,
                            exc,
                        )
                        for amulet in chunk:
                            prof = rule_based_profile(amulet, used_keys=used_in_line)
                            used_in_line.add(prof["bonus_key"])
                            all_profiles.append(merge_catalog_with_profiles([amulet], [prof])[0])
                    if args.delay > 0:
                        await asyncio.sleep(args.delay)

    # Ensure full set
    profile_keys = {(r["name"], r["tier"]) for r in all_profiles}
    for amulet in catalog:
        key = (amulet["name"], amulet["tier"])
        if key not in profile_keys:
            prof = rule_based_profile(amulet)
            all_profiles.append(merge_catalog_with_profiles([amulet], [prof])[0])

    all_profiles.sort(key=lambda r: (r["line_key"], r["tier"], r["name"]))
    meta = {"preset": preset, "source": "llm" if has_text_llm_configured() else "rule_based"}
    save_matrix_json(args.out, all_profiles, meta=meta)

    md = render_markdown(all_profiles, meta=meta)
    save_markdown(args.out_md, md)
    logger.info("Wrote %s and %s (%d amulets)", args.out, args.out_md, len(all_profiles))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", type=str, default=None, help="AI preset (default: expert)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--batch-size", type=int, default=5, help="Amulets per LLM request within a line")
    parser.add_argument("--lines", type=str, default="", help="Comma-separated line keys to regenerate (vit_str,int_dex,cha_luk,restricted)")
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

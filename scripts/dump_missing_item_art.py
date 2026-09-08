#!/usr/bin/env python3
"""Dump a JSONL queue of item WebP placeholders (< 3 KB) with generation prompts.

Does not call any image API. Prompts come from build_item_pixel_art_prompt().

    python3 scripts/dump_missing_item_art.py
    python3 scripts/dump_missing_item_art.py --dry-run --limit 20
    python3 scripts/dump_missing_item_art.py --skip-generic --skip-flat
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

ITEM_WEBP = ROOT / "static" / "game" / "items" / "webp"
CANONICAL_NAMES = ROOT / "scripts" / "data" / "item_base_template_canonical_names.json"
ITEM_TEMPLATES = ROOT / "scripts" / "data" / "item_templates.json"
DEFAULT_OUT = ROOT / "info" / "art_generation_prompts" / "missing_item_art.jsonl"
MIN_PLACEHOLDER_BYTES = 3072


def _slug_from_art_key(art_key: str) -> str | None:
    parts = art_key.split("/")
    if not parts:
        return None
    if parts[0] == "legendary" and len(parts) >= 3:
        return parts[-1]
    if len(parts) >= 2:
        return parts[-1]
    return None


def _queue_rank(art_key: str) -> int:
    """named category/slug → legendary → generic → flat."""
    if art_key.startswith("legendary/"):
        return 1
    if art_key == "generic" or art_key.startswith("generic/"):
        return 2
    if "/" not in art_key:
        return 3
    return 0


def _is_flat_key(art_key: str) -> bool:
    return "/" not in art_key


def _is_generic_key(art_key: str) -> bool:
    return art_key == "generic" or art_key.startswith("generic/")


def _build_slug_to_name_map() -> dict[str, str]:
    from waifu_bot.services.item_art import slugify_item_base_name

    slug_to_name: dict[str, str] = {}
    if CANONICAL_NAMES.is_file():
        data = json.loads(CANONICAL_NAMES.read_text(encoding="utf-8"))
        for name in (data.get("names") or {}).values():
            slug = slugify_item_base_name(str(name))
            slug_to_name.setdefault(slug, str(name))
    return slug_to_name


def _load_seed_meta() -> dict[str, tuple[str | None, str | None]]:
    """art_key -> (display_label, weapon_type) from JSON seeds."""
    from waifu_bot.services.item_art import derive_item_art_key, with_legendary_art_prefix

    found: dict[str, tuple[str | None, str | None]] = {}
    slug_to_name = _build_slug_to_name_map()

    def add_key(art_key: str, label: str | None, wt: str | None) -> None:
        prev = found.get(art_key)
        if art_key not in found:
            found[art_key] = (label, wt)
            return
        if label and not prev[0]:
            found[art_key] = (label, wt or prev[1])
        elif wt and not prev[1]:
            found[art_key] = (prev[0], wt)

    for slug, name in slug_to_name.items():
        add_key(slug, name, None)

    if ITEM_TEMPLATES.is_file():
        for row in json.loads(ITEM_TEMPLATES.read_text(encoding="utf-8")):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            wt = (row.get("weapon_type") or "") or None
            if isinstance(wt, str):
                wt = wt.strip() or None
            ak = derive_item_art_key(row.get("slot_type"), wt, name, display_name=name)
            add_key(ak, name, wt)
            add_key(with_legendary_art_prefix(ak), name, wt)

    return found


def _orb_placeholder_hashes() -> set[str]:
    """SHA-256 of the stub library ``orb/t1.webp`` … ``t10.webp`` (cracked-orb copies)."""
    hashes: set[str] = set()
    orb_dir = ITEM_WEBP / "orb"
    for t in range(1, 11):
        p = orb_dir / f"t{t}.webp"
        if p.is_file():
            hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
    return hashes


def _is_source_orb_stub(rel: Path) -> bool:
    """Keep ``orb/tN.webp`` as the stub library; do not queue it for unique art."""
    return len(rel.parts) == 2 and rel.parts[0] == "orb"


def _best_reference(_art_dir: Path, _min_bytes: int) -> str | None:
    """Never pass a file as an image reference.

    Most t1 assets are byte-identical copies of the cracked-orb stub; using them
    as GenerateImage references copies the placeholder instead of the named item.
    """
    return None


def scan_placeholders(
    *,
    min_bytes: int,
    skip_generic: bool,
    skip_flat: bool,
    limit: int | None,
) -> list[dict]:
    from waifu_bot.services.item_art_generation import (
        build_item_pixel_art_prompt,
        normalize_art_key,
    )

    meta = _load_seed_meta()
    slug_to_name = _build_slug_to_name_map()
    orb_hashes = _orb_placeholder_hashes()
    rows: list[dict] = []

    if not ITEM_WEBP.is_dir():
        return rows

    for path in ITEM_WEBP.rglob("*.webp"):
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        size = len(raw)
        rel = path.relative_to(ITEM_WEBP)
        if _is_source_orb_stub(rel):
            continue
        is_orb_copy = hashlib.sha256(raw).hexdigest() in orb_hashes
        if size >= min_bytes and not is_orb_copy:
            continue
        stem = path.stem
        if not (stem.startswith("t") and stem[1:].isdigit()):
            continue
        tier = int(stem[1:])
        if tier < 1 or tier > 10:
            continue
        parts = rel.parts
        if len(parts) < 2:
            continue
        raw_key = "/".join(parts[:-1])
        ak = normalize_art_key(raw_key)
        if not ak:
            continue
        if skip_generic and _is_generic_key(ak):
            continue
        if skip_flat and _is_flat_key(ak):
            continue

        label: str | None = None
        wt: str | None = None
        if ak in meta:
            label, wt = meta[ak]
        if not label:
            slug = _slug_from_art_key(ak)
            if slug:
                label = slug_to_name.get(slug)

        prompt = build_item_pixel_art_prompt(
            ak, tier, weapon_type=wt, display_label=label
        )
        ref = _best_reference(path.parent, min_bytes)
        rows.append(
            {
                "art_key": ak,
                "tier": tier,
                "path": str(path),
                "size_bytes": size,
                "display_label": label,
                "weapon_type": wt,
                "prompt": prompt,
                "reference_path": ref,
                "queue_rank": _queue_rank(ak),
            }
        )

    rows.sort(key=lambda r: (r["queue_rank"], r["art_key"], r["tier"]))
    if limit is not None:
        rows = rows[: max(0, limit)]
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dump missing item-art placeholders (< min-bytes) as JSONL with prompts."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help=f"JSONL output (default: {DEFAULT_OUT})",
    )
    parser.add_argument("--min-bytes", type=int, default=MIN_PLACEHOLDER_BYTES)
    parser.add_argument("--skip-generic", action="store_true")
    parser.add_argument("--skip-flat", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts and first few rows; do not write the file",
    )
    args = parser.parse_args()

    rows = scan_placeholders(
        min_bytes=args.min_bytes,
        skip_generic=args.skip_generic,
        skip_flat=args.skip_flat,
        limit=args.limit,
    )
    ranks: dict[int, int] = {}
    for r in rows:
        ranks[int(r["queue_rank"])] = ranks.get(int(r["queue_rank"]), 0) + 1

    print(f"missing={len(rows)} min_bytes={args.min_bytes}")
    print(
        "ranks named={n} legendary={l} generic={g} flat={f}".format(
            n=ranks.get(0, 0),
            l=ranks.get(1, 0),
            g=ranks.get(2, 0),
            f=ranks.get(3, 0),
        )
    )
    if args.dry_run:
        for r in rows[:5]:
            print(
                f"  {r['art_key']} t{r['tier']} {r['size_bytes']}B "
                f"label={r['display_label']!r} ref={r['reference_path']}"
            )
        return 0

    out: Path = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

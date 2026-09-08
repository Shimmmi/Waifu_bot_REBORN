#!/usr/bin/env python3
"""Convert a Cursor-generated PNG into item WebP and persist (no image API).

    python3 scripts/ingest_cursor_item_art.py \\
        --src /path/to/item_plasch_vetra_t6.png \\
        --art-key armor/plasch_vetra --tier 6

Resume: if the destination WebP already exists and is >= --min-bytes, skip
unless --force. If the converted image is still under --min-bytes, abort
without replacing a placeholder.

DB upsert uses persist_item_art_webp(); --no-db writes the file only.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MIN_PLACEHOLDER_BYTES = 3072


def _dest_path(art_key: str, tier: int) -> Path:
    from waifu_bot.paths import static_game_directory
    from waifu_bot.services.item_art import normalize_tier
    from waifu_bot.services.item_art_generation import normalize_art_key

    ak = normalize_art_key(art_key)
    if not ak:
        raise SystemExit(f"invalid art_key: {art_key!r}")
    t = normalize_tier(tier)
    return static_game_directory() / "items" / "webp" / ak / f"t{t}.webp"


def png_to_webp_bytes(src: Path) -> bytes:
    from waifu_bot.services.item_art_generation import _image_bytes_to_webp

    raw = src.read_bytes()
    webp = _image_bytes_to_webp(raw)
    if not webp:
        raise SystemExit(f"webp conversion failed: {src}")
    return webp


async def _persist(art_key: str, tier: int, webp: bytes) -> str:
    from waifu_bot.db.session import get_session
    from waifu_bot.services.item_art import persist_item_art_webp

    async for session in get_session():
        return await persist_item_art_webp(session, art_key, tier, webp)
    raise RuntimeError("no db session")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Cursor PNG into item WebP art.")
    parser.add_argument("--src", type=Path, required=True, help="Source PNG (or any Pillow-readable image)")
    parser.add_argument("--art-key", required=True)
    parser.add_argument("--tier", type=int, required=True)
    parser.add_argument("--min-bytes", type=int, default=MIN_PLACEHOLDER_BYTES)
    parser.add_argument("--force", action="store_true", help="Overwrite even if dest already >= min-bytes")
    parser.add_argument("--no-db", action="store_true", help="Write file only, skip item_art upsert")
    args = parser.parse_args()

    src: Path = args.src
    if not src.is_file():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 2

    dest = _dest_path(args.art_key, args.tier)
    size_before = dest.stat().st_size if dest.is_file() else 0
    if not args.force and dest.is_file() and size_before >= args.min_bytes:
        print(f"skip already_ok dest={dest} size={size_before}")
        return 0

    webp = png_to_webp_bytes(src)
    if len(webp) < args.min_bytes:
        print(
            f"ERROR: converted webp too small ({len(webp)} < {args.min_bytes}); "
            "leaving placeholder untouched",
            file=sys.stderr,
        )
        return 4

    print(f"src={src} src_bytes={src.stat().st_size}")
    print(f"art_key={args.art_key} tier={args.tier}")
    print(f"dest={dest} size_before={size_before} webp_bytes={len(webp)}")

    if args.no_db:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(webp)
        print("wrote_file_without_db=True")
    else:
        try:
            url = asyncio.run(_persist(args.art_key, args.tier, webp))
            print(f"persisted_url={url}")
        except Exception as exc:
            print(f"persist_failed={type(exc).__name__}:{exc}", file=sys.stderr)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(webp)
            print("wrote_file_without_db=True")

    size_after = dest.stat().st_size if dest.is_file() else 0
    print(f"size_after={size_after}")
    if size_after < args.min_bytes:
        print("ERROR: dest still under min-bytes", file=sys.stderr)
        return 4
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

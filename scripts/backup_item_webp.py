#!/usr/bin/env python3
"""Copy live item WebP (not orb stubs) outside the repo so placeholder scripts cannot clobber them.

    python3 scripts/backup_item_webp.py
    python3 scripts/backup_item_webp.py --restore  # restore live files onto stubs only
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEM_WEBP = ROOT / "static" / "game" / "items" / "webp"
BACKUP_ROOT = Path("/opt/waifu-item-webp-backup")
MIN_LIVE_BYTES = 3072


def _orb_hashes() -> set[str]:
    hashes: set[str] = set()
    orb = ITEM_WEBP / "orb"
    for t in range(1, 11):
        p = orb / f"t{t}.webp"
        if p.is_file():
            hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
    return hashes


def _is_live(path: Path, orb_hashes: set[str]) -> bool:
    if not path.is_file():
        return False
    raw = path.read_bytes()
    if len(raw) < MIN_LIVE_BYTES:
        return False
    return hashlib.sha256(raw).hexdigest() not in orb_hashes


def backup() -> int:
    orb = _orb_hashes()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    bytes_n = 0
    for src in ITEM_WEBP.rglob("*.webp"):
        if not _is_live(src, orb):
            continue
        rel = src.relative_to(ITEM_WEBP)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        n += 1
        bytes_n += src.stat().st_size
    latest = BACKUP_ROOT / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(dest)
    print(f"backup {n} live webp ({bytes_n} bytes) -> {dest}")
    print(f"latest -> {dest}")
    return 0


def restore() -> int:
    src_root = BACKUP_ROOT / "latest"
    if not src_root.exists():
        print("ERROR: no backup at", src_root, file=sys.stderr)
        return 2
    src_root = src_root.resolve()
    orb = _orb_hashes()
    n = 0
    for src in src_root.rglob("*.webp"):
        if not _is_live(src, orb):
            continue
        rel = src.relative_to(src_root)
        dst = ITEM_WEBP / rel
        if _is_live(dst, orb):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    print(f"restore {n} live webp from {src_root} onto stubs/missing")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup or restore live item WebP outside the repo.")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    return restore() if args.restore else backup()


if __name__ == "__main__":
    raise SystemExit(main())

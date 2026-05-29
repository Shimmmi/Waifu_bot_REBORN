#!/usr/bin/env python3
"""Measure WebApp API response sizes (baseline for performance work).

Usage (dev server running, APP_ENV=dev):
  python scripts/measure_webapp_api.py --player-id 123456789
  python scripts/measure_webapp_api.py --base-url http://127.0.0.1:8000 --player-id 123456789

Prints JSON with byte sizes and timings for endpoints used on tavern/dungeons load.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def fetch(
    base: str,
    path: str,
    player_id: int,
    *,
    label: str | None = None,
    dev_token: str | None = None,
) -> dict[str, Any]:
    url = f"{base.rstrip('/')}{path}"
    headers = {"X-Player-Id": str(player_id)}
    if dev_token:
        headers["X-Dev-Token"] = dev_token
    req = urllib.request.Request(url, headers=headers)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return {
                "label": label or path,
                "path": path,
                "status": resp.status,
                "bytes": len(body),
                "ms": round(elapsed_ms, 1),
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        body = e.read()
        return {
            "label": label or path,
            "path": path,
            "status": e.code,
            "bytes": len(body),
            "ms": round(elapsed_ms, 1),
            "error": body[:200].decode("utf-8", errors="replace"),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure WebApp API payload sizes")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API origin (no /api suffix)")
    parser.add_argument("--player-id", type=int, required=True, help="Telegram player id (X-Player-Id)")
    parser.add_argument(
        "--dev-token",
        default=None,
        help="X-Dev-Token for browser dev bypass (or set DEV_BROWSER_TOKEN env)",
    )
    args = parser.parse_args()
    dev_token = args.dev_token or __import__("os").environ.get("DEV_BROWSER_TOKEN")
    api = f"{args.base_url}/api"

    endpoints = [
        ("/profile", "profile_full"),
        ("/profile?lite=1", "profile_lite"),
        ("/dungeons/active?include_log=0", "dungeons_active_lite"),
        ("/dungeons/active?include_log=1", "dungeons_active_full"),
        ("/expeditions/slots", "expeditions_slots"),
        ("/expeditions/active", "expeditions_active"),
        ("/tavern/available", "tavern_available"),
        ("/tavern/squad", "tavern_squad"),
        ("/tavern/reserve", "tavern_reserve"),
        ("/dungeons/plus/status", "dungeons_plus_status"),
        ("/dungeons?act=1&type=1", "dungeons_list_act1"),
    ]

    results = [fetch(api, path, args.player_id, label=label, dev_token=dev_token) for path, label in endpoints]
    total_bytes = sum(r["bytes"] for r in results if r.get("status") == 200)
    dungeons_page_est = sum(
        r["bytes"]
        for r in results
        if r["label"]
        in {
            "profile_lite",
            "dungeons_active_full",
            "expeditions_slots",
            "expeditions_active",
            "dungeons_plus_status",
            "dungeons_list_act1",
        }
        and r.get("status") == 200
    )
    tavern_page_est = sum(
        r["bytes"]
        for r in results
        if r["label"]
        in {
            "profile_lite",
            "dungeons_active_lite",
            "expeditions_slots",
            "expeditions_active",
            "tavern_available",
        }
        and r.get("status") == 200
    )

    report = {
        "player_id": args.player_id,
        "endpoints": results,
        "totals": {
            "all_measured_bytes": total_bytes,
            "dungeons_page_optimized_est_bytes": dungeons_page_est,
            "tavern_page_optimized_est_bytes": tavern_page_est,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    failed = [r for r in results if r.get("status") != 200]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

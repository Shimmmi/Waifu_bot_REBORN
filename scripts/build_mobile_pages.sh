#!/usr/bin/env bash
# Mobile pages live under src/waifu_bot/webapp/mobile/ (hand-maintained shell).
# This script is a no-op checklist / sync hook analogous to build_steam_pages.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE="$ROOT/src/waifu_bot/webapp/mobile"
for f in login.html shell.html mobile-shell.css mobile-shell.js; do
  if [[ ! -f "$MOBILE/$f" ]]; then
    echo "[FAIL] missing $MOBILE/$f"
    exit 1
  fi
done
echo "[OK] mobile pages present in $MOBILE"
echo "Capacitor entry: /webapp/mobile/login.html?mobileClient=1"
echo "Shell: /webapp/mobile/shell.html?mobileClient=1"
echo "TG link code helper: /webapp/mobile_link.html"

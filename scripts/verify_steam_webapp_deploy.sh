#!/usr/bin/env bash
# Verify the staging API serves current Steam desktop webapp assets (not stale image/cache).
set -euo pipefail

BASE="${WAIFU_BACKEND_URL:-http://127.0.0.1:18000}"
export BASE
FAIL=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "[OK] $name"
  else
    echo "[FAIL] $name" >&2
    FAIL=1
  fi
}

check "GET /health" curl -sf "${BASE}/health" >/dev/null

check "desktop-theme.css has drag regions" \
  bash -c 'curl -sf "$BASE/webapp/desktop-theme.css" | grep -q "app-region: drag"'

check "overlay.js has ov-status-toast" \
  bash -c 'curl -sf "$BASE/webapp/pages/overlay.js" | grep -q "ov-status-toast"'

check "overlay.js has no flashStatus" \
  bash -c 'text=$(curl -sf "$BASE/webapp/pages/overlay.js") && ! echo "$text" | grep -q "flashStatus"'

check "app.min.js uses /webapp/desktop-theme.css" \
  bash -c 'curl -sf "$BASE/webapp/bundle/app.min.js" | grep -q "/webapp/desktop-theme"'

check "desktop-theme.css has titlebar drag strip" \
  bash -c 'curl -sf "$BASE/webapp/desktop-theme.css" | grep -q "desktop-titlebar"'

check "overlay.js uses setMonsterTargetImage placeholder" \
  bash -c 'curl -sf "$BASE/webapp/pages/overlay.js" | grep -q "setMonsterTargetImage"'

STEAM_DEV="${WAIFU_STEAM_TICKET_DEV:-}"
if [[ -n "$STEAM_DEV" ]]; then
  export STEAM_DEV
  check "GET /api/profile?lite=1 (Steam dev ticket)" \
    bash -c 'curl -sf -H "X-Steam-Ticket-Dev: ${STEAM_DEV}" "${BASE}/api/profile?lite=1" >/dev/null'
  check "GET /api/shop/inventory?act=1 (Steam dev ticket)" \
    bash -c 'curl -sf -H "X-Steam-Ticket-Dev: ${STEAM_DEV}" "${BASE}/api/shop/inventory?act=1" >/dev/null'
else
  echo "[SKIP] Steam API auth checks (set WAIFU_STEAM_TICKET_DEV to enable)"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo >&2
  echo "Deploy verification failed. Rebuild api image:" >&2
  echo "  docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build --wait" >&2
  exit 1
fi

echo "All Steam webapp deploy checks passed (${BASE})."

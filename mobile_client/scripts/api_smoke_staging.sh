#!/usr/bin/env bash
# Backend smoke for activity economy (no Android device required).
# Usage:
#   export WAIFU_MOBILE_BACKEND_URL=https://staging.example
#   export WAIFU_LINK_CODE=ABCD1234          # from POST /api/auth/link_code as Telegram user
#   ./scripts/api_smoke_staging.sh
set -euo pipefail

BASE="${WAIFU_MOBILE_BACKEND_URL:?Set WAIFU_MOBILE_BACKEND_URL}"
BASE="${BASE%/}"
SUB="${WAIFU_GOOGLE_SUB_DEV:-smoke-google-sub-1}"
CODE="${WAIFU_LINK_CODE:-}"

echo "== Backend: $BASE =="

echo "-- health / webapp --"
curl -fsS -o /dev/null -w "activity.html HTTP %{http_code}\n" "$BASE/webapp/activity.html?mobileClient=1&economy=activity" || {
  echo "[FAIL] cannot fetch activity.html"
  exit 1
}

if [[ -z "$CODE" ]]; then
  echo "[WARN] WAIFU_LINK_CODE not set — skipping auth/claim smoke."
  echo "Get a code: authenticated POST $BASE/api/auth/link_code (Telegram WebApp)."
  exit 0
fi

echo "-- google login + link --"
LOGIN="$(curl -fsS -X POST "$BASE/api/auth/mobile/google" \
  -H 'Content-Type: application/json' \
  -d "{\"google_sub_dev\":\"$SUB\",\"link_code\":\"$CODE\"}")"
echo "$LOGIN" | head -c 400; echo
SESSION="$(echo "$LOGIN" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("desktop_session",""))')"
if [[ -z "$SESSION" ]]; then
  echo "[FAIL] no desktop_session in login response"
  exit 1
fi

AUTH=(-H "X-Desktop-Session: $SESSION")

echo "-- activity status --"
curl -fsS "${AUTH[@]}" "$BASE/api/activity/status" | python3 -m json.tool | head -40

echo "-- claim 2 units (expect no hit if min_chars=3) --"
curl -fsS -X POST "${AUTH[@]}" "$BASE/api/activity/input/claim" \
  -H 'Content-Type: application/json' \
  -d '{"source":"mobile_steps","units":2,"client_counter_total":1002}' | python3 -m json.tool | head -40

echo "-- claim 3 more units --"
curl -fsS -X POST "${AUTH[@]}" "$BASE/api/activity/input/claim" \
  -H 'Content-Type: application/json' \
  -d '{"source":"mobile_steps","units":3,"client_counter_total":1005}' | python3 -m json.tool | head -60

echo "[OK] API smoke finished (hits_applied depends on active activity dungeon)."

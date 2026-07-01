#!/usr/bin/env bash
# Verify Telegram Mini App can be embedded (no blocking X-Frame-Options on webapp URL).
set -euo pipefail

BASE="${1:-https://shimmirpgbot.ru}"
BASE="${BASE%/}"

fail=0

check_url() {
  local url="$1"
  local label="$2"
  local curl_extra="${3:-}"
  echo "==> $label: $url"
  local headers
  headers="$(curl -fsSI $curl_extra "$url" 2>/dev/null || true)"
  if [[ -z "$headers" ]]; then
    echo "FAIL: could not fetch headers"
    fail=1
    return
  fi
  echo "$headers" | grep -iE '^(HTTP/|content-security-policy|x-frame-options):' || true
  if echo "$headers" | grep -qi '^x-frame-options:[[:space:]]*sameorigin'; then
    echo "FAIL: X-Frame-Options: SAMEORIGIN blocks Telegram iframe"
    fail=1
  fi
  if echo "$headers" | grep -qi '^x-frame-options:[[:space:]]*deny'; then
    echo "FAIL: X-Frame-Options: DENY blocks Telegram iframe"
    fail=1
  fi
}

check_url "$BASE/webapp/index.html" "WebApp entry"
check_url "$BASE/" "Site root (should redirect or allow embed)" "-X GET -L"

if [[ "$fail" -ne 0 ]]; then
  echo
  echo "Headers check failed. For nginx: do not add X-Frame-Options on /webapp/ proxy."
  exit 1
fi

echo
echo "OK: no blocking X-Frame-Options on checked URLs"

#!/usr/bin/env bash
# Summarize what smoke can run in this environment.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Smoke capability report =="
if [[ -d android ]]; then echo "[OK] android/ project present"; else echo "[MISS] android/"; fi

if [[ -n "${ANDROID_HOME:-}${ANDROID_SDK_ROOT:-}" ]] && command -v adb >/dev/null 2>&1; then
  echo "[OK] Device tooling available — run: npm run android:apk && npm run android:install && npm run android:smoke"
else
  echo "[SKIP] No ANDROID_HOME/adb here — build/install/device smoke must run on a laptop with Android SDK"
fi

if [[ -n "${WAIFU_MOBILE_BACKEND_URL:-}" ]]; then
  echo "[OK] WAIFU_MOBILE_BACKEND_URL set — attempting API smoke"
  if [[ -n "${WAIFU_LINK_CODE:-}" ]]; then
    bash scripts/api_smoke_staging.sh
  else
    echo "[SKIP] WAIFU_LINK_CODE unset — only probing activity.html"
    BASE="${WAIFU_MOBILE_BACKEND_URL%/}"
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/webapp/activity.html?mobileClient=1&economy=activity" || echo 000)"
    echo "activity.html → HTTP $code"
  fi
else
  echo "[SKIP] WAIFU_MOBILE_BACKEND_URL unset — set it to run npm run android:api-smoke"
fi

echo
echo "Full device checklist: docs/MOBILE_ANDROID_SMOKE.md"
echo "[OK] smoke_report finished"

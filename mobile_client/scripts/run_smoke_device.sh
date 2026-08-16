#!/usr/bin/env bash
# Launch app and filter logcat for StepCounter / WebView / Capacitor errors.
# Functional API smoke (auth/dungeon/claim) is documented below — run against staging with curl.
set -euo pipefail

PKG="ru.shimmirpgbot.waifu.activity"
ACTIVITY="$PKG/.MainActivity"

if ! command -v adb >/dev/null 2>&1; then
  if [[ -n "${ANDROID_HOME:-}" && -x "$ANDROID_HOME/platform-tools/adb" ]]; then
    export PATH="$ANDROID_HOME/platform-tools:$PATH"
  else
    echo "[FAIL] adb not found"
    exit 1
  fi
fi

echo "== Launch $ACTIVITY =="
adb shell am force-stop "$PKG" || true
adb shell am start -n "$ACTIVITY"
sleep 2

echo "== logcat (Ctrl+C to stop) =="
echo "Filters: WaifuStepCounter, chromium, Capacitor, AndroidRuntime"
adb logcat -c || true
adb logcat -v time \
  '*:S' \
  'WaifuStepCounter:D' \
  'Capacitor:I' \
  'chromium:E' \
  'AndroidRuntime:E' \
  'Console:I'

# Manual API smoke (staging) — print checklist for operator:
# 1) POST /api/auth/link_code (Telegram WebApp on staging)
# 2) POST /api/auth/mobile/google {"google_sub_dev":"...","link_code":"..."}
# 3) GET /api/activity/status with X-Desktop-Session
# 4) POST /api/dungeons/{id}/start?economy=activity
# 5) POST /api/activity/input/claim {"source":"mobile_steps","units":3,"client_counter_total":N}

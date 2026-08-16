#!/usr/bin/env bash
# adb install -r latest debug APK
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK="${1:-$ROOT/android/app/build/outputs/apk/debug/app-debug.apk}"

if [[ ! -f "$APK" ]]; then
  echo "[FAIL] APK not found: $APK"
  echo "Build first: ./scripts/build_debug_apk.sh"
  exit 1
fi

if ! command -v adb >/dev/null 2>&1; then
  if [[ -n "${ANDROID_HOME:-}" && -x "$ANDROID_HOME/platform-tools/adb" ]]; then
    export PATH="$ANDROID_HOME/platform-tools:$PATH"
  else
    echo "[FAIL] adb not on PATH"
    exit 1
  fi
fi

DEVICES="$(adb devices | awk 'NR>1 && $2=="device" {print $1}')"
if [[ -z "$DEVICES" ]]; then
  echo "[FAIL] No adb device/emulator in 'device' state."
  adb devices
  exit 1
fi

echo "Installing $APK ..."
adb install -r "$APK"
echo "[OK] Installed. Launch: adb shell am start -n ru.shimmirpgbot.waifu.activity/.MainActivity"

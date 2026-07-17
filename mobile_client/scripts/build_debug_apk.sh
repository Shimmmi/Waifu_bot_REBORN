#!/usr/bin/env bash
# Build debug APK: npm ci → cap sync → gradlew assembleDebug
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d android ]]; then
  echo "[FAIL] mobile_client/android/ missing."
  echo "Run first: ./scripts/setup_android_project.sh"
  exit 1
fi

./scripts/check_android_dev_env.sh || {
  echo "[FAIL] Fix environment before building."
  exit 1
}

echo "== npm ci =="
npm ci

node scripts/write_capacitor_config.js
node scripts/sync-web-placeholder.js
node scripts/inject_bridge_into_www.js

echo "== npx cap sync android =="
npx cap sync android

echo "== ./gradlew assembleDebug =="
cd android
chmod +x gradlew 2>/dev/null || true
./gradlew assembleDebug
cd "$ROOT"

APK="$ROOT/android/app/build/outputs/apk/debug/app-debug.apk"
if [[ ! -f "$APK" ]]; then
  echo "[FAIL] APK not found at $APK"
  find "$ROOT/android/app/build/outputs" -name '*.apk' 2>/dev/null || true
  exit 1
fi

echo
echo "[OK] Debug APK: $APK"
echo "Install: ./scripts/install_debug_apk.sh"
ls -lh "$APK"

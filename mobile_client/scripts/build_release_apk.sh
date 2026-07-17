#!/usr/bin/env bash
# Build signed release APK / AAB. Requires mobile_client/android/keystore.properties
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROPS="$ROOT/android/keystore.properties"
if [[ ! -f "$PROPS" ]]; then
  echo "[FAIL] Missing $PROPS"
  echo "Copy android/keystore.properties.example → android/keystore.properties and fill paths/passwords."
  exit 1
fi

if [[ ! -d android ]]; then
  echo "[FAIL] Run ./scripts/setup_android_project.sh first"
  exit 1
fi

./scripts/check_android_dev_env.sh
npm ci
node scripts/inject_bridge_into_www.js
npx cap sync android

cd android
chmod +x gradlew 2>/dev/null || true

TARGET="${1:-apk}"
if [[ "$TARGET" == "bundle" || "$TARGET" == "aab" ]]; then
  ./gradlew bundleRelease
  OUT="app/build/outputs/bundle/release/app-release.aab"
else
  ./gradlew assembleRelease
  OUT="app/build/outputs/apk/release/app-release.apk"
fi

cd "$ROOT"
if [[ ! -f "android/$OUT" ]]; then
  echo "[FAIL] Output not found: android/$OUT"
  exit 1
fi
echo "[OK] Release artifact: $ROOT/android/$OUT"
ls -lh "android/$OUT"

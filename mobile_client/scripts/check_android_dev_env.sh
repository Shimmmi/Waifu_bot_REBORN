#!/usr/bin/env bash
# Verify local machine can build the Waifu Activity debug APK.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

ok() { echo "[OK] $*"; }
bad() { echo "[FAIL] $*"; FAIL=1; }
warn() { echo "[WARN] $*"; }

echo "== Waifu Mobile Android env check =="
echo "mobile_client: $ROOT"

# Node
if command -v node >/dev/null 2>&1; then
  NODE_V="$(node -v | sed 's/^v//')"
  NODE_MAJOR="${NODE_V%%.*}"
  if [[ "$NODE_MAJOR" -ge 20 ]]; then
    ok "Node $NODE_V"
  elif [[ "$NODE_MAJOR" -ge 18 ]]; then
    warn "Node $NODE_V (recommend >= 20; 18 may work for Capacitor 6)"
  else
    bad "Node $NODE_V (need >= 18, recommend 20+)"
  fi
else
  bad "node not found"
fi

# Java
if command -v java >/dev/null 2>&1; then
  JAVA_LINE="$(java -version 2>&1 | head -1)"
  if echo "$JAVA_LINE" | grep -Eq 'version "(17|1\.17|21|1\.21)'; then
    ok "Java: $JAVA_LINE"
  else
    warn "Java found but not clearly 17/21: $JAVA_LINE (Android Gradle usually wants JDK 17)"
  fi
else
  bad "java not found (install JDK 17)"
fi

# ANDROID_HOME
if [[ -n "${ANDROID_HOME:-}" && -d "$ANDROID_HOME" ]]; then
  ok "ANDROID_HOME=$ANDROID_HOME"
elif [[ -n "${ANDROID_SDK_ROOT:-}" && -d "$ANDROID_SDK_ROOT" ]]; then
  export ANDROID_HOME="$ANDROID_SDK_ROOT"
  ok "ANDROID_SDK_ROOT=$ANDROID_SDK_ROOT (using as ANDROID_HOME)"
else
  bad "ANDROID_HOME / ANDROID_SDK_ROOT not set or missing"
fi

if [[ -n "${ANDROID_HOME:-}" ]]; then
  if [[ -x "$ANDROID_HOME/platform-tools/adb" ]] || command -v adb >/dev/null 2>&1; then
    ok "adb available"
  else
    bad "adb not found (install Android SDK platform-tools)"
  fi
  if compgen -G "$ANDROID_HOME/build-tools/*/aapt*" >/dev/null 2>&1; then
    ok "build-tools present"
  else
    warn "no build-tools under ANDROID_HOME (sdkmanager \"build-tools;34.0.0\")"
  fi
  if compgen -G "$ANDROID_HOME/platforms/android-*" >/dev/null 2>&1; then
    ok "platforms present"
  else
    warn "no platforms under ANDROID_HOME (sdkmanager \"platforms;android-34\")"
  fi
fi

if [[ -d "$ROOT/android" ]]; then
  ok "mobile_client/android/ present"
else
  warn "mobile_client/android/ missing — run: npm ci && npx cap add android"
fi

if [[ -f "$ROOT/node_modules/@capacitor/cli/package.json" ]]; then
  ok "node_modules installed"
else
  warn "node_modules missing — run: npm ci"
fi

echo
if [[ "$FAIL" -ne 0 ]]; then
  echo "Environment check FAILED. Fix items above, then re-run."
  exit 1
fi
echo "Environment check PASSED."
exit 0

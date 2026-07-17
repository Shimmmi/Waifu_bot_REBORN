#!/usr/bin/env bash
# Patch android/app/build.gradle for release signing via keystore.properties.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GRADLE="$ROOT/android/app/build.gradle"
EXAMPLE_SRC="$ROOT/android-templates/keystore.properties.example"
EXAMPLE_DST="$ROOT/android/keystore.properties.example"

if [[ ! -f "$GRADLE" ]]; then
  echo "[FAIL] $GRADLE missing — run setup_android_project.sh first"
  exit 1
fi

cp -f "$EXAMPLE_SRC" "$EXAMPLE_DST"
echo "[OK] Wrote $EXAMPLE_DST"

MARKER="waifuReleaseSigning"
if grep -q "$MARKER" "$GRADLE"; then
  echo "[OK] Release signing block already present"
  exit 0
fi

# Insert signing config before android { closing is fragile; append a documented block
# after the android { opening instead via a sibling gradle snippet included if present.
SNIPPET="$ROOT/android/app/waifu-signing.gradle"
cat > "$SNIPPET" <<'GRADLE'
// waifuReleaseSigning — loaded from app/build.gradle
def keystorePropertiesFile = rootProject.file("keystore.properties")
def keystoreProperties = new Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    signingConfigs {
        release {
            if (keystorePropertiesFile.exists()) {
                storeFile file(keystoreProperties["storeFile"])
                storePassword keystoreProperties["storePassword"]
                keyAlias keystoreProperties["keyAlias"]
                keyPassword keystoreProperties["keyPassword"]
            }
        }
    }
    buildTypes {
        release {
            if (keystorePropertiesFile.exists()) {
                signingConfig signingConfigs.release
            }
        }
    }
}
GRADLE

# Ensure apply from app/build.gradle
if ! grep -q 'waifu-signing.gradle' "$GRADLE"; then
  echo "" >> "$GRADLE"
  echo "// $MARKER" >> "$GRADLE"
  echo "apply from: 'waifu-signing.gradle'" >> "$GRADLE"
fi

# Ignore secrets
GI="$ROOT/android/.gitignore"
mkdir -p "$(dirname "$GI")"
touch "$GI"
grep -qxF 'keystore.properties' "$GI" || echo 'keystore.properties' >> "$GI"
grep -qxF '*.jks' "$GI" || echo '*.jks' >> "$GI"
grep -qxF '*.keystore' "$GI" || echo '*.keystore' >> "$GI"

echo "[OK] Release signing wiring applied."
echo "Next: copy $EXAMPLE_DST → android/keystore.properties and run ./scripts/build_release_apk.sh"

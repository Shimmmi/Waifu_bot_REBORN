#!/usr/bin/env bash
# Create/refresh Capacitor android/ project and wire StepCounter + bridge injection.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_ID="ru.shimmirpgbot.waifu.activity"
PKG_PATH="ru/shimmirpgbot/waifu/activity"

echo "== npm ci =="
npm ci

node scripts/write_capacitor_config.js
node scripts/sync-web-placeholder.js
node scripts/inject_bridge_into_www.js

if [[ ! -d android ]]; then
  echo "== npx cap add android =="
  npx cap add android
else
  echo "== android/ already present — sync only =="
fi

echo "== npx cap sync android =="
npx cap sync android

JAVA_SRC="android/app/src/main/java"
PLUGIN_DIR="$JAVA_SRC/$PKG_PATH/plugins"
mkdir -p "$PLUGIN_DIR"
cp -f native/android/WaifuStepCounterPlugin.java "$PLUGIN_DIR/WaifuStepCounterPlugin.java"
echo "[OK] Copied WaifuStepCounterPlugin.java → $PLUGIN_DIR"

MAIN="$(find "$JAVA_SRC" -name 'MainActivity.java' | head -1)"
if [[ -z "$MAIN" ]]; then
  echo "[FAIL] MainActivity.java not found under $JAVA_SRC"
  exit 1
fi

# Prefer committed sources under android/ if present; otherwise write templates.
HELPER="$JAVA_SRC/$PKG_PATH/BridgeLoader.java"
if [[ -f "$ROOT/android/app/src/main/java/$PKG_PATH/BridgeLoader.java" ]]; then
  cp -f "$ROOT/android/app/src/main/java/$PKG_PATH/BridgeLoader.java" "$HELPER"
  echo "[OK] Copied BridgeLoader.java from android tree"
else
  echo "[WARN] BridgeLoader.java missing under android/ — skip template rewrite"
fi

# Rewrite MainActivity cleanly (do NOT replace Capacitor WebViewClient)
cat > "$MAIN" <<JAVA
package ${APP_ID};

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.ValueCallback;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

import ${APP_ID}.plugins.WaifuStepCounterPlugin;

public class MainActivity extends BridgeActivity {
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private int injectAttempts = 0;
    private static final int MAX_INJECT_ATTEMPTS = 12;
    private static final long INJECT_INTERVAL_MS = 500L;

    private final Runnable injectLoop = new Runnable() {
        @Override
        public void run() {
            if (bridge == null || bridge.getWebView() == null) {
                return;
            }
            final WebView webView = bridge.getWebView();
            BridgeLoader.inject(webView);
            injectAttempts++;
            if (injectAttempts >= MAX_INJECT_ATTEMPTS) {
                return;
            }
            webView.evaluateJavascript(
                "(function(){try{return !!(window.waifuMobile&&window.waifuMobile.__nativeReady);}catch(e){return false;}})()",
                new ValueCallback<String>() {
                    @Override
                    public void onReceiveValue(String value) {
                        if ("true".equals(value)) {
                            return;
                        }
                        mainHandler.postDelayed(injectLoop, INJECT_INTERVAL_MS);
                    }
                }
            );
        }
    };

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(WaifuStepCounterPlugin.class);
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onStart() {
        super.onStart();
        scheduleBridgeInject();
    }

    @Override
    public void onResume() {
        super.onResume();
        scheduleBridgeInject();
    }

    @Override
    public void onPause() {
        mainHandler.removeCallbacks(injectLoop);
        super.onPause();
    }

    private void scheduleBridgeInject() {
        mainHandler.removeCallbacks(injectLoop);
        injectAttempts = 0;
        mainHandler.postDelayed(injectLoop, 200L);
    }
}
JAVA
echo "[OK] Wrote MainActivity.java"

MANIFEST="android/app/src/main/AndroidManifest.xml"
if [[ -f "$MANIFEST" ]]; then
  if ! grep -q 'ACTIVITY_RECOGNITION' "$MANIFEST"; then
    perl -i -0pe 's|(<manifest[^>]*>)|$1\n    <uses-permission android:name="android.permission.ACTIVITY_RECOGNITION" />\n    <uses-feature android:name="android.hardware.sensor.stepcounter" android:required="false" />|' "$MANIFEST"
    echo "[OK] Added ACTIVITY_RECOGNITION to AndroidManifest.xml"
  else
    echo "[OK] ACTIVITY_RECOGNITION already in manifest"
  fi
else
  echo "[WARN] AndroidManifest.xml not found"
fi

# gitignore build artifacts if missing
GI="$ROOT/android/.gitignore"
if [[ -d android && ! -f "$GI" ]]; then
  cat > "$GI" <<'EOF'
*.iml
.gradle
/local.properties
/.idea
.DS_Store
/build
/captures
.externalNativeBuild
.cxx
app/build
keystore.properties
*.jks
*.keystore
EOF
fi

echo
echo "[OK] Android project ready."
echo "Next: ./scripts/build_debug_apk.sh"

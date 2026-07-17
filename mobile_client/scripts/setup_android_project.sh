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

HELPER="$JAVA_SRC/$PKG_PATH/BridgeLoader.java"
cat > "$HELPER" <<'JAVA'
package ru.shimmirpgbot.waifu.activity;

import android.webkit.WebView;
import com.getcapacitor.BridgeActivity;

/**
 * Injects window.waifuMobile bootstrap into the Capacitor WebView after page load.
 * The full bridge logic is also available as android_asset www/bridge.js for bundled mode.
 */
public final class BridgeLoader {
    private BridgeLoader() {}

    public static final String BOOTSTRAP =
        "(function(){"
        + "if(window.waifuMobile)return;"
        + "var s=document.createElement('script');"
        + "s.src='https://localhost/bridge.js';"
        + "document.documentElement.appendChild(s);"
        + "})();";

    /** Fallback inline minimal stub if asset URL is unavailable under remote server.url */
    public static final String INLINE_STUB =
        "(function(g){if(g.waifuMobile)return;"
        + "var last=null,total=0,perm='prompt';"
        + "function rs(){try{return g.localStorage.getItem('waifuDesktopSession')}catch(e){return null}}"
        + "function ws(t){try{if(t)g.localStorage.setItem('waifuDesktopSession',String(t));"
        + "else g.localStorage.removeItem('waifuDesktopSession')}catch(e){}}"
        + "g.waifuMobile={getDesktopSessionToken:rs,setDesktopSessionToken:ws,"
        + "getStepSnapshot:async function(){if(g.Capacitor&&g.Capacitor.Plugins&&g.Capacitor.Plugins.WaifuStepCounter){"
        + "var snap=await g.Capacitor.Plugins.WaifuStepCounter.getSnapshot();total=Number(snap.total||0);perm=snap.permission||perm;"
        + "var d=last==null?0:Math.max(0,total-last);return{total:total,deltaSinceLastClaim:d,pendingDelta:d,permission:perm};}"
        + "return{total:0,deltaSinceLastClaim:0,pendingDelta:0,permission:'unavailable'};},"
        + "consumePendingSteps:async function(){var snap=await g.waifuMobile.getStepSnapshot();var u=Number(snap.deltaSinceLastClaim||0);"
        + "if(snap.total!=null)last=Number(snap.total);return{units:u,total:snap.total};},"
        + "requestActivityPermission:async function(){if(g.Capacitor&&g.Capacitor.Plugins&&g.Capacitor.Plugins.WaifuStepCounter){"
        + "var r=await g.Capacitor.Plugins.WaifuStepCounter.requestPermission();perm=r.permission||perm;return r;}"
        + "return{permission:'unavailable'};}};})(window);";

    public static void inject(WebView webView) {
        if (webView == null) return;
        webView.evaluateJavascript(INLINE_STUB, null);
    }
}
JAVA
echo "[OK] Wrote BridgeLoader.java"

# Rewrite MainActivity cleanly (do NOT replace Capacitor WebViewClient)
cat > "$MAIN" <<JAVA
package ${APP_ID};

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import ${APP_ID}.plugins.WaifuStepCounterPlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(WaifuStepCounterPlugin.class);
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onResume() {
        super.onResume();
        // Re-inject after remote WebApp navigations; Capacitor keeps its own WebViewClient.
        if (bridge != null && bridge.getWebView() != null) {
            bridge.getWebView().postDelayed(
                () -> BridgeLoader.inject(bridge.getWebView()),
                300
            );
        }
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

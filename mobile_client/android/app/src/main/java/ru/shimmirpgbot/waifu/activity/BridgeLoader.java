package ru.shimmirpgbot.waifu.activity;

import android.webkit.WebView;

/**
 * Injects window.waifuMobile bootstrap into the Capacitor WebView after page load.
 * The full bridge logic is also available as android_asset www/bridge.js for bundled mode.
 */
public final class BridgeLoader {
    private BridgeLoader() {}

    /** Inline stub for remote server.url pages (asset URL may be unavailable). */
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

package ru.shimmirpgbot.waifu.activity;

import android.webkit.WebView;

/**
 * Injects window.waifuMobile into the Capacitor WebView (remote server.url pages).
 * Waits for Capacitor and resolves WaifuStepCounter via Plugins or registerPlugin.
 */
public final class BridgeLoader {
    private BridgeLoader() {}

    /**
     * Full bridge body (keep in sync with mobile_client/src/bridge.js).
     * Always reassigns window.waifuMobile so a late Capacitor load upgrades a cold stub.
     */
    public static final String INLINE_STUB =
        "(function(g){"
        + "var last=null,total=0,perm='prompt',pluginRef=null;"
        + "function rs(){try{return g.localStorage.getItem('waifuDesktopSession')}catch(e){return null}}"
        + "function ws(t){try{if(t)g.localStorage.setItem('waifuDesktopSession',String(t));"
        + "else g.localStorage.removeItem('waifuDesktopSession')}catch(e){}}"
        + "function resolvePlugin(){var Cap=g.Capacitor;if(!Cap)return null;if(pluginRef)return pluginRef;"
        + "try{if(Cap.Plugins&&Cap.Plugins.WaifuStepCounter){pluginRef=Cap.Plugins.WaifuStepCounter;return pluginRef;}"
        + "if(typeof Cap.registerPlugin==='function'){pluginRef=Cap.registerPlugin('WaifuStepCounter');return pluginRef;}"
        + "}catch(e){pluginRef=null;}return null;}"
        + "function markReady(ok){var a=g.waifuMobile;if(!a)return;a.__nativeReady=!!ok;"
        + "a.__hasCapacitor=!!g.Capacitor;a.__hasPlugin=!!ok;}"
        + "var api={"
        + "__nativeReady:false,__hasCapacitor:false,__hasPlugin:false,"
        + "getDesktopSessionToken:rs,setDesktopSessionToken:ws,"
        + "getStepSnapshot:async function(){var plugin=resolvePlugin();markReady(!!plugin);"
        + "if(!plugin||typeof plugin.getSnapshot!=='function'){"
        + "return{total:total,deltaSinceLastClaim:0,pendingDelta:0,permission:'unavailable',sensor:'none'};}"
        + "var snap=await plugin.getSnapshot();total=Number(snap.total||0);perm=snap.permission||perm;"
        + "var d=last==null?0:Math.max(0,total-last);"
        + "return{total:total,deltaSinceLastClaim:d,pendingDelta:d,permission:perm,sensor:snap.sensor||null};},"
        + "consumePendingSteps:async function(){var snap=await g.waifuMobile.getStepSnapshot();"
        + "var u=Number(snap.deltaSinceLastClaim||0);if(snap.total!=null)last=Number(snap.total);"
        + "return{units:u,total:snap.total};},"
        + "requestActivityPermission:async function(){var plugin=resolvePlugin();markReady(!!plugin);"
        + "if(!plugin||typeof plugin.requestPermission!=='function'){return{permission:'unavailable'};}"
        + "var r=await plugin.requestPermission();perm=r.permission||perm;return r;}"
        + "};"
        + "g.waifuMobile=api;markReady(!!resolvePlugin());"
        + "var tries=0;var timer=g.setInterval(function(){tries++;"
        + "if(resolvePlugin()){markReady(true);g.clearInterval(timer);}"
        + "else if(tries>=20){markReady(false);g.clearInterval(timer);}"
        + "},250);"
        + "})(window);";

    public static void inject(WebView webView) {
        if (webView == null) return;
        webView.evaluateJavascript(INLINE_STUB, null);
    }
}

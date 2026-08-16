package ru.shimmirpgbot.waifu.activity;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.ValueCallback;
import android.webkit.WebView;

import com.getcapacitor.BridgeActivity;

import ru.shimmirpgbot.waifu.activity.plugins.WaifuStepCounterPlugin;

/**
 * Capacitor host. Re-injects window.waifuMobile after in-WebView navigations
 * (login → OIDC → shell) because Activity onResume often does not fire again.
 */
public class MainActivity extends BridgeActivity {
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private int injectAttempts = 0;
    private static final int MAX_INJECT_ATTEMPTS = 12;
    private static final long INJECT_INTERVAL_MS = 500L;
    private static final long URL_WATCH_INTERVAL_MS = 400L;

    private String lastSeenUrl = null;
    private boolean urlWatchActive = false;

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

    private final Runnable urlWatchLoop = new Runnable() {
        @Override
        public void run() {
            if (!urlWatchActive || bridge == null || bridge.getWebView() == null) {
                return;
            }
            String url = bridge.getWebView().getUrl();
            if (url != null && !url.equals(lastSeenUrl)) {
                lastSeenUrl = url;
                scheduleBridgeInject();
            }
            mainHandler.postDelayed(this, URL_WATCH_INTERVAL_MS);
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
        startUrlWatch();
        scheduleBridgeInject();
    }

    @Override
    public void onPause() {
        stopUrlWatch();
        mainHandler.removeCallbacks(injectLoop);
        super.onPause();
    }

    private void startUrlWatch() {
        urlWatchActive = true;
        mainHandler.removeCallbacks(urlWatchLoop);
        mainHandler.postDelayed(urlWatchLoop, URL_WATCH_INTERVAL_MS);
    }

    private void stopUrlWatch() {
        urlWatchActive = false;
        mainHandler.removeCallbacks(urlWatchLoop);
    }

    private void scheduleBridgeInject() {
        mainHandler.removeCallbacks(injectLoop);
        injectAttempts = 0;
        // First tick after a short delay so Capacitor native-bridge can attach.
        mainHandler.postDelayed(injectLoop, 200L);
    }
}

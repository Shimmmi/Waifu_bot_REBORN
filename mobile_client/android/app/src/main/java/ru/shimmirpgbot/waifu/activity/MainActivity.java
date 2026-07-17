package ru.shimmirpgbot.waifu.activity;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import ru.shimmirpgbot.waifu.activity.plugins.WaifuStepCounterPlugin;

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

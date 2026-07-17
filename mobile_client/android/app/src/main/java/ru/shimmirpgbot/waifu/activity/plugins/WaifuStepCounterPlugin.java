package ru.shimmirpgbot.waifu.activity.plugins;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

/**
 * TYPE_STEP_COUNTER based pedometer for activity combat (1 step = 1 char).
 * Copy into the Capacitor Android app module after `npx cap add android`.
 */
@CapacitorPlugin(
    name = "WaifuStepCounter",
    permissions = {
        @Permission(
            alias = "activity",
            strings = { Manifest.permission.ACTIVITY_RECOGNITION }
        )
    }
)
public class WaifuStepCounterPlugin extends Plugin implements SensorEventListener {
    private SensorManager sensorManager;
    private Sensor stepCounter;
    private float lastReading = -1f;

    @Override
    public void load() {
        Context ctx = getContext();
        sensorManager = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
        if (sensorManager != null) {
            stepCounter = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
            if (stepCounter != null) {
                sensorManager.registerListener(this, stepCounter, SensorManager.SENSOR_DELAY_NORMAL);
            }
        }
    }

    @PluginMethod
    public void getSnapshot(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("total", lastReading < 0 ? 0 : (long) lastReading);
        ret.put("permission", currentPermission());
        call.resolve(ret);
    }

    @PluginMethod
    public void requestPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < 29) {
            JSObject ret = new JSObject();
            ret.put("permission", "granted");
            call.resolve(ret);
            return;
        }
        if ("granted".equals(currentPermission())) {
            JSObject ret = new JSObject();
            ret.put("permission", "granted");
            call.resolve(ret);
            return;
        }
        requestPermissionForAlias("activity", call, "activityPermCallback");
    }

    @PermissionCallback
    private void activityPermCallback(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("permission", currentPermission());
        call.resolve(ret);
    }

    private String currentPermission() {
        if (Build.VERSION.SDK_INT < 29) return "granted";
        int st = ContextCompat.checkSelfPermission(getContext(), Manifest.permission.ACTIVITY_RECOGNITION);
        if (st == PackageManager.PERMISSION_GRANTED) return "granted";
        return "denied";
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (event.sensor.getType() == Sensor.TYPE_STEP_COUNTER) {
            lastReading = event.values[0];
        }
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) { }
}

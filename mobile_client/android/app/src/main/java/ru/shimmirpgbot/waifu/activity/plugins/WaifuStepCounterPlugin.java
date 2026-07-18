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
 * Pedometer for activity combat (1 step = 1 char).
 * Prefers TYPE_STEP_COUNTER; falls back to TYPE_STEP_DETECTOR.
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
    private Sensor stepDetector;
    private String activeSensor = "none";
    private float counterReading = -1f;
    private long detectorTotal = 0L;
    private boolean permissionAsked = false;
    private boolean permissionDenied = false;
    private boolean sensorRegistered = false;

    @Override
    public void load() {
        Context ctx = getContext();
        sensorManager = (SensorManager) ctx.getSystemService(Context.SENSOR_SERVICE);
        if (sensorManager != null) {
            stepCounter = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
            stepDetector = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_DETECTOR);
        }
        if (isPermissionGranted()) {
            startSensorListening();
        }
    }

    @PluginMethod
    public void getSnapshot(PluginCall call) {
        ensureSensorIfPermitted();
        JSObject ret = new JSObject();
        ret.put("total", currentTotal());
        ret.put("permission", currentPermission());
        ret.put("sensor", activeSensor);
        call.resolve(ret);
    }

    @PluginMethod
    public void requestPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < 29) {
            permissionAsked = true;
            permissionDenied = false;
            startSensorListening();
            JSObject ret = new JSObject();
            ret.put("permission", "granted");
            ret.put("sensor", activeSensor);
            call.resolve(ret);
            return;
        }
        if (isPermissionGranted()) {
            permissionAsked = true;
            permissionDenied = false;
            startSensorListening();
            JSObject ret = new JSObject();
            ret.put("permission", "granted");
            ret.put("sensor", activeSensor);
            call.resolve(ret);
            return;
        }
        permissionAsked = true;
        requestPermissionForAlias("activity", call, "activityPermCallback");
    }

    @PermissionCallback
    private void activityPermCallback(PluginCall call) {
        boolean granted = isPermissionGranted();
        permissionDenied = !granted;
        if (granted) {
            startSensorListening();
        } else {
            stopSensorListening();
        }
        JSObject ret = new JSObject();
        ret.put("permission", currentPermission());
        ret.put("sensor", activeSensor);
        call.resolve(ret);
    }

    private void ensureSensorIfPermitted() {
        if (isPermissionGranted() && !sensorRegistered) {
            startSensorListening();
        }
    }

    private synchronized void startSensorListening() {
        if (sensorManager == null || sensorRegistered) {
            if (sensorRegistered) return;
        }
        stopSensorListening();
        if (stepCounter != null) {
            sensorManager.registerListener(this, stepCounter, SensorManager.SENSOR_DELAY_NORMAL);
            activeSensor = "step_counter";
            sensorRegistered = true;
            return;
        }
        if (stepDetector != null) {
            sensorManager.registerListener(this, stepDetector, SensorManager.SENSOR_DELAY_NORMAL);
            activeSensor = "step_detector";
            sensorRegistered = true;
            return;
        }
        activeSensor = "none";
        sensorRegistered = false;
    }

    private synchronized void stopSensorListening() {
        if (sensorManager != null && sensorRegistered) {
            sensorManager.unregisterListener(this);
        }
        sensorRegistered = false;
        if (activeSensor.equals("step_counter") || activeSensor.equals("step_detector")) {
            // keep last known activeSensor label for diagnostics when stopped due to deny
        }
        if (!isPermissionGranted()) {
            activeSensor = "none";
        }
    }

    private long currentTotal() {
        if ("step_counter".equals(activeSensor)) {
            return counterReading < 0 ? 0L : (long) counterReading;
        }
        if ("step_detector".equals(activeSensor)) {
            return detectorTotal;
        }
        // Prefer counter reading if we ever got one before fallback
        if (counterReading >= 0) return (long) counterReading;
        return detectorTotal;
    }

    private boolean isPermissionGranted() {
        if (Build.VERSION.SDK_INT < 29) return true;
        int st = ContextCompat.checkSelfPermission(getContext(), Manifest.permission.ACTIVITY_RECOGNITION);
        return st == PackageManager.PERMISSION_GRANTED;
    }

    private String currentPermission() {
        if (Build.VERSION.SDK_INT < 29) return "granted";
        if (isPermissionGranted()) return "granted";
        if (permissionDenied && permissionAsked) return "denied";
        return "prompt";
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (event.sensor.getType() == Sensor.TYPE_STEP_COUNTER) {
            counterReading = event.values[0];
            activeSensor = "step_counter";
        } else if (event.sensor.getType() == Sensor.TYPE_STEP_DETECTOR) {
            detectorTotal += 1;
            if (!"step_counter".equals(activeSensor)) {
                activeSensor = "step_detector";
            }
        }
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) { }
}

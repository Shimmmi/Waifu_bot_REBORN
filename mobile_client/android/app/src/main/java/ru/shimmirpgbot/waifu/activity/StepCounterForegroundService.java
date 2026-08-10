package ru.shimmirpgbot.waifu.activity;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Build;
import android.os.IBinder;

import androidx.core.app.NotificationCompat;

/**
 * Keeps TYPE_STEP_COUNTER registered while the app process would otherwise sleep.
 * Persists the latest total for cold-start delta computation.
 */
public class StepCounterForegroundService extends Service implements SensorEventListener {
    public static final String ACTION_START = "ru.shimmirpgbot.waifu.activity.STEP_FGS_START";
    public static final String ACTION_STOP = "ru.shimmirpgbot.waifu.activity.STEP_FGS_STOP";
    private static final String CHANNEL_ID = "waifu_steps";
    private static final int NOTIF_ID = 7101;
    private static final String PREFS = "waifu_steps";
    private static final String KEY_TOTAL = "last_total";

    private SensorManager sensorManager;
    private Sensor stepCounter;
    private boolean registered = false;

    public static void start(Context ctx) {
        Intent i = new Intent(ctx, StepCounterForegroundService.class);
        i.setAction(ACTION_START);
        if (Build.VERSION.SDK_INT >= 26) {
            ctx.startForegroundService(i);
        } else {
            ctx.startService(i);
        }
    }

    public static void stop(Context ctx) {
        Intent i = new Intent(ctx, StepCounterForegroundService.class);
        i.setAction(ACTION_STOP);
        ctx.startService(i);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        sensorManager = (SensorManager) getSystemService(Context.SENSOR_SERVICE);
        if (sensorManager != null) {
            stepCounter = sensorManager.getDefaultSensor(Sensor.TYPE_STEP_COUNTER);
        }
        ensureChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : ACTION_START;
        if (ACTION_STOP.equals(action)) {
            stopListening();
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        Notification n = buildNotification();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH);
        } else {
            startForeground(NOTIF_ID, n);
        }
        startListening();
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        stopListening();
        super.onDestroy();
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel ch = new NotificationChannel(
            CHANNEL_ID,
            "Подсчёт шагов",
            NotificationManager.IMPORTANCE_LOW
        );
        ch.setDescription("Фоновый шагомер Waifu Activity");
        nm.createNotificationChannel(ch);
    }

    private Notification buildNotification() {
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi = PendingIntent.getActivity(
            this,
            0,
            open,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Waifu — шаги")
            .setContentText("Подсчёт шагов в фоне")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentIntent(pi)
            .setOngoing(true)
            .setSilent(true)
            .build();
    }

    private void startListening() {
        if (registered || sensorManager == null || stepCounter == null) return;
        sensorManager.registerListener(this, stepCounter, SensorManager.SENSOR_DELAY_NORMAL);
        registered = true;
    }

    private void stopListening() {
        if (sensorManager != null && registered) {
            sensorManager.unregisterListener(this);
        }
        registered = false;
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (event.sensor.getType() != Sensor.TYPE_STEP_COUNTER) return;
        long total = (long) event.values[0];
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        prefs.edit().putLong(KEY_TOTAL, total).apply();
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) { }
}

package com.dlinkddns.hil.naptimealarm;

import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;

public class PlayRingtoneReceiver extends BroadcastReceiver {
    private static final Uri alarmNotification;
    private static AudioManager audioManager;
    private static Ringtone ringtone;

    static {
        alarmNotification = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
    }

    public static Ringtone getRingtone(Context context) {
        if (ringtone == null) {
            ringtone = RingtoneManager.getRingtone(context, alarmNotification);
        }

        return ringtone;
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        if (ringtone == null) {
            ringtone = RingtoneManager.getRingtone(context, alarmNotification);
        }
        if (audioManager == null) {
            audioManager = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
        }

        // set the Do Not Disturb mode to sound alarm ringtone and all notifications
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            NotificationManager notificationManager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            notificationManager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALL);
        }

        // set the audio ringer mode to normal so alarm can be heard
        audioManager.setRingerMode(AudioManager.RINGER_MODE_NORMAL);
        ringtone.stop();
        // start playing alarm ringtone to wake the user
        ringtone.play();
    }
}
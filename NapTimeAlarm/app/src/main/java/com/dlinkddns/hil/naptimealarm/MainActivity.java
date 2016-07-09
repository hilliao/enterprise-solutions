package com.dlinkddns.hil.naptimealarm;

import android.content.Context;
import android.graphics.Color;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.support.v7.app.AppCompatActivity;
import android.support.v7.widget.Toolbar;
import android.view.Menu;
import android.view.MenuItem;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;

import java.util.Calendar;

public class MainActivity extends AppCompatActivity {
    public static final Uri notification;
    protected static AudioManager audioManager;
    protected static Runnable playRingtone;
    protected static Handler ringtoneHandler;
    protected static Ringtone ringtone;
    protected int alarmCountdownMinute;
    protected int alarmCountdownSecond;
    protected int previousAlarmMode;

    static {
        notification = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
    }

    protected Runnable getPlayRingtongRunnable() {
        if (ringtone == null) {
            ringtone = RingtoneManager.getRingtone(getApplicationContext(), notification);
        }

        if (playRingtone == null) {
            playRingtone = new Runnable() {
                @Override
                public void run() {
                    // restore the audio ringer mode to normal so alarm can be heard
                    audioManager.setRingerMode(AudioManager.RINGER_MODE_NORMAL);
                    ringtone.stop();
                    // start playing alarm to wake the user
                    ringtone.play();
                }
            };
        }

        return playRingtone;
    }

    protected Handler getRingtoneHandler() {
        if (ringtoneHandler == null) {
            ringtoneHandler = new Handler();
        }

        return ringtoneHandler;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        Toolbar toolbar = (Toolbar) findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

        final Switch alarmSwitch = (Switch) findViewById(R.id.switchAlarm);
        alarmSwitch.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton buttonView, boolean isChecked) {
                if (audioManager == null) {
                    audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
                }

                if (isChecked == true) {
                    // get the user input of minute countdown
                    EditText minuteCountdownText = (EditText) findViewById(R.id.minuteCountdown);
                    alarmCountdownMinute = Integer.parseInt(minuteCountdownText.getText().toString());
                    // get the user input of second countdown
                    EditText secondCountdownText = (EditText) findViewById(R.id.secondCountdown);
                    alarmCountdownSecond = Integer.parseInt(secondCountdownText.getText().toString());
                    Calendar timeSet = Calendar.getInstance();
                    timeSet.add(Calendar.MINUTE, alarmCountdownMinute);
                    timeSet.add(Calendar.SECOND, alarmCountdownSecond);
                    String timeStr = timeSet.get(Calendar.HOUR_OF_DAY) + ":" +
                            timeSet.get(Calendar.MINUTE) + ":" + timeSet.get(Calendar.SECOND);
                    previousAlarmMode = audioManager.getRingerMode();
                    audioManager.setRingerMode(AudioManager.RINGER_MODE_SILENT);
                    // show the time alarm will sound
                    alarmSwitch.setText(getResources().getString(R.string.alarmSetAt) + " " + timeStr);
                    alarmSwitch.setTextColor(Color.RED);
                    getRingtoneHandler().postDelayed(getPlayRingtongRunnable(),
                            alarmCountdownMinute * 60 * 1000 + alarmCountdownSecond * 1000);
                } else {
                    getRingtoneHandler().removeCallbacks(getPlayRingtongRunnable());
                    audioManager.setRingerMode(previousAlarmMode);
                    alarmSwitch.setTextColor(Color.GRAY);
                    alarmSwitch.setText(alarmSwitch.getTextOff());
                    ringtone.stop();
                }
            }
        });
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        // Inflate the menu; this adds items to the action bar if it is present.
        getMenuInflater().inflate(R.menu.menu_main, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        // Handle action bar item clicks here. The action bar will
        // automatically handle clicks on the Home/Up button, so long
        // as you specify a parent activity in AndroidManifest.xml.
        int id = item.getItemId();

        //noinspection SimplifiableIfStatement
        if (id == R.id.action_settings) {
            if (ringtone != null) {
                ringtone.stop();
            }
            return true;
        }

        return super.onOptionsItemSelected(item);
    }
}

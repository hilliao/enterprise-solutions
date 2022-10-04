package com.dlinkddns.hil.naptimealarm;

import android.app.AlarmManager;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.ProgressDialog;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.media.AudioManager;
import android.media.Ringtone;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import android.util.Log;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.gms.auth.api.Auth;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.auth.api.signin.GoogleSignInResult;
import com.google.android.gms.common.api.GoogleApiClient;
import com.google.android.gms.common.api.Status;
import com.google.android.gms.tasks.Task;
import com.google.firebase.auth.AuthCredential;
import com.google.firebase.auth.AuthResult;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.auth.GoogleAuthProvider;
import com.google.firebase.database.DataSnapshot;
import com.google.firebase.database.DatabaseError;
import com.google.firebase.database.DatabaseReference;
import com.google.firebase.database.FirebaseDatabase;
import com.google.firebase.database.ValueEventListener;

import java.text.SimpleDateFormat;
import java.util.Calendar;

public class MainActivity extends AppCompatActivity {
    private static final int RC_SIGN_IN = 9001;
    private static final String GoogleFirebase = "GoogleActivity";
    public static final int UNASSIGNED = -1;
    private static AudioManager audioManager;
    private static AlarmManager alarmManager;
    private static DatabaseReference database;

    private GoogleApiClient googleAuthApiClient;
    private FirebaseAuth firebaseAuth;
    private ProgressDialog progressDialog;
    private FirebaseAuth.AuthStateListener authListener;
    private String firebaseUid;
    private PendingIntent playRingtoneIntent;
    private Switch alarmSwitch;
    private BroadcastReceiver screenOnOffReceiver;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        Toolbar toolbar = findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

        // for SDK >= 23, android.permission.ACCESS_NOTIFICATION_POLICY -> request user's permission to Do Not Disturb access
        NotificationManager notificationManager =
                (NotificationManager) getApplicationContext().getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                && !notificationManager.isNotificationPolicyAccessGranted()) {
            Intent intent = new Intent(android.provider.Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS);
            startActivity(intent);
        }

        // register UI component's listeners
        alarmSwitch = findViewById(R.id.switchAlarm);
        alarmSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            // app crash if not have Do Not Disturb access: java.lang.SecurityException: Not allowed to change Do Not Disturb state
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                // if user has not granted app access to do not disturb, show the UI for user to grant permissions
                if (!notificationManager.isNotificationPolicyAccessGranted()) {
                    alarmSwitch.setChecked(false);
                    Intent intent = new Intent(android.provider.Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS);
                    startActivity(intent);
                } else {
                    // switch alarm timer on or off; on activates Do Not Disturb
                    alarmSwitchLogic(isChecked, alarmSwitch);
                }
            } else {
                alarmSwitchLogic(isChecked, alarmSwitch);
            }
        });

        // support Google sign-in for Firebase authentication
        GoogleSignInOptions gso = new GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                .requestIdToken(getString(R.string.default_web_client_id))
                .requestEmail()
                .build();
        googleAuthApiClient = new GoogleApiClient.Builder(this)
                .enableAutoManage(this, connectionResult -> {
                    // An unresolvable error has occurred; Google APIs (including Sign-In) not available.
                    Log.d(GoogleFirebase, "onConnectionFailed:" + connectionResult);
                    Toast.makeText(MainActivity.this, R.string.Google_signin_error, Toast.LENGTH_SHORT).show();
                })
                .addApi(Auth.GOOGLE_SIGN_IN_API, gso)
                .build();

        // register Firebase authentication change event
        firebaseAuth = FirebaseAuth.getInstance();
        authListener = (FirebaseAuth firebaseAuth) -> {
            FirebaseUser user = firebaseAuth.getCurrentUser();
            if (user != null) {
                // User is signed in
                Log.d(GoogleFirebase, "onAuthStateChanged:signed_in:" + user.getUid());
                MainActivity.this.firebaseUid = user.getUid();
            } else {
                // User is signed out
                Log.d(GoogleFirebase, "onAuthStateChanged:signed_out");
                MainActivity.this.firebaseUid = null;
            }
            updateUI(user);
        };

        // sign in and out button
        findViewById(R.id.sign_in_button).setOnClickListener(
                (View v) -> {
                    Intent signInIntent = Auth.GoogleSignInApi.getSignInIntent(googleAuthApiClient);
                    startActivityForResult(signInIntent, RC_SIGN_IN);
                }
        );
        findViewById(R.id.sign_out_button).setOnClickListener(
                (View v) -> MainActivity.this.signOut()
        );

        // default Firebase database client for this app
        database = FirebaseDatabase.getInstance().getReference().child(getString(R.string.app_name));

        // stop ringtone at screen on off event
        if (screenOnOffReceiver == null) {
            final IntentFilter screenOnOffFilter = new IntentFilter();
            screenOnOffFilter.addAction(Intent.ACTION_SCREEN_ON);
            screenOnOffFilter.addAction(Intent.ACTION_SCREEN_OFF);

            screenOnOffReceiver = new BroadcastReceiver() {
                @Override
                public void onReceive(Context context, Intent intent) {
                    String strAction = intent.getAction();

                    if (strAction.equals(Intent.ACTION_SCREEN_OFF) || strAction.equals(Intent.ACTION_SCREEN_ON)) {
                        Ringtone ringtone = PlayRingtoneReceiver.getRingtone(MainActivity.this);
                        if (ringtone.isPlaying()) {
                            ringtone.stop();
                        }
                    }
                }
            };

            registerReceiver(screenOnOffReceiver, screenOnOffFilter);
        }

        // adjust default focus
        findViewById(R.id.minuteCountdown).requestFocus();
    }

    @Override
    protected void onStart() {
        super.onStart();
        firebaseAuth.addAuthStateListener(authListener);

        if (audioManager == null) {
            audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        }
        if (alarmManager == null) {
            alarmManager = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
        }

        Intent intent = new Intent(this, PlayRingtoneReceiver.class);
        playRingtoneIntent = PendingIntent.getBroadcast(this, 0, intent, PendingIntent.FLAG_MUTABLE);
    }

    @Override
    protected void onResume() {
        super.onResume();

        // check if user has granted Do Not Disturb access
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            TextView DnDWarning = findViewById(R.id.DnDAccessWarning);
            NotificationManager notificationManager =
                    (NotificationManager) getApplicationContext().getSystemService(Context.NOTIFICATION_SERVICE);
            if (!notificationManager.isNotificationPolicyAccessGranted()) {
                DnDWarning.setVisibility(View.VISIBLE);
            } else {
                DnDWarning.setVisibility(View.INVISIBLE);
            }
        }
    }

    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        // add SHA1 fingerprint to Firebase project settings: https://developers.google.com/drive/android/auth
        // Result returned from launching the Intent from GoogleSignInApi.getSignInIntent(...);
        if (requestCode == RC_SIGN_IN) {
            GoogleSignInResult result = Auth.GoogleSignInApi.getSignInResultFromIntent(data);
            if (result.isSuccess()) {
                // Google Sign In was successful, authenticate with Firebase
                GoogleSignInAccount account = result.getSignInAccount();
                firebaseAuthWithGoogle(account);
            } else {
                // verify Firebase project settings has the release and debug SHA1 fingerprint: https://developers.google.com/drive/android/auth
                // re-add SHA1 fingerprint and retry sign-in
                // Google Sign In failed, update UI appropriately
                updateUI(null);
            }
        }
    }

    private void firebaseAuthWithGoogle(GoogleSignInAccount acct) {
        Log.d(GoogleFirebase, "firebaseAuthWithGoogle:" + acct.getId());
        showProgressDialog();
        AuthCredential credential = GoogleAuthProvider.getCredential(acct.getIdToken(), null);

        firebaseAuth.signInWithCredential(credential).addOnCompleteListener(this,
                (Task<AuthResult> task) -> {
                    Log.d(GoogleFirebase, "signInWithCredential:onComplete:" + task.isSuccessful());

                    // If sign in fails, display a message to the user. If sign in succeeds
                    // the auth state listener will be notified and logic to handle the
                    // signed in user can be handled in the listener.
                    if (!task.isSuccessful()) {
                        Log.w(GoogleFirebase, "signInWithCredential", task.getException());
                        Toast.makeText(MainActivity.this, "Authentication failed.",
                                Toast.LENGTH_SHORT).show();
                    }
                    hideProgressDialog();
                });
    }

    private void updateUI(FirebaseUser user) {
        TextView googleEmail = findViewById(R.id.textViewGoogleUser);
        TextView firebaseUid = findViewById(R.id.textViewFirebaseUser);

        hideProgressDialog();
        if (user != null) {
            googleEmail.setText(getString(R.string.google_status_fmt, user.getEmail()));
            firebaseUid.setText(getString(R.string.firebase_status_fmt, user.getUid()));

            findViewById(R.id.sign_in_button).setVisibility(View.GONE);
            findViewById(R.id.sign_out_button).setVisibility(View.VISIBLE);

            database.child(user.getUid()).addListenerForSingleValueEvent(new ValueEventListener() {
                @Override
                public void onDataChange(DataSnapshot dataSnapshot) {
                    // get user alarm time interval
                    TimeInterval timeInterval = dataSnapshot.getValue(TimeInterval.class);
                    if (timeInterval != null) {
                        ((EditText) findViewById(R.id.minuteCountdown)).setText(String.valueOf(timeInterval.minutes));
                        ((EditText) findViewById(R.id.secondCountdown)).setText(String.valueOf(timeInterval.seconds));
                        ((EditText) findViewById(R.id.hourCountdown)).setText(String.valueOf(timeInterval.hours));
                    }
                }

                @Override
                public void onCancelled(DatabaseError databaseError) {
                    Log.e(GoogleFirebase, "Firebase database get value failed", databaseError.toException());
                }
            });
        } else {
            googleEmail.setText(R.string.Google_signed_out);
            firebaseUid.setText(R.string.firebase_signed_out);

            findViewById(R.id.sign_in_button).setVisibility(View.VISIBLE);
            findViewById(R.id.sign_out_button).setVisibility(View.GONE);
        }
    }

    private void alarmSwitchLogic(boolean isActivated, Switch alarmSwitch) {
        int alarmCountdownMinutes = UNASSIGNED;
        int alarmCountdownSeconds = UNASSIGNED;
        int alarmCountdownHours = UNASSIGNED;

        if (!alarmSwitch.isPressed()) {
            return;
        }

        if (isActivated) {
            // get the user input of minute countdown
            EditText minuteCountdownText = findViewById(R.id.minuteCountdown);
            String strMinutes = minuteCountdownText.getText().toString();
            boolean timeInputError = false;

            if (strMinutes.isEmpty()) {
                alarmCountdownMinutes = 0;
            } else {
                try {
                    alarmCountdownMinutes = Integer.parseInt(strMinutes);
                } catch (NumberFormatException ex) {
                    timeInputError = true;
                }
            }

            // get the user input of second countdown
            EditText secondCountdownText = findViewById(R.id.secondCountdown);
            String strSeconds = secondCountdownText.getText().toString();

            if (strSeconds.isEmpty()) {
                alarmCountdownSeconds = 0;
            } else {
                try {
                    alarmCountdownSeconds = Integer.parseInt(strSeconds);
                } catch (NumberFormatException ex) {
                    timeInputError = true;
                }
            }

            // get the user input of hour countdown
            EditText hourCountdownText = findViewById(R.id.hourCountdown);
            String strHours = hourCountdownText.getText().toString();

            if (strHours.isEmpty()) {
                alarmCountdownHours = 0;
            } else {
                try {
                    alarmCountdownHours = Integer.parseInt(strHours);
                } catch (NumberFormatException ex) {
                    timeInputError = true;
                }
            }

            if (alarmCountdownSeconds < 0 || alarmCountdownMinutes < 0 || alarmCountdownHours < 0 || timeInputError) {
                alarmSwitch.setChecked(false);
                Toast.makeText(MainActivity.this, R.string.time_input_error, Toast.LENGTH_SHORT).show();
                return;
            }

            // calculate the time to fire the alarm
            Calendar alarmFireAt = Calendar.getInstance();
            alarmFireAt.add(Calendar.HOUR_OF_DAY, alarmCountdownHours);
            alarmFireAt.add(Calendar.MINUTE, alarmCountdownMinutes);
            alarmFireAt.add(Calendar.SECOND, alarmCountdownSeconds);

            // requires android.permission.ACCESS_NOTIFICATION_POLICY to silence everything
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                NotificationManager notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                notificationManager.setInterruptionFilter(NotificationManager.INTERRUPTION_FILTER_ALARMS);
            } else {
                audioManager.setRingerMode(AudioManager.RINGER_MODE_SILENT);
            }

            // show the time alarm will fire
            SimpleDateFormat dateFormatter = new SimpleDateFormat("MM/dd HH:mm:ss");
            alarmSwitch.setText(String.format(getResources().getString(R.string.alarm_set_at),
                    dateFormatter.format(alarmFireAt.getTime())));
            alarmSwitch.setTextColor(Color.RED);

            // schedule the alarm; set up the alarm firing event
            AlarmManager.AlarmClockInfo alarmClockInfo = new AlarmManager.AlarmClockInfo(
                    alarmFireAt.getTimeInMillis(), playRingtoneIntent);
            alarmManager.setAlarmClock(alarmClockInfo, playRingtoneIntent);

            // persist the alarm intervals
            if (this.firebaseUid != null) {
                DatabaseReference dbClient = database.child(this.firebaseUid);
                TimeInterval timeInterval = new TimeInterval(alarmCountdownHours, alarmCountdownMinutes, alarmCountdownSeconds);
                dbClient.setValue(timeInterval);
            }

            // change intro text to show how to stop ringtone
            TextView introText = findViewById(R.id.introText);
            introText.setText(R.string.intro_text_alarm_on);
            introText.setTextColor(Color.BLUE);
        } else {
            // cancel future alarm scheduled
            alarmManager.cancel(playRingtoneIntent);

            alarmSwitch.setTextColor(Color.GRAY);
            alarmSwitch.setText(alarmSwitch.getTextOff());
            PlayRingtoneReceiver.getRingtone(this).stop();
            TextView introText = findViewById(R.id.introText);
            introText.setText(R.string.intro_text);
            introText.setTextColor(Color.BLACK);
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        // Inflate the menu; this adds items to the action bar if it is present.
        getMenuInflater().inflate(R.menu.menu_main, menu);
        return true;
    }

    // Handle action bar item clicks here
    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == R.id.viewGitSource) {
            Uri uri = Uri.parse(getString(R.string.git));
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
            return true;
        }

        return super.onOptionsItemSelected(item);
    }

    @Override
    protected void onPause() {
        super.onPause();

        Ringtone ringtone = PlayRingtoneReceiver.getRingtone(MainActivity.this);
        if (ringtone.isPlaying()) {
            ringtone.stop();
        }
    }

    private void showProgressDialog() {
        if (progressDialog == null) {
            progressDialog = new ProgressDialog(this);
            progressDialog.setMessage(getString(R.string.loading));
            progressDialog.setIndeterminate(true);
        }

        progressDialog.show();
    }

    private void hideProgressDialog() {
        if (progressDialog != null && progressDialog.isShowing()) {
            progressDialog.hide();
        }
    }

    private void signOut() {
        // Firebase sign out
        firebaseAuth.signOut();
        // Google sign out
        Auth.GoogleSignInApi.signOut(googleAuthApiClient).setResultCallback(
                (Status status) -> updateUI(null));
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();

        if (isFinishing()) {
            // cancel future alarm scheduled
            alarmManager.cancel(playRingtoneIntent);
            PlayRingtoneReceiver.getRingtone(this).stop();

            unregisterReceiver(this.screenOnOffReceiver);
        }
    }
}
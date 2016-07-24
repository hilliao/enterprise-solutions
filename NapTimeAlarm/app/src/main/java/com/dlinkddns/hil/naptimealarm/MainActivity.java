package com.dlinkddns.hil.naptimealarm;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.app.ProgressDialog;
import android.content.Context;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Bundle;
import android.support.annotation.NonNull;
import android.support.v7.app.AppCompatActivity;
import android.support.v7.widget.Toolbar;
import android.util.Log;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import com.google.android.gms.appindexing.Action;
import com.google.android.gms.appindexing.AppIndex;
import com.google.android.gms.auth.api.Auth;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.auth.api.signin.GoogleSignInResult;
import com.google.android.gms.common.ConnectionResult;
import com.google.android.gms.common.api.GoogleApiClient;
import com.google.android.gms.common.api.PendingResult;
import com.google.android.gms.common.api.ResultCallback;
import com.google.android.gms.common.api.Status;
import com.google.android.gms.tasks.OnCompleteListener;
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
    private static AudioManager audioManager;
    private static AlarmManager alarmManager;
    private static DatabaseReference database;

    private int previousAlarmMode;
    private GoogleApiClient googleAuthApiClient;
    private GoogleApiClient googleIndexApiClient;
    private FirebaseAuth firebaseAuth;
    private ProgressDialog progressDialog;
    private FirebaseAuth.AuthStateListener authListener;
    private String firebaseUid;
    private PendingIntent playRingtoneIntent;
    private Switch alarmSwitch;// format per https://developer.android.com/training/app-indexing/enabling-app-indexing.html
    private Action viewAppAction;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        Toolbar toolbar = (Toolbar) findViewById(R.id.toolbar);
        setSupportActionBar(toolbar);

        // Firebase app indexing https://firebase.google.com/docs/app-indexing/android/app
        // Deep Links for App Content https://developer.android.com/training/app-indexing/deep-linking.html
        Intent urlIntent = getIntent();
        String url = urlIntent.getDataString();
        Log.i(GoogleFirebase, String.format("MainActivity started from deep-linking at %s", url));

        // register UI component's listeners
        alarmSwitch = (Switch) findViewById(R.id.switchAlarm);
        alarmSwitch.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton buttonView, boolean isChecked) {
                alarmSwitchLogic(isChecked, alarmSwitch);
            }
        });

        // support Google sign-in for Firebase authentication
        GoogleSignInOptions gso = new GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                .requestIdToken(getString(R.string.default_web_client_id))
                .requestEmail()
                .build();
        googleIndexApiClient = new GoogleApiClient.Builder(this).addApi(AppIndex.API).build();
        googleAuthApiClient = new GoogleApiClient.Builder(this)
                .enableAutoManage(this, new GoogleApiClient.OnConnectionFailedListener() {
                    @Override
                    public void onConnectionFailed(@NonNull ConnectionResult connectionResult) {
                        // An unresolvable error has occurred; Google APIs (including Sign-In) not available.
                        Log.d(GoogleFirebase, "onConnectionFailed:" + connectionResult);
                        Toast.makeText(MainActivity.this, "Google Play Services sign in error.", Toast.LENGTH_SHORT).show();
                    }
                })
                .addApi(Auth.GOOGLE_SIGN_IN_API, gso)
                .build();

        // register Firebase authentication change event
        firebaseAuth = FirebaseAuth.getInstance();
        authListener = new FirebaseAuth.AuthStateListener() {
            @Override
            public void onAuthStateChanged(@NonNull FirebaseAuth firebaseAuth) {
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
            }
        };

        // sign in and out button
        findViewById(R.id.sign_in_button).setOnClickListener(
                new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        Intent signInIntent = Auth.GoogleSignInApi.getSignInIntent(googleAuthApiClient);
                        startActivityForResult(signInIntent, RC_SIGN_IN);
                    }
                }
        );
        findViewById(R.id.sign_out_button).setOnClickListener(
                new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        MainActivity.this.signOut();
                    }
                }
        );

        // default Firebase database reference for this app
        database = FirebaseDatabase.getInstance().getReference().child(getString(R.string.app_name));

        /*
         * Test launching the app from deep-link by adb
         * PS C:\Users\Hil\Documents> adb shell am start -a android.intent.action.VIEW  -d "http://hil.dlinkddns.com/naptimealarm" com.dlinkddns.hil.naptimealarm
         * */
        viewAppAction = Action.newAction(
                Action.TYPE_VIEW,
                "Nap Time Alarm",
                Uri.parse(getString(R.string.uri)),
                Uri.parse(getString(R.string.appUri))
        );
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
        playRingtoneIntent = PendingIntent.getBroadcast(this, 0, intent, 0);

        googleIndexApiClient.connect();
        PendingResult<Status> result = AppIndex.AppIndexApi.start(googleIndexApiClient, viewAppAction);
        googleIndexApiClient.disconnect();
    }

    @Override
    protected void onStop() {
        StopAppIndexing();
        super.onStop();
    }

    private void StopAppIndexing() {
        AppIndex.AppIndexApi.end(googleIndexApiClient, viewAppAction);
        googleIndexApiClient.disconnect();
    }

    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        // Result returned from launching the Intent from GoogleSignInApi.getSignInIntent(...);
        if (requestCode == RC_SIGN_IN) {
            GoogleSignInResult result = Auth.GoogleSignInApi.getSignInResultFromIntent(data);
            if (result.isSuccess()) {
                // Google Sign In was successful, authenticate with Firebase
                GoogleSignInAccount account = result.getSignInAccount();
                firebaseAuthWithGoogle(account);
            } else {
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
                new OnCompleteListener<AuthResult>() {
                    @Override
                    public void onComplete(@NonNull Task<AuthResult> task) {
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
                    }
                });
    }

    private void updateUI(FirebaseUser user) {
        TextView googleEmail = (TextView) findViewById(R.id.textViewGoogleUser);
        TextView firebaseUid = (TextView) findViewById(R.id.textViewFirebaseUser);

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

    private void alarmSwitchLogic(boolean isChecked, Switch alarmSwitch) {
        int alarmCountdownMinutes;
        int alarmCountdownSeconds;
        int alarmCountdownHours;

        if (!alarmSwitch.isPressed()) {
            return;
        }

        if (isChecked == true) {
            // get the user input of minute countdown
            EditText minuteCountdownText = (EditText) findViewById(R.id.minuteCountdown);
            String strMinutes = minuteCountdownText.getText().toString();

            if (strMinutes.isEmpty()) {
                alarmCountdownMinutes = 0;
            } else {
                try {
                    alarmCountdownMinutes = Integer.parseInt(strMinutes);
                } catch (NumberFormatException ex) {
                    alarmSwitch.setChecked(false);
                    return;
                }
            }

            // get the user input of second countdown
            EditText secondCountdownText = (EditText) findViewById(R.id.secondCountdown);
            String strSeconds = secondCountdownText.getText().toString();

            if (strSeconds.isEmpty()) {
                alarmCountdownSeconds = 0;
            } else {
                try {
                    alarmCountdownSeconds = Integer.parseInt(strSeconds);
                } catch (NumberFormatException ex) {
                    alarmSwitch.setChecked(false);
                    return;
                }
            }

            // get the user input of hour countdown
            EditText hourCountdownText = (EditText) findViewById(R.id.hourCountdown);
            String strHours = hourCountdownText.getText().toString();

            if (strHours.isEmpty()) {
                alarmCountdownHours = 0;
            } else {
                try {
                    alarmCountdownHours = Integer.parseInt(strHours);
                } catch (NumberFormatException ex) {
                    alarmSwitch.setChecked(false);
                    return;
                }
            }

            // calculate the time to fire the alarm
            Calendar alarmFireAt = Calendar.getInstance();
            alarmFireAt.add(Calendar.HOUR_OF_DAY, alarmCountdownHours);
            alarmFireAt.add(Calendar.MINUTE, alarmCountdownMinutes);
            alarmFireAt.add(Calendar.SECOND, alarmCountdownSeconds);

            // will restore the previous alarm mode when the switch if off
            previousAlarmMode = audioManager.getRingerMode();
            audioManager.setRingerMode(AudioManager.RINGER_MODE_SILENT);

            // show the time alarm will fire
            SimpleDateFormat dateFormatter = new SimpleDateFormat("MM/dd HH:mm:ss");
            alarmSwitch.setText(String.format(getResources().getString(R.string.alarmSetAt),
                    dateFormatter.format(alarmFireAt.getTime())));
            alarmSwitch.setTextColor(Color.RED);

            // schedule the alarm; set up the alarm firing event
            AlarmManager.AlarmClockInfo alarmClockInfo = new AlarmManager.AlarmClockInfo(
                    alarmFireAt.getTimeInMillis(), playRingtoneIntent);
            alarmManager.setAlarmClock(alarmClockInfo, playRingtoneIntent);

            // persist the alarm intervals
            if (this.firebaseUid != null) {
                DatabaseReference uidRef = database.child(this.firebaseUid);
                TimeInterval timeInterval = new TimeInterval(alarmCountdownHours, alarmCountdownMinutes, alarmCountdownSeconds);
                uidRef.setValue(timeInterval);
            }
        } else {
            // cancel future alarm scheduled
            alarmManager.cancel(playRingtoneIntent);
            audioManager.setRingerMode(previousAlarmMode);
            alarmSwitch.setTextColor(Color.GRAY);
            alarmSwitch.setText(alarmSwitch.getTextOff());
            PlayRingtoneReceiver.getRingtone(this).stop();
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        // Inflate the menu; this adds items to the action bar if it is present.
        getMenuInflater().inflate(R.menu.menu_main, menu);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        // Handle action bar item clicks here.
        int id = item.getItemId();

        // noinspection SimplifiableIfStatement
        if (id == R.id.action_stop_ringtone) {
            PlayRingtoneReceiver.getRingtone(this).stop();
            return true;
        }

        return super.onOptionsItemSelected(item);
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
                new ResultCallback<Status>() {
                    @Override
                    public void onResult(@NonNull Status status) {
                        updateUI(null);
                    }
                });
    }

    @Override
    protected void onSaveInstanceState(Bundle savedInstanceState) {
        super.onSaveInstanceState(savedInstanceState);
        savedInstanceState.putInt("previousAlarmMode", previousAlarmMode);
        savedInstanceState.putCharSequence("alarmSwitchText", alarmSwitch.getText());
        savedInstanceState.putParcelable("alarmSwitchColor", alarmSwitch.getTextColors());
    }

    @Override
    protected void onRestoreInstanceState(Bundle savedInstanceState) {
        super.onRestoreInstanceState(savedInstanceState);
        previousAlarmMode = savedInstanceState.getInt("previousAlarmMode");
        alarmSwitch.setText(savedInstanceState.getCharSequence("alarmSwitchText"));
        alarmSwitch.setTextColor((ColorStateList) savedInstanceState.getParcelable("alarmSwitchColor"));
    }
}

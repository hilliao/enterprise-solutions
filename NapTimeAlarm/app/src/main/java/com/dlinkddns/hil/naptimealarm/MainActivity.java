package com.dlinkddns.hil.naptimealarm;

import android.app.ProgressDialog;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.media.AudioManager;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
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

import com.google.android.gms.auth.api.Auth;
import com.google.android.gms.auth.api.signin.GoogleSignInAccount;
import com.google.android.gms.auth.api.signin.GoogleSignInOptions;
import com.google.android.gms.auth.api.signin.GoogleSignInResult;
import com.google.android.gms.common.ConnectionResult;
import com.google.android.gms.common.api.GoogleApiClient;
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

import java.util.Calendar;

public class MainActivity extends AppCompatActivity {
    private static final Uri notification;
    private static final int RC_SIGN_IN = 9001;
    private static final String TAG = "GoogleActivity";
    private static AudioManager audioManager;
    private static Runnable playRingtone;
    private static Handler ringtoneHandler;
    private static Ringtone ringtone;
    private static DatabaseReference database;

    static {
        notification = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
    }

    private int alarmCountdownMinute;
    private int alarmCountdownSecond;
    private int previousAlarmMode;
    private GoogleApiClient googleApiClient;
    private FirebaseAuth firebaseAuth;
    private ProgressDialog progressDialog;
    private FirebaseAuth.AuthStateListener authListener;
    private String firebaseUid;

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
        if (audioManager == null) {
            audioManager = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        }

        final Switch alarmSwitch = (Switch) findViewById(R.id.switchAlarm);
        alarmSwitch.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton buttonView, boolean isChecked) {
                alarmSwitchLogic(isChecked, alarmSwitch);
            }
        });

        GoogleSignInOptions gso = new GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
                .requestIdToken(getString(R.string.default_web_client_id))
                .requestEmail()
                .build();
        googleApiClient = new GoogleApiClient.Builder(this)
                .enableAutoManage(this /* FragmentActivity */, new GoogleApiClient.OnConnectionFailedListener() {
                    @Override
                    public void onConnectionFailed(@NonNull ConnectionResult connectionResult) {
                        // An unresolvable error has occurred and Google APIs (including Sign-In) will not
                        // be available.
                        Log.d(TAG, "onConnectionFailed:" + connectionResult);
                        Toast.makeText(MainActivity.this, "Google Play Services sign in error.", Toast.LENGTH_SHORT).show();
                    }
                })
                .addApi(Auth.GOOGLE_SIGN_IN_API, gso)
                .build();
        firebaseAuth = FirebaseAuth.getInstance();
        authListener = new FirebaseAuth.AuthStateListener() {
            @Override
            public void onAuthStateChanged(@NonNull FirebaseAuth firebaseAuth) {
                FirebaseUser user = firebaseAuth.getCurrentUser();
                if (user != null) {
                    // User is signed in
                    Log.d(TAG, "onAuthStateChanged:signed_in:" + user.getUid());
                    MainActivity.this.firebaseUid = user.getUid();
                } else {
                    // User is signed out
                    Log.d(TAG, "onAuthStateChanged:signed_out");
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
                        Intent signInIntent = Auth.GoogleSignInApi.getSignInIntent(googleApiClient);
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
        // default database reference for this app
        database = FirebaseDatabase.getInstance().getReference().child(getString(R.string.app_name));
    }

    @Override
    public void onStart() {
        super.onStart();
        firebaseAuth.addAuthStateListener(authListener);
        // will restore the previous alarm mode when the switch if off
        previousAlarmMode = audioManager.getRingerMode();
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
                // [START_EXCLUDE]
                updateUI(null);
                // [END_EXCLUDE]
            }
        }
    }

    private void firebaseAuthWithGoogle(GoogleSignInAccount acct) {
        Log.d(TAG, "firebaseAuthWithGoogle:" + acct.getId());
        showProgressDialog();

        AuthCredential credential = GoogleAuthProvider.getCredential(acct.getIdToken(), null);
        firebaseAuth.signInWithCredential(credential)
                .addOnCompleteListener(this, new OnCompleteListener<AuthResult>() {
                    @Override
                    public void onComplete(@NonNull Task<AuthResult> task) {
                        Log.d(TAG, "signInWithCredential:onComplete:" + task.isSuccessful());

                        // If sign in fails, display a message to the user. If sign in succeeds
                        // the auth state listener will be notified and logic to handle the
                        // signed in user can be handled in the listener.
                        if (!task.isSuccessful()) {
                            Log.w(TAG, "signInWithCredential", task.getException());
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
                    }
                }

                @Override
                public void onCancelled(DatabaseError databaseError) {

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
        if (isChecked == true) {
            // get the user input of minute countdown
            EditText minuteCountdownText = (EditText) findViewById(R.id.minuteCountdown);
            try {
                alarmCountdownMinute = Integer.parseInt(minuteCountdownText.getText().toString());
            } catch (NumberFormatException ex) {
                alarmSwitch.setChecked(false);
                return;
            }
            // get the user input of second countdown
            EditText secondCountdownText = (EditText) findViewById(R.id.secondCountdown);
            try {
                alarmCountdownSecond = Integer.parseInt(secondCountdownText.getText().toString());
            } catch (NumberFormatException ex) {
                alarmSwitch.setChecked(false);
                return;
            }
            // add time to set when the alarm will sound
            Calendar timeSet = Calendar.getInstance();
            timeSet.add(Calendar.MINUTE, alarmCountdownMinute);
            timeSet.add(Calendar.SECOND, alarmCountdownSecond);
            String timeStr = timeSet.get(Calendar.HOUR_OF_DAY) + ":" +
                    timeSet.get(Calendar.MINUTE) + ":" + timeSet.get(Calendar.SECOND);
            audioManager.setRingerMode(AudioManager.RINGER_MODE_SILENT);
            // show the time alarm will sound
            alarmSwitch.setText(getResources().getString(R.string.alarmSetAt) + " " + timeStr);
            alarmSwitch.setTextColor(Color.RED);
            // schedule the alarm
            getRingtoneHandler().postDelayed(getPlayRingtongRunnable(),
                    alarmCountdownMinute * 60 * 1000 + alarmCountdownSecond * 1000);
            // persist the alarm intervals
            if (this.firebaseUid != null) {
                DatabaseReference uidRef = database.child(this.firebaseUid);
                uidRef.push().getKey();
                TimeInterval timeInterval = new TimeInterval(0, alarmCountdownMinute, alarmCountdownSecond);
                uidRef.setValue(timeInterval);
            }
        } else {
            // cancel future alarm sounding runnable scheduled
            getRingtoneHandler().removeCallbacks(getPlayRingtongRunnable());
            audioManager.setRingerMode(previousAlarmMode);
            alarmSwitch.setTextColor(Color.GRAY);
            alarmSwitch.setText(alarmSwitch.getTextOff());
            ringtone.stop();
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

    public void showProgressDialog() {
        if (progressDialog == null) {
            progressDialog = new ProgressDialog(this);
            progressDialog.setMessage(getString(R.string.loading));
            progressDialog.setIndeterminate(true);
        }

        progressDialog.show();
    }

    public void hideProgressDialog() {
        if (progressDialog != null && progressDialog.isShowing()) {
            progressDialog.hide();
        }
    }

    private void signOut() {
        // Firebase sign out
        firebaseAuth.signOut();

        // Google sign out
        Auth.GoogleSignInApi.signOut(googleApiClient).setResultCallback(
                new ResultCallback<Status>() {
                    @Override
                    public void onResult(@NonNull Status status) {
                        updateUI(null);
                    }
                });
    }
}

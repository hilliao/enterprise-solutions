/**
 * Sample modified from https://github.com/GoogleCloudPlatform/java-docs-samples/tree/master/firestore
 * set GOOGLE_APPLICATION_CREDENTIALS to the service account with Cloud Datastore User role
 */
package com.google.firebase.quickstart;

import com.google.api.core.ApiFuture;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import com.google.cloud.firestore.WriteResult;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.database.*;
import com.google.firebase.quickstart.model.Post;
import com.google.firebase.quickstart.model.User;
import org.knowm.sundial.SundialJobScheduler;

import java.io.FileInputStream;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

//import com.google.firebase.quickstart.email.MyEmailer;

/**
 * Firebase Database quickstart sample for the Java Admin SDK.
 * See: https://firebase.google.com/docs/admin/setup#add_firebase_to_your_app
 */
public class Database {

    private static final String DATABASE_URL = "https://<YOUR-DATABASE>.firebaseio.com/";

    private static DatabaseReference database;

    /**
     * Notify a user of a new start and then update the last notification time.
     */
    private static void sendNotificationToUser(final String uid, final String postId) {
        // [START single_value_read]
        final DatabaseReference userRef = database.child("users").child(uid);
        userRef.addListenerForSingleValueEvent(new ValueEventListener() {
            public void onDataChange(DataSnapshot dataSnapshot) {
                User user = dataSnapshot.getValue(User.class);
                if (user.email != null) {
                    // Send email notification
//                    MyEmailer.sendNotificationEmail(user.email, uid, postId);
                }
            }

            public void onCancelled(DatabaseError databaseError) {
                System.out.println("Unable to get user data from " + userRef.getKey());
                System.out.println("Error: " + databaseError.getMessage());
            }
        });
        // [END single_value_read]
    }

    /**
     * Update the startCount value to equal the number of stars in the map.
     */
    private static void updateStarCount(DatabaseReference postRef) {
        // [START post_stars_transaction]
        postRef.runTransaction(new Transaction.Handler() {
            public Transaction.Result doTransaction(MutableData mutableData) {
                Post post = mutableData.getValue(Post.class);
                if (post != null) {
                    // Update the starCount to be the same as the number of members in the stars map.
                    if (post.stars != null) {
                        post.starCount = post.stars.size();
                    } else {
                        post.starCount = 0;
                    }

                    mutableData.setValue(post);
                    return Transaction.success(mutableData);
                } else {
                    return Transaction.success(mutableData);
                }
            }

            public void onComplete(DatabaseError databaseError, boolean complete, DataSnapshot dataSnapshot) {
                System.out.println("updateStarCount:onComplete:" + complete);
            }
        });
        // [END post_stars_transaction]
    }

    /**
     * Start global listener for all Posts.
     */
    public static void startListeners() {
        database.child("posts").addChildEventListener(new ChildEventListener() {

            public void onChildAdded(DataSnapshot dataSnapshot, String prevChildName) {
                final String postId = dataSnapshot.getKey();
                final Post post = dataSnapshot.getValue(Post.class);

                // Listen for changes in the number of stars and update starCount
                addStarsChangedListener(post, postId);

                // Listen for new stars on the post, notify users on changes
                addNewStarsListener(dataSnapshot.getRef(), post);
            }

            public void onChildChanged(DataSnapshot dataSnapshot, String prevChildName) {
            }

            public void onChildRemoved(DataSnapshot dataSnapshot) {
            }

            public void onChildMoved(DataSnapshot dataSnapshot, String prevChildName) {
            }

            public void onCancelled(DatabaseError databaseError) {
                System.out.println("startListeners: unable to attach listener to posts");
                System.out.println("startListeners: " + databaseError.getMessage());
            }
        });
    }

    /**
     * Listen for stars added or removed and update the starCount.
     */
    private static void addStarsChangedListener(Post post, String postId) {
        // Get references to the post in both locations
        final DatabaseReference postRef = database.child("posts").child(postId);
        final DatabaseReference userPostRef = database.child("user-posts").child(post.uid).child(postId);

        // When the post changes, update the star counts
        // [START post_value_event_listener]
        postRef.child("stars").addValueEventListener(new ValueEventListener() {
            public void onDataChange(DataSnapshot dataSnapshot) {
                updateStarCount(postRef);
                // [START_EXCLUDE]
                updateStarCount(userPostRef);
                // [END_EXCLUDE]
            }

            public void onCancelled(DatabaseError databaseError) {
                System.out.println("Unable to attach listener to stars for post: " + postRef.getKey());
                System.out.println("Error: " + databaseError.getMessage());
            }
        });
        // [END post_value_event_listener]
    }

    /**
     * Send email to author when new star is received.
     */
    private static void addNewStarsListener(final DatabaseReference postRef, final Post post) {
        // [START child_event_listener_recycler]
        postRef.child("stars").addChildEventListener(new ChildEventListener() {
            public void onChildAdded(DataSnapshot dataSnapshot, String prevChildName) {
                // New star added, notify the author of the post
                sendNotificationToUser(post.uid, postRef.getKey());
            }

            public void onChildChanged(DataSnapshot dataSnapshot, String prevChildName) {
            }

            public void onChildRemoved(DataSnapshot dataSnapshot) {
            }

            public void onChildMoved(DataSnapshot dataSnapshot, String prevChildName) {
            }

            public void onCancelled(DatabaseError databaseError) {
                System.out.println("Unable to attach new star listener to: " + postRef.getKey());
                System.out.println("Error: " + databaseError.getMessage());
            }
        });
        // [END child_event_listener_recycler]
    }

    /**
     * Send an email listing the top posts every Sunday.
     */
    private static void startWeeklyTopPostEmailer() {
        SundialJobScheduler.startScheduler("com.google.firebase.quickstart.email");
    }

    public static void main(String[] args) throws Exception {
        FirestoreOptions firestoreOptions =
                FirestoreOptions.newBuilder().setTimestampsInSnapshotsEnabled(true)
                        .setProjectId("firestore-confidential-data")
                        .build();
        Firestore db = firestoreOptions.getService();

        DocumentReference docRef = db.collection("users").document("alovelace");
// Add document data  with id "alovelace" using a hashmap
        Map<String, Object> data = new HashMap<>();
        data.put("first", "Ada");
        data.put("last", "Lovelace");
        data.put("born", 1815);
//asynchronously write data
        ApiFuture<WriteResult> result = docRef.set(data);
// ...
// result.get() blocks on response
        System.out.println("Update time : " + result.get().getUpdateTime());
    }

    public void initFirebase() {
        // Initialize Firebase
        try {
            // [START initialize]
            FileInputStream serviceAccount = new FileInputStream("service-account.json");
            FirebaseOptions options = new FirebaseOptions.Builder()
                    .setCredentials(GoogleCredentials.fromStream(serviceAccount))
                    .setDatabaseUrl(DATABASE_URL)
                    .build();
            FirebaseApp.initializeApp(options);
            // [END initialize]
        } catch (IOException e) {
            System.out.println("ERROR: invalid service account credentials. See README.");
            System.out.println(e.getMessage());

            System.exit(1);
        }

        // Shared Database reference
        database = FirebaseDatabase.getInstance().getReference();

        // Start listening to the Database
        startListeners();

        // Kick off weekly email task
        startWeeklyTopPostEmailer();
    }

}

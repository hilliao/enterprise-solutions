/* Official Google Java doc for OAuth2: https://developers.google.com/api-client-library/java/google-api-java-client/oauth2#googlecredential
 * referenced examples from `Update Spring problem also fixed`: https://stackoverflow.com/questions/31133757/spring-google-authentication-redirect-uri-mismatch-and-url-wont-open-on-browse
 * avoid using AuthorizationCodeInstalledApp at example: https://stackoverflow.com/questions/50104138/google-java-api-for-authorizationcodeinstalledapp-for-web-application
 * Official Google Cloud BigQuery user authentication doc: https://cloud.google.com/bigquery/docs/authentication/end-user-installed
 */

package com.intient.internal;

import com.google.api.client.auth.oauth2.Credential;
import com.google.api.client.googleapis.auth.oauth2.GoogleAuthorizationCodeFlow;
import com.google.api.client.googleapis.auth.oauth2.GoogleAuthorizationCodeRequestUrl;
import com.google.api.client.googleapis.auth.oauth2.GoogleTokenResponse;
import com.google.api.client.googleapis.javanet.GoogleNetHttpTransport;
import com.google.api.client.http.HttpTransport;
import com.google.api.client.json.JsonFactory;
import com.google.api.client.json.jackson2.JacksonFactory;
import com.google.api.client.util.store.FileDataStoreFactory;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.UserCredentials;
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.Dataset;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.ResponseBody;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.view.RedirectView;

import javax.servlet.http.HttpSession;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;


@RestController
public class GoogleOAuth2 {
    private static final List<String> scope = Arrays.asList("https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/compute.readonly", "https://www.googleapis.com/auth/cloud-platform");
    private static final java.io.File credentialFile = new java.io.File(System.getenv("HOME"),
            "GoogleOAuth2Credentials");
    public static String CALLBACK_URL;
    private static final String CLIENT_ID = System.getenv("CLIENT_ID");
    private static final String CLIENT_SECRET = System.getenv("CLIENT_SECRET");
    private static FileDataStoreFactory SampleFileDataStoreFactory;
    private static HttpTransport HTTP_TRANSPORT;
    private static final JsonFactory JSON_FACTORY = JacksonFactory.getDefaultInstance();

    static {
        if (System.getenv("LOCAL_DEBUG") != null) {
            CALLBACK_URL = "http://hil.freeddns.org:8080/callback";
        } else {
            CALLBACK_URL = "https://ai-notebook-mgmt-zro2itatnq-uc.a.run.app/callback";
        }

        try {
            HTTP_TRANSPORT = GoogleNetHttpTransport.newTrustedTransport();
            SampleFileDataStoreFactory = new FileDataStoreFactory(credentialFile);
        } catch (Throwable t) {
            t.printStackTrace();
            System.exit(1);
        }
    }

    /**
     * Authorizes the Java application to access user's protected data.
     */
    private static GoogleAuthorizationCodeFlow authorize() throws IOException {
        // set up authorization code flow
        GoogleAuthorizationCodeFlow flow = new GoogleAuthorizationCodeFlow.Builder(
                HTTP_TRANSPORT, JSON_FACTORY,
                CLIENT_ID,
                CLIENT_SECRET,
                scope)
                .setDataStoreFactory(SampleFileDataStoreFactory)
                .setAccessType("offline")
                .setApprovalPrompt("force") // need to force to get the refresh token
                .build();
        return flow;
    }

    @GetMapping("/login")
    public RedirectView login(HttpSession session) throws IOException {
        GoogleAuthorizationCodeFlow flow = authorize();
        String stateToken = getStateToken();
        session.setAttribute("state", stateToken);

        String url = buildLoginUrl(flow, stateToken);
        return new RedirectView(url); // https://www.baeldung.com/spring-redirect-and-forward
    }

    public String buildLoginUrl(GoogleAuthorizationCodeFlow flow, String stateToken) {
        final GoogleAuthorizationCodeRequestUrl url = flow.newAuthorizationUrl();
        return url.setRedirectUri(CALLBACK_URL).setState(stateToken).build();
    }

    /**
     * Generates a secure state token
     */
    public String getStateToken() {
        SecureRandom sr1 = new SecureRandom();
        return "google;" + sr1.nextInt();
    }

    @GetMapping("/projects/{projectId}/datasets")
    public BigQueryDatasets getDatasets(HttpSession session, @PathVariable String projectId) throws IOException {
        GoogleAuthorizationCodeFlow flow = authorize();
        String email = (String) session.getAttribute("userid");

        Credential credential = flow.loadCredential(email);

        GoogleCredentials gCredentials = UserCredentials.newBuilder()
                .setClientId(CLIENT_ID)
                .setClientSecret(CLIENT_SECRET)
                .setRefreshToken(credential.getRefreshToken())
                .build();
        List<String> datasets = getDatasets(gCredentials, projectId);
        BigQueryDatasets bigQueryDatasets = new BigQueryDatasets(
                credential.getAccessToken(),
                credential.getRefreshToken(),
                email,
                datasets);

        return bigQueryDatasets;
    }

    /**
     * Expects an Authentication Code, and makes an authenticated request for the user's profile information
     * * @param authCode authentication code provided by google
     */
    @GetMapping("/callback")
    public BigQueryDatasets callback(HttpSession session, @RequestParam(value = "code") String authCode) throws Exception {
        session.removeAttribute("state");
        GoogleAuthorizationCodeFlow flow = authorize();
        GoogleTokenResponse tokenResponse = flow.newTokenRequest(authCode).setRedirectUri(CALLBACK_URL).execute();
        String email = getUserEmail(tokenResponse);
        Credential credential = flow.createAndStoreCredential(tokenResponse, email);
        GoogleCredentials gCredentials = UserCredentials.newBuilder()
                .setClientId(CLIENT_ID)
                .setClientSecret(CLIENT_SECRET)
                .setRefreshToken(tokenResponse.getRefreshToken())
                .build();

        List<String> datasets = getDatasets(gCredentials, "bigquery-public-data");
        session.setAttribute("userid", email);
        session.setAttribute("auth", authCode);

        BigQueryDatasets bigQueryDatasets = new BigQueryDatasets(
                credential.getAccessToken(),
                credential.getRefreshToken(),
                email,
                datasets);

        return bigQueryDatasets;
    }

    public List<String> getDatasets(GoogleCredentials gCredentials, String projectId) throws IOException {


        BigQuery bigquery = BigQueryOptions.newBuilder()
                .setCredentials(gCredentials)
                .setProjectId(projectId)
                .build()
                .getService();
        List<String> datasets = new ArrayList<>();
        for (Dataset dataset : bigquery.listDatasets().iterateAll()) {
            datasets.add(dataset.getDatasetId().getDataset());
        }

        return datasets;
    }

    private String getUserEmail(GoogleTokenResponse response) throws IOException {
        Request request = new Request.Builder()
                .url("https://www.googleapis.com/oauth2/v1/userinfo?access_token=" + response.getAccessToken())
                .build();
        OkHttpClient client = new OkHttpClient();
        ResponseBody responseBody = client.newCall(request).execute().body();
        JsonObject userinfo = JsonParser.parseString(responseBody.string()).getAsJsonObject();
        String email = userinfo.get("email").getAsString();
        return email;
    }
}

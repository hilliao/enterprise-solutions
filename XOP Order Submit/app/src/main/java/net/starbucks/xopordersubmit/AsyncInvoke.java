package net.starbucks.xopordersubmit;

import android.os.AsyncTask;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import org.apache.http.HttpResponse;
import org.apache.http.client.HttpClient;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.entity.StringEntity;
import org.apache.http.impl.client.DefaultHttpClient;
import org.apache.http.message.BasicHttpResponse;
import org.apache.http.protocol.HTTP;

public class AsyncInvoke extends AsyncTask<String, String, String> {
    @Override
    protected String doInBackground(String... params) {
        String urlString = params[0]; // URL to call
        String httpPostXml = params[1];
        String resultToDisplay = "";

        try {
            HttpClient httpclient = new DefaultHttpClient();
            HttpPost post = new HttpPost(urlString);
            post.addHeader("Accept", "application/json, text/javascript, */*; q=0.01");
            post.addHeader("Content-Type", "application/xml");
            post.setEntity(new StringEntity(httpPostXml, HTTP.UTF_8));
            BasicHttpResponse httpResponse = (BasicHttpResponse) httpclient.execute(post);
            resultToDisplay = TextHelper.GetText(httpResponse);
        } catch (Exception e ) {
            return e.getMessage();
        }
        return resultToDisplay;
    }

    @Override
    protected void onPostExecute(String result) {
        super.onPostExecute(result);
    }
}

class TextHelper {
    public static String GetText(InputStream in) {
        String text = "";
        BufferedReader reader = new BufferedReader(new InputStreamReader(in));
        StringBuilder sb = new StringBuilder();
        String line = null;
        try {
            while ((line = reader.readLine()) != null) {
                sb.append(line + "\n");
            }
            text = sb.toString();
        } catch (Exception ex) {

        } finally {
            try {

                in.close();
            } catch (Exception ex) {
            }
        }
        return text;
    }

    public static String GetText(HttpResponse response) {
        String text = "";
        try {
            text = GetText(response.getEntity().getContent());
        } catch (Exception ex) {
        }
        return text;
    }
}
package net.starbucks.xopordersubmit;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.EditText;
import android.widget.TextView;
import net.starbucks.xopordersubmit.AsyncInvoke;

public class MainActivity extends Activity {
    public final static String PriceCheckResult = "com.example.xoppricecheck.MESSAGE";
    private String store;
    private String user;

    public void checkPrice(View view) {
        EditText userText = (EditText) findViewById(R.id.user_guid);
        EditText storeNumber = (EditText) findViewById(R.id.store_number);
        user = userText.getText().toString();
        store = storeNumber.getText().toString();

        String urlString = String.format("http://test3host.openapi.starbucks.com/expressorder/v1/users/%s/stores/%s/orderPricing?locale=en-US", user, store);
        TextView urlText = (TextView)findViewById(R.id.posturl);
        urlText.setText(getResources().getString(R.string.invoking) + " " + urlString);
        String postContent = ((TextView)findViewById(R.id.postcontent)).getText().toString();
        new InvokePriceCheck().execute(urlString, postContent);
    }

    private class InvokePriceCheck extends AsyncInvoke {

        @Override
        protected void onPostExecute(String result) {
            Intent intent = new Intent(getApplicationContext(), OrderSubmitActivity.class);
            intent.putExtra(PriceCheckResult, new String[] {result, user, store});
            startActivity(intent);
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
    }

    @Override
    protected void onResume() {
        super.onResume();
        TextView urlText = (TextView) findViewById(R.id.posturl);
        urlText.setText(R.string.url0);
    }
}
/*
import android.app.Activity;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;


public class MainActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
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
            return true;
        }

        return super.onOptionsItemSelected(item);
    }
}
*/
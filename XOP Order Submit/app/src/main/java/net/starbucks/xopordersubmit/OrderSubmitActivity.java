package net.starbucks.xopordersubmit;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import org.json.*;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import net.starbucks.xopordersubmit.AsyncInvoke;

public class OrderSubmitActivity extends Activity {
    private String orderToken;
    private String signature;
    private Double price;
    private String user;
    private String store;
    final public static String SubmitOrderXml = "<submitOrder><tenders><tender><type>SVC</type><id>856075FC</id><amountToCharge>3.12</amountToCharge></tender></tenders><signature>%s</signature></submitOrder>";

    public void submitOrder(View view) {
        String postContent = String.format(SubmitOrderXml, signature);
        String urlString = String.format("http://test3host.openapi.starbucks.com/expressorder/v1/users/%s/stores/%s/orderToken/%s/submitOrder?locale=en-US", user, store, orderToken);
        TextView urlText = (TextView) findViewById(R.id.postSubmitUrl);
        urlText.setText(getResources().getString(R.string.invoking) + " " + urlString);
        Button submitOrderButton = (Button) findViewById(R.id.submitOrder);
        submitOrderButton.setEnabled(false);
        new InvokeOrderSubmit().execute(urlString, postContent);
    }

    private class InvokeOrderSubmit extends AsyncInvoke {

        @Override
        protected void onPostExecute(String result) {
            TextView jsonView = (TextView)findViewById(R.id.jsonView);
            jsonView.setText("OrderSubmit result: " + result);
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_order_submit);

        Intent intent = getIntent();
        String[] orderDetails = intent.getStringArrayExtra(MainActivity.PriceCheckResult);
        TextView jsonView = (TextView)findViewById(R.id.jsonView);
        jsonView.setText("Price check result: " + orderDetails[0]);
        TextView urlText = (TextView) findViewById(R.id.postSubmitUrl);
        urlText.setText(R.string.url0);
        user = orderDetails[1];
        store = orderDetails[2];

        try {
            JSONObject jsonObject = new JSONObject(orderDetails[0]);
            signature = (String) jsonObject.get("signature");
            orderToken = (String) jsonObject.get("orderToken");
            JSONArray cartItems = (JSONArray) ((JSONObject) jsonObject.get("cart")).getJSONArray("items");
            price = (Double) ((JSONObject) cartItems.getJSONObject(0)).get("price");

            TextView priceView = (TextView)findViewById(R.id.orderPrice);
            priceView.setText(priceView.getText().toString() + price.toString());
        } catch (JSONException e) {
            e.printStackTrace();
        }
    }
}

/*
import android.app.Activity;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;


public class OrderSubmit extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_order_submit);
    }


    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        // Inflate the menu; this adds items to the action bar if it is present.
        getMenuInflater().inflate(R.menu.menu_order_submit, menu);
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
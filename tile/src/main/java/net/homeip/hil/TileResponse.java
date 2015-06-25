package net.homeip.hil;

/** The object model for the data we are sending through endpoints */
public class TileResponse {

    private String myData;

    public String getData() {
        return myData;
    }

    public void setData(String data) {
        myData = data;
    }
}

package net.homeip.hil;

import com.google.api.server.spi.config.Api;
import com.google.api.server.spi.config.ApiMethod;
import com.google.api.server.spi.config.ApiNamespace;

import javax.inject.Named;

/** An endpoint class we are exposing */
@Api(name = "tileservice",
     version = "v1",
     namespace = @ApiNamespace(ownerDomain = "net.homeip.hil",
                                ownerName = "net.homeip.hil",
                                packagePath=""),
        clientIds = {Constants.WEB_CLIENT_ID, Constants.ANDROID_CLIENT_ID, Constants.IOS_CLIENT_ID, Constants.API_EXPLORER_CLIENT_ID})
public class GetTile {

    /** A simple endpoint method that takes a name and says Hi back */
    @ApiMethod(name = "sayHi", httpMethod = ApiMethod.HttpMethod.GET)
    public TileResponse GetTile(@Named("name") String name) {
        TileResponse response = new TileResponse();
        response.setData("Hi, you got tile -> " + name);

        return response;
    }
}
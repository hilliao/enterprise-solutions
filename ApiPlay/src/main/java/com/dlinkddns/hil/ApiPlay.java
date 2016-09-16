package com.dlinkddns.hil;

import com.google.api.server.spi.Constant;
import com.google.api.server.spi.auth.common.User;
import com.google.api.server.spi.config.Api;
import com.google.api.server.spi.config.ApiMethod;
import com.google.api.server.spi.config.Nullable;
import com.google.api.server.spi.response.BadRequestException;
import com.google.api.server.spi.response.NotFoundException;
import com.google.appengine.api.datastore.Key;
import com.google.appengine.api.datastore.KeyFactory;
import com.google.appengine.api.oauth.OAuthRequestException;

import javax.inject.Named;
import javax.jdo.JDOObjectNotFoundException;
import javax.jdo.PersistenceManager;
import java.util.Random;

@Api(
        name = "ApiPlay", version = "1.1",
        scopes = Constant.API_EMAIL_SCOPE,
        clientIds = {Constants.WEB_CLIENT_ID, Constant.API_EXPLORER_CLIENT_ID}
)
public class ApiPlay {
    @ApiMethod(httpMethod = ApiMethod.HttpMethod.GET, name = "echoBack")
    public UserData echoBack(@Named("stringData") @Nullable String input, User user) throws OAuthRequestException {
        if (user == null) {
            throw new OAuthRequestException("Unauthorized user access attempted!");
        }

        UserData result = new UserData();
        result.setStringData(user.getEmail() + " of ID " + user.getId() + " entered " + input);

        return result;
    }

    @ApiMethod(httpMethod = ApiMethod.HttpMethod.POST, name = "postData")
    public com.google.appengine.api.datastore.Key postString(UserData input, User user)
            throws OAuthRequestException {
        if (user == null) {
            throw new OAuthRequestException("Unauthorized user access attempted!");
        }

        PersistenceManager pm = PMF.get().getPersistenceManager();
        UserData storeThis = new UserData();
        storeThis.setStringData(input.getStringData());
        Key newKey = KeyFactory.createKey(UserData.class.getSimpleName(), new Random().nextLong());
        storeThis.setKey(newKey);
        pm.makePersistent(storeThis);

        return newKey;
    }

    @ApiMethod(httpMethod = ApiMethod.HttpMethod.GET, name = "getByID")
    public UserData getUserDataById(@Named("Id") long id, User user) throws NotFoundException, OAuthRequestException {
        UserData dataFound;

        if (user == null) {
            throw new OAuthRequestException("Unauthorized user access attempted!");
        }

        PersistenceManager pm = PMF.get().getPersistenceManager();
        Key existingKey = KeyFactory.createKey(UserData.class.getSimpleName(), id);
        try {
            dataFound = pm.getObjectById(UserData.class, existingKey);
        } catch (JDOObjectNotFoundException ex) {
            throw new NotFoundException(String.format("User data of ID %d not found", id), ex);
        }

        return dataFound;
    }

    @ApiMethod(httpMethod = ApiMethod.HttpMethod.PUT, name = "putByID")
    public UserData putUserDataById(@Named("id") long id, UserData input, User user)
            throws NotFoundException, BadRequestException, OAuthRequestException {
        UserData dataFound;

        if (user == null) {
            throw new OAuthRequestException("Unauthorized user access attempted!");
        }

        PersistenceManager pm = PMF.get().getPersistenceManager();
        Key existingKey = KeyFactory.createKey(UserData.class.getSimpleName(), id);
        try {
            dataFound = pm.getObjectById(UserData.class, existingKey);
        } catch (JDOObjectNotFoundException ex) {
            throw new NotFoundException(String.format("User data of ID %d not found", id), ex);
        }

        try {
            pm.currentTransaction().begin();
            dataFound.setStringData(input.getStringData());
            pm.currentTransaction().commit();
        } catch (Throwable t) {
            pm.currentTransaction().rollback();
            throw new BadRequestException("Failed to modify by ID", t);
        }

        return dataFound;
    }

    @ApiMethod(httpMethod = ApiMethod.HttpMethod.DELETE, name = "deleteByID", path = "deleteById/{id}")
    public void deleteUserDataById(@Named("id") long id, User user) throws NotFoundException, OAuthRequestException {
        UserData dataFound;

        if (user == null) {
            throw new OAuthRequestException("Unauthorized user access attempted!");
        }

        PersistenceManager pm = PMF.get().getPersistenceManager();
        Key existingKey = KeyFactory.createKey(UserData.class.getSimpleName(), id);
        try {
            dataFound = pm.getObjectById(UserData.class, existingKey);
        } catch (JDOObjectNotFoundException ex) {
            throw new NotFoundException(String.format("User data of ID %d not found", id), ex);
        }
        pm.deletePersistent(dataFound);
    }
}
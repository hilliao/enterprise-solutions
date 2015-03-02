package com.example.helloendpoints;

import com.google.api.server.spi.config.Api;
import com.google.api.server.spi.config.ApiMethod;
import com.google.api.server.spi.response.NotFoundException;
import com.google.appengine.api.datastore.DatastoreService;
import com.google.appengine.api.datastore.DatastoreServiceFactory;
import com.google.appengine.api.users.User;
import com.google.appengine.api.datastore.Query;
import com.google.appengine.api.datastore.PreparedQuery;
import com.google.appengine.api.datastore.Entity;

import java.util.ArrayList;
import javax.inject.Named;

/**
 * Defines v1 of a helloworld API, which provides simple "greeting" methods.
 */
@Api(
    name = "helloworld",
    version = "v1",
    scopes = {Constants.EMAIL_SCOPE},
    clientIds = {Constants.WEB_CLIENT_ID, Constants.ANDROID_CLIENT_ID, Constants.IOS_CLIENT_ID, Constants.API_EXPLORER_CLIENT_ID},
    audiences = {Constants.ANDROID_AUDIENCE}
)
public class Greetings {

  public HelloGreeting getGreeting(@Named("id") Integer id) throws NotFoundException {
    try {
      return this.listGreeting().get(id);
    } catch (IndexOutOfBoundsException e) {
      throw new NotFoundException("Greeting not found at index: " + id);
    }
  }
  
  @ApiMethod(httpMethod = "get")
  public ArrayList<HelloGreeting> listGreeting() {
	  ArrayList<HelloGreeting> list = new ArrayList<HelloGreeting>();
	  
	  DatastoreService datastore = DatastoreServiceFactory.getDatastoreService();
	  Query q = new Query("greetings");
	  PreparedQuery pq = datastore.prepare(q);
	  for (Entity result : pq.asIterable()) {
		  String greeting = (String) result.getProperty("greeting");
		  list.add(new HelloGreeting(greeting));
	  }
	  return list;
  }
  
  @ApiMethod(name = "greetings.addNew", httpMethod = "post")
  public Entity addGreeting(@Named("newGreeting") String newGreeting) {
	  DatastoreService datastore = DatastoreServiceFactory.getDatastoreService();
	  Entity greeting = new Entity(Constants.DATASTORE_KIND_GREETINGS);
	  greeting.setProperty("greeting", newGreeting);
	  datastore.put(greeting);
	  //this.greetings.add(new HelloGreeting(newGreeting));
	  return greeting;
  }

  @ApiMethod(name = "greetings.multiply", httpMethod = "post")
  public HelloGreeting insertGreeting(@Named("times") Integer times, HelloGreeting greeting) {
    HelloGreeting response = new HelloGreeting();
    StringBuilder responseBuilder = new StringBuilder();
    for (int i = 0; i < times; i++) {
      responseBuilder.append(greeting.getMessage());
    }
    response.setMessage(responseBuilder.toString());
    return response;
  }

  @ApiMethod(name = "greetings.authed", path = "hellogreeting/authed")
  public HelloGreeting authedGreeting(User user) {
    HelloGreeting response = new HelloGreeting("hello " + user.getEmail());
    return response;
  }
}

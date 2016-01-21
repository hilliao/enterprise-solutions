package com.example.helloendpoints;

import com.google.api.server.spi.config.Api;
import com.google.api.server.spi.config.ApiMethod;
import com.google.api.server.spi.config.ApiMethod.HttpMethod;
import com.google.api.server.spi.response.NotFoundException;
import com.google.appengine.api.datastore.*;
import com.google.appengine.api.users.User;

import javax.inject.Named;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.concurrent.*;

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

    public HelloGreeting getGreeting(@Named("id") final Integer id) throws NotFoundException, InterruptedException, ExecutionException {
        try {
            java.lang.Thread.sleep(234);
        } catch (InterruptedException e) {
            //need to log exception
        }
        int cores = Runtime.getRuntime().availableProcessors();
        ExecutorService executor = Executors.newFixedThreadPool(cores);
        Future<HelloGreeting> future;
        try {
            future = executor.submit(new Callable<HelloGreeting>() {
                @Override
                public HelloGreeting call() {
                    return Greetings.this.listGreeting().get(id);
                }
            });
        } catch (IndexOutOfBoundsException e) {
            throw new NotFoundException("Greeting not found at index: " + id);
        }
        return future.get();
    }

    @ApiMethod(httpMethod = HttpMethod.GET)
    public ArrayList<HelloGreeting> listGreeting() {
        ArrayList<HelloGreeting> list = new ArrayList<HelloGreeting>();

        DatastoreService datastore = DatastoreServiceFactory.getDatastoreService();
        Query q = new Query("greetings");
        PreparedQuery pq = datastore.prepare(q);
        for (Entity result : pq.asIterable()) {
            String greeting = (String) result.getProperty("greeting");
            list.add(new HelloGreeting(greeting));
        }
        //for Java 8: list.sort((g1, g2) -> g1.getMessage().compareTo(g2.getMessage()));
        Collections.sort(list, new Comparator<HelloGreeting>() {
            @Override
            public int compare(HelloGreeting o1, HelloGreeting o2) {
                return o1.getMessage().compareTo(o2.getMessage());
            }
        });
        return list;
    }

    @ApiMethod(name = "greetings.addNew", httpMethod = HttpMethod.POST)
    public Entity addGreeting(@Named("newGreeting") String newGreeting) {
        DatastoreService datastore = DatastoreServiceFactory.getDatastoreService();
        Entity greeting = new Entity(Constants.DATASTORE_KIND_GREETINGS);
        greeting.setProperty("greeting", newGreeting);
        datastore.put(greeting);

        return greeting;
    }

    @ApiMethod(name = "greetings.multiply", httpMethod = HttpMethod.POST)
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
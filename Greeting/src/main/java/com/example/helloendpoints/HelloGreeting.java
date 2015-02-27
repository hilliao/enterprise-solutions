package com.example.helloendpoints;

import com.google.appengine.api.datastore.DatastoreServiceFactory;
import com.google.appengine.api.datastore.DatastoreService;
import com.google.appengine.api.datastore.Query.Filter;
import com.google.appengine.api.datastore.Query.FilterPredicate;
import com.google.appengine.api.datastore.Query.FilterOperator;
import com.google.appengine.api.datastore.Query;
import com.google.appengine.api.datastore.PreparedQuery;
import com.google.appengine.api.datastore.Entity;
import com.google.appengine.api.datastore.FetchOptions;

public class HelloGreeting {

  public String message;

  public HelloGreeting() {};

  public HelloGreeting(String message) {
    this.message = message;
    //appendMessage(99);
  }

  public String getMessage() {
    return message;
  }

  public void setMessage(String message) {
    this.message = message;
  }
  
  public void appendMessage(int moneyMin) {
	  // Get the Datastore Service
	  DatastoreService datastore = DatastoreServiceFactory.getDatastoreService();
//	  Entity testEntity = new Entity("people", datastore.hashCode());
//	  datastore.put(testEntity);
	  
	  Filter moneyFilter = new FilterPredicate("money",
              FilterOperator.GREATER_THAN_OR_EQUAL,
              moneyMin);
	  
	  // Use class Query to assemble a query
	  Query q = new Query(Constants.DATASTORE_KIND_PEOPLE).setFilter(moneyFilter);
      // Use PreparedQuery interface to retrieve results
	  PreparedQuery pq = datastore.prepare(q);
	  int listSize = pq.asList(FetchOptions.Builder.withLimit(10)).size();
	  this.message += "~" + listSize + "~";
	  
	  for (Entity result : pq.asIterable()) {
		  String name = (String) result.getProperty("name");
		  this.message += ", " + name;
	  }
  }
}

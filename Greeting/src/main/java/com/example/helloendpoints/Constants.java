package com.example.helloendpoints;

/**
 * Contains the client IDs and scopes for allowed clients consuming the helloworld API.
 */
public class Constants {
  public static final String WEB_CLIENT_ID = "776318621121-u7r4fpkhhpig2jei6hs6ng0jcqtfgdji.apps.googleusercontent.com";
  public static final String ANDROID_CLIENT_ID = "replace this with your Android client ID";
  public static final String IOS_CLIENT_ID = "replace this with your iOS client ID";
  public static final String ANDROID_AUDIENCE = WEB_CLIENT_ID;

  public static final String EMAIL_SCOPE = "https://www.googleapis.com/auth/userinfo.email";
  public static final String API_EXPLORER_CLIENT_ID = com.google.api.server.spi.Constant.API_EXPLORER_CLIENT_ID;
  public static final String DATASTORE_KIND_GREETINGS = "greetings";
  public static final String DATASTORE_KIND_PEOPLE = "people";
}


interface IShape<T>
{
	T GetArea();
}

class Rectangle implements IShape<Number>
{
	public Number GetArea() {
		Double d = new Double(1.03);
		return d;
	}
}

class Square extends Rectangle implements IShape<Number> {
	public Float GetArea() {
		Float f = new Float(1);
		return f;
	}
}

class Test {
	void Try() {
		Square s = new Square();
		Rectangle r = new Rectangle();
		r = s; // assignment achieved
		
		IShape<? extends Number> s0 = r;
	}
}
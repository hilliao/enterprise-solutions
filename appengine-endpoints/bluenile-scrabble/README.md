# App Engine Standard & Google Cloud Endpoints Frameworks & Java

This sample demonstrates how to use Google Cloud Endpoints Frameworks using
Java on App Engine Standard.

## Build with Maven and IntelliJ
0. The latest build, debug, and deployment instructions are at https://cloud.google.com/endpoints/docs/frameworks/java/get-started-frameworks-java
0. Download the latest IntelliJ IDEA and install the latest plugin of Google Cloud Tools by following instructions at https://cloud.google.com/tools/intellij/docs/
0. Make sure Java 8 is configured in IntelliJ IDEA and installed on the development environment. Verify with java -version
0. Make sure the latest Google cloud SDK is installed. The older SDK did not support Java 8 in Google App Engine.
0. Debugging in IntelliJ by using Google app engine standard local server may result in the following error:
    
         Oct 13, 2017 3:49:27 PM com.google.appengine.tools.development.InstanceHelper sendStartRequest    
         WARNING: Start request to /_ah/start on server 0.default failed (HTTP status code=503). Retrying...

    The solution is to run mvn clean package and add environment variable ENDPOINTS_SERVICE_NAME to Run/Debug Configurations -> Startup/Connection ->
 Environment variables. The `Value` is [YOUR_PROJECT_ID].appspot.com. Check the Intellij_run_configuration_environment_variables.png file in the project.

### Building the whole project

To build the project:

    mvn clean package

### Generating the openapi.json file

To generate the required configuration file `openapi.json`:

    mvn endpoints-framework:openApiDocs

### Deploying the sample API to App Engine

To deploy the sample API:

0. Invoke the `gcloud` command to deploy the API configuration file:

         gcloud service-management deploy target/openapi-docs/openapi.json

0. Deploy the API implementation code by invoking:

         mvn appengine:deploy

    The first time you upload a sample app, you may be prompted to authorize the
    deployment. Follow the prompts: when you are presented with a browser window
    containing a code, copy it to the terminal window.

0. Wait for the upload to finish.

### Sending a request to the bluenile API

After you deploy the API and its configuration file, you can send requests
to the API.

To send a request to the API, from a command line, invoke the following `cURL`
command:

     curl -X GET \
      http://localhost:8080/_ah/api/scrabble/v1/bluenile/words/HAT-
    curl -X GET \
      https://careful-sphinx-161801.appspot.com/_ah/api/scrabble/v1/bluenile/words/HAT-

You will get a 200 response with the following data:

    {
        "words": ["hat","ah","ha","th","at","a"]
    }

### Sending a request to the sample API

After you deploy the API and its configuration file, you can send requests
to the API.

To send a request to the API, from a command line, invoke the following `cURL`
command:

     curl \
         -H "Content-Type: application/json" \
         -X POST \
         -d '{"message":"echo"}' \
         https://$PROJECT_ID.appspot.com/_ah/api/echo/v1/echo

You will get a 200 response with the following data:

    {
     "message": "echo"
    }


## Scrabble Solver Service

### Summary

Implement an HTTP REST service that returns Scrabble words for a given set of letters.

### Data source

Use the list of words here: http://www-01.sil.org/linguistics/wordlists/english/wordlist/wordsEn.txt

### API Specification

The REST web service runs on port 8080 and responds to a URL of the pattern http://localhost:8080/words/<letters>, where <letters> is a string of arbitrary
letters. There are two cases that need to be covered:

    1. The dictionary contains words that can be spelled with the given letters.

      A JSON list of strings is returned, where each entry is a word. They are sorted by Scrabble score, from highest to lowest scoring. For example:

      Request URL:       http://localhost:8080/words/hat
      Expected response: ["hat","ah","ha","th","at","a"]

      The letters are like Scrabble tiles. Order is unimportant:

      Request URL:       http://localhost:8080/words/aht
      Expected response: ["hat","ah","ha","th","at","a"]

      The letters are not case-sensitive, so this returns the same results:

      Request URL:       http://localhost:8080/words/HAT
      Expected response: ["hat","ah","ha","th","at","a"]

      Request URL:       http://localhost:8080/words/Hat
      Expected response: ["hat","ah","ha","th","at","a"]

    2. No dictionary words can be spelled with the given letters.

      An empty JSON list is returned.  For example:

      Request URL:       http://localhost:8080/words/zzz
      Expected response: []

The Scrabble score is calculated by adding up the point values of every letter in the word.
The point values are:

    Points | Letters
    -------+-----------------------------
       1   | A, E, I, L, N, O, R, S, T, U
       2   | D, G
       3   | B, C, M, P
       4   | F, H, V, W, Y
       5   | K
       8   | J, X
      10   | Q, Z

For example, the following words have these scores:

hat:  6
code: 7
antidisestablishmenatarianism: 39

(From https://en.wikipedia.org/wiki/Scrabble_letter_distributions)
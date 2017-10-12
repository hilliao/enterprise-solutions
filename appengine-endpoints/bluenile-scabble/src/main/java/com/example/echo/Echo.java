/*
 * Copyright (c) 2016 Google Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may
 * not  use this file except in compliance with the License. You may obtain a
 * copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
 * License for the specific language governing permissions and limitations under
 * the License.
 */

package com.example.echo;

import com.google.api.server.spi.auth.EspAuthenticator;
import com.google.api.server.spi.auth.common.User;
import com.google.api.server.spi.config.AnnotationBoolean;
import com.google.api.server.spi.config.Api;
import com.google.api.server.spi.config.ApiIssuer;
import com.google.api.server.spi.config.ApiIssuerAudience;
import com.google.api.server.spi.config.ApiMethod;
import com.google.api.server.spi.config.ApiNamespace;
import com.google.api.server.spi.config.Named;
import com.google.api.server.spi.config.Nullable;
import com.google.api.server.spi.response.UnauthorizedException;
import com.google.appengine.api.utils.SystemProperty;
import com.google.appengine.tools.cloudstorage.*;
import org.apache.commons.io.IOUtils;

import java.io.IOException;
import java.nio.channels.Channels;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

/**
 * The Echo API which Endpoints will be exposing.
 */
// [START echo_api_annotation]
@Api(
        name = "echo",
        version = "v1",
        namespace =
        @ApiNamespace(
                ownerDomain = "echo.example.com",
                ownerName = "echo.example.com",
                packagePath = ""
        ),
        // [START_EXCLUDE]
        issuers = {
                @ApiIssuer(
                        name = "firebase",
                        issuer = "https://securetoken.google.com/YOUR-PROJECT-ID",
                        jwksUri =
                                "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system"
                                        + ".gserviceaccount.com"
                )
        }
// [END_EXCLUDE]
)
// [END echo_api_annotation]

public class Echo {
    /**
     * Used below to determine the size of chucks to read in. Should be > 1kb and < 10MB
     */
    private static final int BUFFER_SIZE = 2 * 1024 * 1024;

    /**
     * This is where backoff parameters are configured. Here it is aggressively retrying with
     * backoff, up to 10 times but taking no more that 15 seconds total to do so.
     */
    private final GcsService gcsService = GcsServiceFactory.createGcsService(new RetryParams.Builder()
            .initialRetryDelayMillis(10)
            .retryMaxAttempts(10)
            .totalRetryPeriodMillis(15000)
            .build());

    @ApiMethod(
            httpMethod = ApiMethod.HttpMethod.GET,
            name = "scrabble_solver_service", path = "bluenile/word/{letters}")
    public WordScore bluenileScrabble(@Named("letters") String letters) throws IOException {
        String words;
        // get the dictionary's words
        if (SystemProperty.environment.value() == SystemProperty.Environment.Value.Production) {
            GcsFilename fileName = new GcsFilename("careful-sphinx-161801.appspot.com", "wordsEn.txt");
            GcsInputChannel readChannel = gcsService.openPrefetchingReadChannel(fileName, 0, BUFFER_SIZE);
            words = IOUtils.toString(Channels.newInputStream(readChannel), "UTF-8");
        } else {
            words = "at\nthe\nhas\nas";
            WordManager wordManager = new WordManager(words);
            wordManager.isValid("fdklsjfghgg");
        }

        WordScore result = new WordScore();
        result.words = Arrays.asList(letters, String.valueOf(words.length()));
        return result;
    }

    /**
     * Echoes the received message back. If n is a non-negative integer, the message is copied that
     * many times in the returned message.
     * <p>
     * <p>Note that name is specified and will override the default name of "{class name}.{method
     * name}". For example, the default is "echo.echo".
     * <p>
     * <p>Note that httpMethod is not specified. This will default to a reasonable HTTP method
     * depending on the API method name. In this case, the HTTP method will default to POST.
     */
    // [START echo_method]
    @ApiMethod(name = "echo")
    public Message echo(Message message, @Named("n") @Nullable Integer n) {
        Character[] a = {'a', 'b'};
        Stream<Character> s = Arrays.stream(a);
        return doEcho(message, n);
    }
    // [END echo_method]

    /**
     * Echoes the received message back. If n is a non-negative integer, the message is copied that
     * many times in the returned message.
     * <p>
     * <p>Note that name is specified and will override the default name of "{class name}.{method
     * name}". For example, the default is "echo.echo".
     * <p>
     * <p>Note that httpMethod is not specified. This will default to a reasonable HTTP method
     * depending on the API method name. In this case, the HTTP method will default to POST.
     */
    // [START echo_path]
    @ApiMethod(name = "echo_path_parameter", path = "echo/{n}")
    public Message echoPathParameter(Message message, @Named("n") int n) {
        return doEcho(message, n);
    }
    // [END echo_path]

    /**
     * Echoes the received message back. If n is a non-negative integer, the message is copied that
     * many times in the returned message.
     * <p>
     * <p>Note that name is specified and will override the default name of "{class name}.{method
     * name}". For example, the default is "echo.echo".
     * <p>
     * <p>Note that httpMethod is not specified. This will default to a reasonable HTTP method
     * depending on the API method name. In this case, the HTTP method will default to POST.
     */
    // [START echo_api_key]
    @ApiMethod(name = "echo_api_key", path = "echo_api_key", apiKeyRequired = AnnotationBoolean.TRUE)
    public Message echoApiKey(Message message, @Named("n") @Nullable Integer n) {
        return doEcho(message, n);
    }
    // [END echo_api_key]

    private Message doEcho(Message message, Integer n) {
        if (n != null && n >= 0) {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < n; i++) {
                if (i > 0) {
                    sb.append(" ");
                }
                sb.append(message.getMessage());
            }
            message.setMessage(sb.toString());
        }
        return message;
    }

    /**
     * Gets the authenticated user's email. If the user is not authenticated, this will return an HTTP
     * 401.
     * <p>
     * <p>Note that name is not specified. This will default to "{class name}.{method name}". For
     * example, the default is "echo.getUserEmail".
     * <p>
     * <p>Note that httpMethod is not required here. Without httpMethod, this will default to GET due
     * to the API method name. httpMethod is added here for example purposes.
     */
    // [START google_id_token_auth]
    @ApiMethod(
            httpMethod = ApiMethod.HttpMethod.GET,
            authenticators = {EspAuthenticator.class},
            audiences = {"YOUR_OAUTH_CLIENT_ID"},
            clientIds = {"YOUR_OAUTH_CLIENT_ID"}
    )
    public Email getUserEmail(User user) throws UnauthorizedException {
        if (user == null) {
            throw new UnauthorizedException("Invalid credentials");
        }

        Email response = new Email();
        response.setEmail(user.getEmail());
        return response;
    }
    // [END google_id_token_auth]

    /**
     * Gets the authenticated user's email. If the user is not authenticated, this will return an HTTP
     * 401.
     * <p>
     * <p>Note that name is not specified. This will default to "{class name}.{method name}". For
     * example, the default is "echo.getUserEmail".
     * <p>
     * <p>Note that httpMethod is not required here. Without httpMethod, this will default to GET due
     * to the API method name. httpMethod is added here for example purposes.
     */
    // [START firebase_auth]
    @ApiMethod(
            path = "firebase_user",
            httpMethod = ApiMethod.HttpMethod.GET,
            authenticators = {EspAuthenticator.class},
            issuerAudiences = {
                    @ApiIssuerAudience(
                            name = "firebase",
                            audiences = {"YOUR-PROJECT-ID"}
                    )
            }
    )
    public Email getUserEmailFirebase(User user) throws UnauthorizedException {
        if (user == null) {
            throw new UnauthorizedException("Invalid credentials");
        }

        Email response = new Email();
        response.setEmail(user.getEmail());
        return response;
    }
    // [END firebase_auth]
}

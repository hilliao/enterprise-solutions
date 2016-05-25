package com.dlinkddns.hil;

import com.google.api.server.spi.auth.common.User;
import com.google.api.server.spi.config.AnnotationBoolean;
import com.google.api.server.spi.config.Api;
import com.google.api.server.spi.config.ApiMethod;
import com.google.api.server.spi.config.ApiNamespace;
import com.google.api.server.spi.config.ApiResourceProperty;
import com.google.api.server.spi.response.NotFoundException;
import com.google.appengine.api.oauth.OAuthRequestException;

import java.io.IOException;

import javax.inject.Named;

@com.google.api.server.spi.config.Api(name = "apiPlayground", version = "v1")
public class ApiPlay {
    @ApiMethod(httpMethod = ApiMethod.HttpMethod.GET, name = "echo")
    public EchoResult echoBack(@Named("stringData") String input) {
        EchoResult result = new EchoResult();
        result.echoBack = input;

        return result;
    }
}
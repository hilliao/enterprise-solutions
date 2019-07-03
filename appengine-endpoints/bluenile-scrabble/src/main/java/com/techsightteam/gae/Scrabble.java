/*
 * Copyright (c) 2016 techsightteam Inc.
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

package com.techsightteam.gae;

import com.google.api.server.spi.config.*;
import com.google.api.server.spi.response.InternalServerErrorException;
import com.google.appengine.api.memcache.MemcacheService;
import com.google.appengine.api.memcache.MemcacheServiceFactory;
import com.google.appengine.api.utils.SystemProperty;
import com.google.appengine.tools.cloudstorage.*;
import org.apache.commons.io.IOUtils;

import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.logging.Logger;

/**
 * scrabble game simulation
 */
@Api(
        name = "scrabble",
        version = "v1",
        namespace =
        @ApiNamespace(
                ownerDomain = "techsightteam.com",
                ownerName = "Hil",
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
)
public class Scrabble {
    /**
     * Used below to determine the size of chucks to read in. Should be > 1kb and < 10MB
     */
    private static final int BUFFER_SIZE = 2 * 1024 * 1024;
    public static final String DICT_FILE = "wordsEn.txt";
    public static final String DICT_PATH = "/tmp/wordsEn.txt";
    public static final String DICT_ENCODING = "UTF-8";

    /**
     * This is where backoff parameters are configured. Here it is aggressively retrying with
     * backoff, up to 10 times but taking no more that 15 seconds total to do so.
     */
    private final GcsService gcsService = GcsServiceFactory.createGcsService(new RetryParams.Builder()
            .initialRetryDelayMillis(10)
            .retryMaxAttempts(10)
            .totalRetryPeriodMillis(15000)
            .build());

    private static final Logger log = Logger.getLogger(Scrabble.class.getName());

    public static String cacheKeyDict = "dict";

    @ApiMethod(
            httpMethod = ApiMethod.HttpMethod.GET,
            name = "scrabble_solver_service", path = "bluenile/words/{letters}")
    public WordScore bluenileScrabble(
            @Named("letters") String letters,
            @Named("withscores") @Nullable Boolean withScores) throws InternalServerErrorException {
        String dictWords;
        letters = letters.toLowerCase();

        try {
            dictWords = getDictWords();
        } catch (IOException | ClassNotFoundException ex) {
            String error = "Failed to get dictionary words";
            log.severe(error + ": " + ex.toString());
            throw new InternalServerErrorException(error, ex.toString(), ex);
        }

        WordManager wordManager = new WordManager(dictWords);
        List<String> words = wordManager.getWordsFrom(letters);
        WordScore wordScore = new WordScore(words);

        if (withScores == null || !withScores) {
            wordScore.scores = null;
        }

        return wordScore;
    }

    private String getDictWords() throws IOException, ClassNotFoundException {
        String dictWords;// check if dictionary is cached
        MemcacheService syncCache = MemcacheServiceFactory.getMemcacheService();
        MemcacheService.IdentifiableValue dictCache = syncCache.getIdentifiable(cacheKeyDict);

        if (dictCache == null) {
            // get the dictionary's words
            if (SystemProperty.environment.value() == SystemProperty.Environment.Value.Production) {
                // bucketName = "staging.firestore-confidential-data.appspot.com"
                GcsFilename fileName = new GcsFilename("staging." + SystemProperty.applicationId.get() + ".appspot.com", DICT_FILE);
                GcsInputChannel readChannel = gcsService.openPrefetchingReadChannel(fileName, 0, BUFFER_SIZE);
                dictWords = IOUtils.toString(Channels.newInputStream(readChannel), DICT_ENCODING);
            } else { // running on local development server
                dictWords = new String(Files.readAllBytes(Paths.get(DICT_PATH)));
            }

            // need to compress the dictionary to avoid 1MB limit
            byte[] bytes = CompressString.compressString(dictWords);
            boolean isAddedToCache = syncCache.put(cacheKeyDict, bytes, null, MemcacheService.SetPolicy.ADD_ONLY_IF_NOT_PRESENT);
            if (isAddedToCache) {
                log.info("Dictionary words added to Memcache");
            }
        } else {
            // decompress from cache to String
            byte[] bytes = (byte[]) dictCache.getValue();
            dictWords = CompressString.decompressString(bytes);
        }
        return dictWords;
    }

    @ApiMethod(httpMethod = ApiMethod.HttpMethod.GET, name = "echotest", path = "echo/{pathparam}")
    public EchoBack echo(@Named("pathparam") String pathParam, @Named("queryparam") @Nullable String queryParam) {
        EchoBack echoResult = new EchoBack();
        echoResult.pathParam = pathParam;
        echoResult.queryParam = queryParam;
        return echoResult;
    }

    public static class EchoBack {
        public String pathParam;
        public String queryParam;
    }
}

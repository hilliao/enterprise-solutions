package com.intient.internal;

import java.util.List;

public class BigQueryDatasets {
    private final String accessToken;
    private final String refreshToken;
    private final String userEmail;
    private final List<String> datasets;

    public BigQueryDatasets(String accessToken, String refreshToken, String userEmail, List<String> datasets) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
        this.userEmail = userEmail;
        this.datasets = datasets;
    }

    public String getUserEmail() {
        return userEmail;
    }

    public String getAccessToken() {
        return accessToken;
    }

    public String getRefreshToken() {
        return refreshToken;
    }

    public List<String> getDatasets() {
        return datasets;
    }
}

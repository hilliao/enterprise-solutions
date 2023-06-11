package com.techsightteam;

public class SleepTracked {

    private final long id;
    private final String content;

    public SleepTracked(long id, String content) {
        this.id = id;
        this.content = content;
    }

    public long getId() {
        return id;
    }

    public String getContent() {
        return content;
    }
}

package com.dlinkddns.hil.naptimealarm;

import java.util.HashMap;
import java.util.Map;

/**
 * initially only seconds and minutes are used on the UI
 */
public class TimeInterval {
    public int hours;
    public int minutes;
    public int seconds;

    public TimeInterval() {
        // Default constructor required for calls to DataSnapshot.getValue(Post.class)
    }

    public TimeInterval(int hours, int minutes, int seconds) {
        this.hours = hours;
        this.minutes = minutes;
        this.seconds = seconds;
    }

    public Map<String, Object> toMap() {
        Map<String, Object> timeInterval = new HashMap<>();
        timeInterval.put("minutes", minutes);
        timeInterval.put("seconds", seconds);
        timeInterval.put("hours", hours);

        return timeInterval;
    }
}

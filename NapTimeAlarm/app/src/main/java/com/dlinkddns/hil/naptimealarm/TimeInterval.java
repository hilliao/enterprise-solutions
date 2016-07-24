package com.dlinkddns.hil.naptimealarm;

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
}

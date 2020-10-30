package com.dlinkddns.hil;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class Runner {
    public static class Row {
        public UUID session_id;
        public String user_id;
        public Integer steps;

        public Row(UUID uuid, String user_id, int steps) {
            this.session_id = uuid;
            this.user_id = user_id;
            this.steps = steps;
        }
    }

    public static void main(String[] args) {
        Row r0 = new Row(UUID.randomUUID(), "user1", 897);
        Row r1 = new Row(UUID.randomUUID(), "user1", 456);
        Row r2 = new Row(UUID.randomUUID(), "user2", 321);
        Row r3 = new Row(UUID.randomUUID(), "user2", 421);
        Row r4 = new Row(UUID.randomUUID(), "user2", 977);
        Row r5 = new Row(UUID.randomUUID(), "user3", 568);
        List<Row> rows = Arrays.asList(r0, r1, r2, r3, r4, r5);
        System.out.println(Aggregate(rows));
    }

    public static ConcurrentHashMap<String, Integer> Aggregate(List<Row> rows) {
        ConcurrentHashMap<String, Integer> aggregates = new ConcurrentHashMap<>();

        rows.parallelStream().forEach(row -> aggregates.compute(
                row.user_id, (k, v) -> v == null ? row.steps : v + row.steps));
        return aggregates;
    }
}

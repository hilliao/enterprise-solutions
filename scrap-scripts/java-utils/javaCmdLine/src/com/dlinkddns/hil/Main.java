package com.dlinkddns.hil;

import java.util.*;
import java.util.stream.Collectors;

public class Main {

    static <K, V extends Comparable<? super V>>
    SortedSet<Map.Entry<K, V>> entriesSortedByValues(Map<K, V> map) {
        SortedSet<Map.Entry<K, V>> sortedEntries = new TreeSet<Map.Entry<K, V>>(
                new Comparator<Map.Entry<K, V>>() {
                    @Override
                    public int compare(Map.Entry<K, V> e1, Map.Entry<K, V> e2) {
                        int res = e1.getValue().compareTo(e2.getValue());
                        return res != 0 ? res : 1;
                    }
                }
        );
        sortedEntries.addAll(map.entrySet());
        return sortedEntries;
    }

    static void customSort(int[] arr) {
        // key is the input int, value is the int's frequency
        SortedMap<Integer, Integer> freq = new TreeMap<Integer, Integer>();
        for (int i : arr) {
            Integer key = Integer.valueOf(i);
            if (freq.containsKey(key)) {
                freq.put(key, freq.get(key) + 1);
            } else {
                freq.put(key, 1);
            }
        }

        SortedSet<Map.Entry<Integer, Integer>> sorted = entriesSortedByValues(freq);
        List<Map.Entry<Integer, Integer>> sortedList = sorted.stream().collect(Collectors.toList());
        System.out.print("start debugging info: ");
        sorted.stream().forEach(e -> System.out.print(e + ","));
        System.out.println("end debugging info");

        // sort the ints that have the same frequency
        List<Integer> sameFreqInts = new ArrayList<>();
        int i = 0;
        for (i = 0; i < sortedList.size() - 1; i++) {
            // same frequency
            if (sortedList.get(i).getValue() == sortedList.get(i + 1).getValue()) {
                sameFreqInts.add(sortedList.get(i).getKey());
            } else {            // different frequency
                if (sameFreqInts.size() > 0) {
                    Collections.sort(sameFreqInts);
                    sameFreqInts.forEach(item -> System.out.println(item));
                    sameFreqInts.clear();
                }

                // repeatedly print the int at frequency times
                for (int j = 0; j < sortedList.get(i).getValue(); j++) {
                    System.out.println(sortedList.get(i).getKey());
                }
            }
        }

        // don't forget the last equal frequency check
        if (sortedList.get(i).getValue() == sortedList.get(i - 1).getValue()) {
            sameFreqInts.add(sortedList.get(i).getKey());
            Collections.sort(sameFreqInts);
            sameFreqInts.forEach(item -> System.out.println(item));
        } else {
            for (int j = 0; j < sortedList.get(i).getValue(); j++) {
                System.out.println(sortedList.get(i).getKey());
            }
        }

    }

    public static double getDistance(Integer x, Integer y) {
        double x0 = Integer.valueOf(x) * Integer.valueOf(x);
        double y0 = Integer.valueOf(y) * Integer.valueOf(y);
        return java.lang.Math.sqrt(x0 + y0);
    }

    public static class PositionDist {
        public List<Integer> position;
        public Double distance;

        public PositionDist(List<Integer> position, Double distance) {
            this.position = position;
            this.distance = distance;
        }
    }

    public static class ListNode {
        int val;
        ListNode next;

        ListNode(int x) {
            val = x;
        }
    }

    public static ListNode addTwoNumbers(ListNode l1, ListNode l2) {
        List<Long> li1 = convertToList(l1);
        List<Long> li2 = convertToList(l2);

        Long sum = calc(li1) + calc(li2);
        ListNode result = buildList(sum);
        while (result != null) {
            System.out.println(result.val);
            result=result.next;
        }

        return result;
    }

    public static Long calc(List<Long> li) {
        Long sum = li.get(0);
        for (int i = 1; i < li.size(); ++i) {
            sum += li.get(i) * (long) java.lang.Math.pow(10, i);
        }

        return sum;
    }

    public static List<Long> convertToList(ListNode l) {
        List<Long> al = new ArrayList<Long>();
        while (l != null) {
            al.add((long)l.val);
            l = l.next;
        }

        return al;
    }

    public static ListNode buildList(Long i) {
        String num = String.valueOf(i);
        StringBuilder input1 = new StringBuilder();
        input1.append(num);
        input1 = input1.reverse();
        ListNode previous = new ListNode(-1);
        ListNode head = previous;
        for (Character ch : input1.toString().toCharArray()) {
            previous.next = new ListNode(Character.getNumericValue(ch));
            previous = previous.next;
        }

        previous.next = null;
        return head.next;
    }

    public static void main(String[] args) {
        ListNode l1 = new ListNode(9);
        ListNode l2 = new ListNode(1);
        l2.next = new ListNode(9);
        l2.next.next = new ListNode(9);
        l2.next.next.next = new ListNode(9);
        l2.next.next.next.next = new ListNode(9);
        l2.next.next.next.next.next = new ListNode(9);
        l2.next.next.next.next.next.next = new ListNode(9);
        l2.next.next.next.next.next.next.next = new ListNode(9);
        l2.next.next.next.next.next.next.next.next = new ListNode(9);
        l2.next.next.next.next.next.next.next.next.next = new ListNode(9);

        System.out.println(addTwoNumbers(l1, l2));
        System.exit(1);


        int totalCrates = 5;
        List<List<Integer>> allLocations = null;
        int truckCapacity = 4;
        List<PositionDist> distances = allLocations.stream().map(coords -> new PositionDist(coords,
                (Double) getDistance(coords.get(0), coords.get(1)))).collect(Collectors.toList());
        distances.sort((d1, d2) -> d1.distance.compareTo(d2.distance));
        List<List<Integer>> pos = distances.stream().limit(truckCapacity).map(dist -> dist.position).collect(Collectors.toList());


        int[] arr1 = new int[]{3, 1, 2, 2, 4};
        customSort(arr1);

        int[] arr2 = new int[]{8, 5, 5, 5, 5, 1, 1, 1, 4, 4};
        customSort(arr2);

        System.exit(1);

        long sum = calculateAmount(new int[]{});
        long sum1 = calculateAmount(null);
        System.out.println("calculated = " + sum);
        System.out.println("calculated = " + sum1);
        getIntArray();
        String t[] = {"a", ""};
    }

    static int[] getIntArray() {
        int i = 3;
        return new int[]{1, 2, i};
    }

    static long calculateAmount(int[] prices) {
        if (prices == null || prices.length == 0) {
            return -1;
        }
        long sum = prices[0];
        java.util.List<Integer> list_prices = java.util.stream.IntStream.of(prices).boxed().collect(java.util.stream.Collectors.toList());

        for (int i = 1; i < prices.length; i++) {
            java.util.List<Integer> list_prices_range = list_prices.subList(0, i);
            int min = java.util.Collections.min(list_prices_range);
            sum += java.lang.Math.max(0, prices[i] - min);
        }

        return sum;
    }

    private boolean flag = true;

    class Inner {
        void test() {
            if (Main.this.flag) {
                int i = Integer.valueOf("4");
            }
        }
    }
}

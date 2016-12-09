package com.dlinkddns.hil;

public class Main {

    public static void main(String[] args) {
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

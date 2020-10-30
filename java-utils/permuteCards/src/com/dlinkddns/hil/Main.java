/*
Problem Statement

    You are given a set of cards. Each card has a string written on the front and a number on the back. The strings on all the cards have the same length. You must choose some of these cards (at least one, possibly all) and place them in a row with the front sides visible, such that the concatenated string is a palindrome
    You are given a list of strings "front" and a list of numbers "back" describing the set of cards you are given. The i-th card has front[i] written on the front and back[i] on the back
    Find the maximum possible score you can achieve with these cards. Score is obtained by summing up all the "front" values that were used
Problem Constraints
    front will contain between 1 and 50 elements, inclusive
    Each element of front will contain between 1 and 50 characters, inclusive
    Each element of front will contain the same number of characters
    Each character in front will be a lowercase letter ('a' - 'z')
    front and back will contain the same number of elements
    Each element of back will be between 1 and 1,000,000, inclusive
Input Format
    Line 1: Comma separated list of front strings
    Line 2: Comma separated list of back numbers

Sample Input
    abc,abc,def,cba,fed
    24,7,63,222,190
Sample Output
    499

Sample Input
    topcoder,redcoder,redocpot
    7,5,3
Sample Output
    10

Sample Input
    rabbit
    1000000
Sample Output
    0
*/
package com.dlinkddns.hil;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class Main {
    public static String frontCSV;
    public static String backCSV;

    public static void main(String[] args) {
        do {
            try {
                readCardsScores();
            } catch (IOException e) {
                e.printStackTrace();
                return;
            }

            if (frontCSV.equals("") || backCSV.equals("")) {
                continue;
            }

            int size = frontCSV.split(",").length;
            int topScore = 0;
            ExecutorService executor = Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors());
            ArrayList<Future<Integer>> futures = new ArrayList<Future<Integer>>();

            for (int i = 1; i <= size; i++) {
                Future<Integer> future = executor.submit(new Permute(i, frontCSV, backCSV));
                futures.add(future);
            }

            for (Future<Integer> f : futures) {
                try {
                    int score = f.get();
                    if (score > topScore) {
                        topScore = score;
                    }
                } catch (InterruptedException e) {
                    e.printStackTrace();
                } catch (ExecutionException e) {
                    e.printStackTrace();
                }
            }

            System.out.println("max score is " + topScore);
            executor.shutdown();
        } while (frontCSV != null && !frontCSV.equals("") && backCSV != null && !backCSV.equals(""));

        System.out.println("returning from Main");
    }

    public static void readCardsScores() throws IOException {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));
        frontCSV = in.readLine();
        backCSV = in.readLine();
    }
}

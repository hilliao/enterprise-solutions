package com.dlinkddns.hil;

import java.util.*;
import java.util.concurrent.Callable;

public class Permute implements Callable<Integer> {
    protected ArrayList<String> front;
    protected ArrayList<Integer> back;
    private int topScore;
    protected int numCards;

    public Permute(int numCards, String frontCSV, String backCSV) {
        this();
        this.numCards = numCards;
        this.setCardsFront(frontCSV);
        this.setCardsBack(backCSV);
    }

    public Permute() {
        this.front = new ArrayList<String>();
        this.back = new ArrayList<Integer>();

        //abc,abc,def,cba,fed
        front.add("abc");
        front.add("abc");
        front.add("def");
        front.add("cba");
        front.add("fed");

        //24,7,63,222,190
        back.add(24);
        back.add(7);
        back.add(63);
        back.add(222);
        back.add(190);

        this.topScore = 0;
    }

    public void setCardsFront(String frontCSV) {
        this.front = new ArrayList<String>(Arrays.asList(frontCSV.split(",")));
    }

    public void setCardsBack(String backCSV) {
        String[] splitBackCSV = backCSV.split(",");
        Integer[] parsed = Arrays.stream(splitBackCSV).mapToInt(Integer::parseInt).boxed().toArray(size -> new Integer[size]);
        this.back = new ArrayList<Integer>(Arrays.asList(parsed));
    }

    @Override
    public Integer call() {
        return this.getTopScoreSelectingNCards(this.numCards);
    }

    public static boolean isPalindrome(String s) {

        for (int i = 0, j = s.length() - 1; i < j; i++, j--) {

            if (s.charAt(i) != s.charAt(j)) {
                return false;
            }
        }

        return true;
    }

    public int getTopScoreSelectingNCards(int numCards) {
        this.topScore = 0;
        calcScore("", this.front, numCards, new ArrayList<Integer>());
        return this.topScore;
    }

    public void calcScore(String palindromeCandidate, ArrayList<String> subFront, int recursionsLeft, ArrayList<Integer> order) {
        if (recursionsLeft > 0) {
            recursionsLeft--;

            for (int i = 0; i < subFront.size(); i++) {
                ArrayList<Integer> clonedOrder = (ArrayList<Integer>) order.clone();
                // find the index of the string from the original front ArrayList
                int indexInFront = this.front.indexOf(subFront.get(i));
                clonedOrder.add(indexInFront);
                ArrayList<String> clonedSubFront = (ArrayList<String>) subFront.clone();
                String selected = clonedSubFront.remove(i);
                calcScore(palindromeCandidate + selected, clonedSubFront, recursionsLeft, clonedOrder);
            }
        } else {
            // add all the values of the cards if the cards form a Palindrome
            if (isPalindrome(palindromeCandidate)) {
                int score = 0;

                for (int i : order) {
                    score += back.get(i);
                }

                if (score > this.topScore) {
                    this.topScore = score;
                }
            }
        }
    }
}

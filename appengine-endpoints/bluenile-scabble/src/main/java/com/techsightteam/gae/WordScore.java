package com.techsightteam.gae;

import java.util.ArrayList;
import java.util.List;

public class WordScore {
    public List<String> words;
    public List<Integer> scores;

    public WordScore(List<String> words) {
        this.words = words;
        this.scores = new ArrayList<>();
        words.stream().forEach(word -> scores.add(WordManager.getPointsOf(word)));
    }
}

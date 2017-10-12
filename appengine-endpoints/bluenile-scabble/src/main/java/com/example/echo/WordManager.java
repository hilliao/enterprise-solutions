package com.example.echo;

import com.google.appengine.repackaged.com.google.common.base.Pair;

import java.util.*;
import java.util.stream.Stream;

public class WordManager {
    protected List<Pair<String, Map<Character, Integer>>> wordCharMaps;

    public static Map<Character, Integer> analyzeWord(String word) {
        Map<Character, Integer> charMap = new HashMap<>();
        Stream<Character> characterStream = word.chars().mapToObj(i -> (char) i);
        characterStream.forEach(ch -> charMap.compute(ch, (k, v) -> v == null ? 1 : v + 1));
        return charMap;
    }

    public WordManager(String words) {
        wordCharMaps = new ArrayList<>();
        String lines[] = words.split("\r?\n");
        Arrays.stream(lines).forEach(word -> wordCharMaps.add(Pair.of(word, analyzeWord(word))));
    }

    boolean isValid(String word) {
        return true;
    }
}
package com.techsightteam.gae;

import org.apache.commons.lang3.StringUtils;
import org.apache.commons.lang3.tuple.Pair;

import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Manage scrabble dictionary, character maps of dictionary words, get words from letters
 * Sort words by points of letters, memory intensive on wordCharMaps
 */
public class WordManager {
    protected List<Pair<String, Map<Character, Integer>>> wordCharMaps;
    private static Map<Character, Integer> pointsMap;

    /**
     * @param word the word to analyze
     * @return a map of the word's characters as key, its character counts as value
     */
    public static Map<Character, Integer> analyzeWord(String word) {
        if (StringUtils.isBlank(word)) {
            return Collections.emptyMap();
        }

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

    /**
     * @param letters a set of characters to find matching words
     * @return words in the dictionary where each character is used less than or equal to how many times the character
     * is used in @param letters. The resulting words are sorted by word's weight defined by character's points.
     */
    public List<String> getWordsFrom(String letters) {
        if (StringUtils.isBlank(letters)) {
            return Collections.emptyList();
        }

        Map<Character, Integer> userInputCharMap = analyzeWord(letters);

        // gather words that contain the letters user specified
        List<Pair<String, Map<Character, Integer>>> dictWords = this.wordCharMaps.parallelStream()
                .filter(wordCharMap -> userInputCharMap.keySet().containsAll(wordCharMap.getRight().keySet()))
                .collect(Collectors.toList());

        // remove those using letters more times than the letter count user specified
        List<String> filteredWords = dictWords.parallelStream().filter(word -> {
            for (Map.Entry<Character, Integer> dictWordCharMap : word.getRight().entrySet()) {
                // check if the word uses more characters than the count in the letters user specified
                if (userInputCharMap.get(dictWordCharMap.getKey()) < dictWordCharMap.getValue()) {
                    return false;
                }
            }
            return true;
        }).map(Pair::getLeft).collect(Collectors.toList());

//         filteredWords.sort((w1, w2)-> getPointsOf(w1)-getPointsOf(w2));
        filteredWords.sort(Comparator.comparingInt(word -> -1 * getPointsOf(word)));
        return filteredWords;
    }

    /**
     * @return a fixed mapping from letters a to z to their points with lazy initialization pattern
     */
    public static synchronized Map<Character, Integer> getA2ZPoints() {
        if (WordManager.pointsMap != null) {
            return WordManager.pointsMap;
        }

        HashMap<Character, Integer> pointsMap = new HashMap<>();
        Stream.of('a', 'e', 'i', 'l', 'n', 'o', 'r', 's', 't', 'u').forEach(ch -> pointsMap.put(ch, 1));
        Stream.of('d', 'g').forEach(ch -> pointsMap.put(ch, 2));
        Stream.of('b', 'c', 'm', 'p').forEach(ch -> pointsMap.put(ch, 3));
        Stream.of('f', 'h', 'v', 'w', 'y').forEach(ch -> pointsMap.put(ch, 4));
        pointsMap.put('k', 5);
        Stream.of('j', 'x').forEach(ch -> pointsMap.put(ch, 8));
        Stream.of('q', 'z').forEach(ch -> pointsMap.put(ch, 10));

        WordManager.pointsMap = pointsMap;
        return pointsMap;
    }

    /**
     * @param word which word to calculate points from
     * @return the points of @param word
     */
    public static Integer getPointsOf(String word) {
        Integer points = 0;
        if (StringUtils.isBlank(word)) {
            return 0;
        }

        for (Character ch : word.toCharArray()) {
            points += getA2ZPoints().get(ch);
        }

        return points;
    }
}
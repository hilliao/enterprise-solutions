package com.techsightteam.gae;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class WordManagerTest {
    WordManager wordManager;

    @BeforeEach
    void setUp() {
        wordManager = new WordManager("at\nthe\nhas\nas");
    }

    @AfterEach
    void tearDown() {
    }

    @Test
    void analyzeWord() {
        Map<Character, Integer> analysis = WordManager.analyzeWord("this");
        assertEquals(4, analysis.size());
        assertEquals(Integer.valueOf(1), analysis.get('t'));
        assertNull(analysis.get('f'));
    }

    @Test
    void getWordsFrom() {
        List<String> words = wordManager.getWordsFrom("test");
        assertEquals(0, words.size());
        words = wordManager.getWordsFrom("a test");
        assertEquals(2, words.size());
    }

    @Test
    void getPointsOf() {
        Integer points = WordManager.getPointsOf("antidisestablishmenatarianism");
        assertEquals(39, (int) points);
    }
}
package com.dlinkddns.hil;

import java.io.Console;

public class Main {

    public static void main(String[] args) {
        int cores = Runtime.getRuntime().availableProcessors();
        System.out.println("processor core count " + cores);
    }
}

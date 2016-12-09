package com.dlinkddns.hil;

import com.google.inject.Guice;
import com.google.inject.Injector;

import java.util.concurrent.*;

public class app {

    public static void main(String[] args) throws InterruptedException, ExecutionException {
        System.out.println("fake maven project running!");
        Injector injector = Guice.createInjector(new GuiceModule());
        PaymentProvider paymentProvider = injector.getInstance(PaymentProvider.class);
        Callable<Integer> sendMoney = () -> {
            return paymentProvider.sendMoneyTo(2745.38, "pohsiang09@gmail.com");
        };
        ExecutorService es = Executors.newFixedThreadPool(4);
        Future<Integer> result = es.submit(sendMoney);
        Thread.sleep(1000);
        int r = result.get();
        System.out.println("send money resulted in " + r);
    }

    static int[] getIntArray() {
        int i = 3;
        return new int[]{1, 2, i};
    }
}

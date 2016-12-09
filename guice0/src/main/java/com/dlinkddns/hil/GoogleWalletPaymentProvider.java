package com.dlinkddns.hil;

// https://developers.google.com/android-pay/tutorial
public class GoogleWalletPaymentProvider implements PaymentProvider {

    @Override
    public int sendMoneyTo(double howMuch, String email) {
        System.out.println("you paid " + howMuch + " to " + email);
        return 200;
    }
}

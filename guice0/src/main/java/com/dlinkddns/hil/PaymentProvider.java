package com.dlinkddns.hil;

// happy humming bird payment provider interface
public interface PaymentProvider {
    int sendMoneyTo(double howMuch, String email);
}

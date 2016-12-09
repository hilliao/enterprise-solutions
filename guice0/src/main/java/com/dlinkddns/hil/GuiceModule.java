package com.dlinkddns.hil;

import com.google.inject.AbstractModule;

// https://github.com/google/guice/wiki/GettingStarted
public class GuiceModule extends AbstractModule {
    @Override
    protected void configure() {
        bind(PaymentProvider.class).to(GoogleWalletPaymentProvider.class);
    }
}
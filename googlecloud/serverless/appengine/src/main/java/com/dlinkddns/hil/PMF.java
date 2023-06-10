package com.dlinkddns.hil;

import javax.jdo.JDOHelper;
import javax.jdo.PersistenceManagerFactory;

// ensures single instance of PersistenceManagerFactory
public final class PMF {
    private static final PersistenceManagerFactory pmfInstance =
            JDOHelper.getPersistenceManagerFactory(Constants.PersistenceManagerFactoryName);

    private PMF() {}

    public static PersistenceManagerFactory get() {
        return pmfInstance;
    }
}
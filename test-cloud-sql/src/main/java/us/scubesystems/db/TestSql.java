package us.scubesystems.db;

/*
 connection pool sample code from https://cloud.google.com/sql/docs/postgres/manage-connections
 See https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory for details.
 applicationContext.xml example at https://stackoverflow.com/questions/57408664/hikaricp-google-cloud-sql-jdbc-socket-factory-cloudsqlinstance-property-not-set
 */

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class TestSql {
    public static String password = "Cloud SQL password";
    public static String SqlConnectionName = "car-repair-warranty:us-central1:psql-dev";

    public static void main(String[] args) throws SQLException {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(String.format("jdbc:postgresql:///%s", "patient")); // patient is the database
        config.setUsername("postgres"); // user should not be root or postgres
        config.setPassword(password); // bad to have clear password in code

        config.addDataSourceProperty("socketFactory", "com.google.cloud.sql.postgres.SocketFactory");
        config.addDataSourceProperty("cloudSqlInstance", SqlConnectionName);
        config.setConnectionTestQuery("SELECT 1");
        String testQuery = config.getConnectionTestQuery();

        // Initialize the connection pool using the configuration object.
        DataSource pool = new HikariDataSource(config);
        try (Connection conn = pool.getConnection()) {
            String stmt = "SELECT 2;";
            try (PreparedStatement createTableStatement = conn.prepareStatement(stmt);) {
                createTableStatement.execute();
            }
        }
        System.out.println("Executed " + testQuery);
    }
}

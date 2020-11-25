package com.techsightteam;

import io.opencensus.exporter.trace.stackdriver.StackdriverTraceConfiguration;
import io.opencensus.exporter.trace.stackdriver.StackdriverTraceExporter;
import org.springframework.boot.SpringApplication;

import java.io.IOException;

@org.springframework.boot.autoconfigure.SpringBootApplication
public class MainApplication {

    public static void main(String[] args) throws IOException {
        if (System.getenv("LOCAL_DEBUG_GCP_PROJECT") != null) {
            createAndRegisterGoogleCloudPlatform(System.getenv("LOCAL_DEBUG_GCP_PROJECT"));
        } else {
            StackdriverTraceExporter.createAndRegister(StackdriverTraceConfiguration.builder().build());
        }
        SpringApplication.run(MainApplication.class, args);
    }

    // ref: https://cloud.google.com/trace/docs/setup/java#registering_the_exporter
    public static void createAndRegisterGoogleCloudPlatform(String projectId) throws IOException {
        StackdriverTraceExporter.createAndRegister(
                StackdriverTraceConfiguration.builder().setProjectId(projectId).build());
    }
}

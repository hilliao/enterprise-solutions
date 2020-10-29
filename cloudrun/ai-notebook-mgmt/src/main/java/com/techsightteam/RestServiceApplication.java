package com.techsightteam;

import io.opencensus.exporter.trace.stackdriver.StackdriverTraceConfiguration;
import io.opencensus.exporter.trace.stackdriver.StackdriverTraceExporter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import java.io.IOException;

@SpringBootApplication
public class RestServiceApplication {

    public static void main(String[] args) throws IOException {
        if (System.getenv("LOCAL_DEBUG_GCP_PROJECT") != null) {
            createAndRegisterGoogleCloudPlatform(System.getenv("LOCAL_DEBUG_GCP_PROJECT"));
        } else {
            StackdriverTraceExporter.createAndRegister(StackdriverTraceConfiguration.builder().build());
        }
        SpringApplication.run(RestServiceApplication.class, args);
    }

    public static void createAndRegisterGoogleCloudPlatform(String projectId) throws IOException {
        StackdriverTraceExporter.createAndRegister(
                StackdriverTraceConfiguration.builder().setProjectId(projectId).build());
    }
}

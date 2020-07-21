package com.intient.internal;

import io.opencensus.common.Scope;
import io.opencensus.trace.Tracer;
import io.opencensus.trace.Tracing;
import io.opencensus.trace.samplers.Samplers;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicLong;

import com.google.cloud.MonitoredResource;
import com.google.cloud.logging.LogEntry;
import com.google.cloud.logging.Logging;
import com.google.cloud.logging.LoggingOptions;
import com.google.cloud.logging.Payload.StringPayload;
import com.google.cloud.logging.Severity;

import java.util.Collections;


@RestController
public class CreateAINotebook {
    private static final Tracer tracer = Tracing.getTracer();
    private static final String template = "Slept %s seconds;";
    private final AtomicLong counter = new AtomicLong();

    @GetMapping("/sleep")
    public SleepTracked getSleep(@RequestParam(value = "seconds", defaultValue = "1") String sec)
            throws InterruptedException {
        try (Scope ss = tracer.spanBuilder("sleep").setSampler(Samplers.alwaysSample()).startScopedSpan()) {
            Thread.sleep(1000 * Integer.parseInt(sec));
            tracer.getCurrentSpan().addAnnotation("waking");
        }

        // test Google cloud logging severity
        Logging logging = LoggingOptions.getDefaultInstance().getService();
        String logName = "test-logging";
        String text = "test logging SeverityEnum of slept " + sec + " seconds";
        LogEntry logError = LogEntry.newBuilder(StringPayload.of(
                text.replace("SeverityEnum", "ERROR")))
                .setSeverity(Severity.ERROR)
                .setLogName(logName)
                .setResource(MonitoredResource.newBuilder("global").build())
                .build();
        LogEntry logInfo = LogEntry.newBuilder(StringPayload.of(
                text.replace("SeverityEnum", "INFO")))
                .setSeverity(Severity.INFO)
                .setLogName(logName)
                .setResource(MonitoredResource.newBuilder("global").build())
                .build();
        LogEntry logWarning = LogEntry.newBuilder(StringPayload.of(
                text.replace("SeverityEnum", "WARNING")))
                .setSeverity(Severity.WARNING)
                .setLogName(logName)
                .setResource(MonitoredResource.newBuilder("global").build())
                .build();
        LogEntry logDebug = LogEntry.newBuilder(StringPayload.of(
                text.replace("SeverityEnum", "DEBUG")))
                .setSeverity(Severity.DEBUG)
                .setLogName(logName)
                .setResource(MonitoredResource.newBuilder("global").build())
                .build();
        // Writes the log entry asynchronously
        logging.write(Collections.singleton(logInfo));
        logging.write(Collections.singleton(logDebug));
        logging.write(Collections.singleton(logWarning));
        logging.write(Collections.singleton(logError));

        return new SleepTracked(counter.incrementAndGet(), String.format(template, sec));
    }

    @PostMapping("/createAINotebook")
    public ResponseEntity addSleep(@RequestHeader(name = "Authorization", required = true) String Bearer,
                                   @RequestBody AINotebookReq req) throws IOException {
        Response r;
        try (Scope ss = tracer.spanBuilder("CreateAINotebook").setSampler(Samplers.alwaysSample()).startScopedSpan()) {
            r = this.createAiNotebook(
                    Bearer,
                    req.getProjectId(),
                    req.getInstanceName(),
                    req.getVPCProjectId(),
                    req.getVPCName(),
                    req.getRegion(),
                    req.getZone(),
                    req.getSubnetName());
        }
        return new ResponseEntity(r.body().string(), HttpStatus.valueOf(r.code()));
    }

    public Response createAiNotebook(
            final String access_token,
            final String projectId,
            final String instanceName,
            final String VPCProjectId,
            final String VPCName,
            final String region,
            final String zone,
            final String subnetName) throws IOException {
        OkHttpClient client = new OkHttpClient();

        MediaType mediaType = MediaType.parse("application/json");
        String bodyJson = "{\"network\":\"projects/" + VPCProjectId + "/global/networks/" + VPCName + "\",\"subnet\":\"projects/" + VPCProjectId + "/regions/" + region + "/subnetworks/" + subnetName + "\",\"noProxyAccess\":false,\"installGpuDriver\":false,\"machineType\":\"n1-standard-1\",\"metadata\":{\"framework\":\"TensorFlow:2.2\"},\"bootDiskType\":\"DISK_TYPE_UNSPECIFIED\",\"bootDiskSizeGb\":\"100\",\"noPublicIp\":false,\"serviceAccount\":\"default\",\"vmImage\":{\"project\":\"deeplearning-platform-release\",\"imageFamily\":\"tf2-2-2-cu101-notebooks\"}}";
        okhttp3.RequestBody body = okhttp3.RequestBody.create(bodyJson, mediaType);
        String url = "https://notebooks.googleapis.com/v1beta1/projects/" + projectId + "/locations/" + zone + "/instances?instanceId=" + instanceName;
        Request request = new Request.Builder()
                .url(url)
                .post(body)
                .addHeader("authorization", "Bearer " + access_token)
                .addHeader("content-type", "application/json")
                .build();

        tracer.getCurrentSpan().addAnnotation("Calling " + url);
        Response response = client.newCall(request).execute();
        return response;
    }
}

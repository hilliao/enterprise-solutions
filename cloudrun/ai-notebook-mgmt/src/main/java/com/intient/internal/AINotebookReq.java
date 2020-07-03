package com.intient.internal;

public class AINotebookReq {

    private final String projectId;
    private final String instanceName;
    private final String VPCProjectId;
    private final String VPCName;
    private final String region;
    private final String zone;
    private final String subnetName;

    public AINotebookReq(String projectId,
                         String VPCProjectId,
                         String VPCName,
                         String region,
                         String zone,
                         String subnetName,
                         String instanceName) {
        this.projectId = projectId;
        this.instanceName = instanceName;
        this.VPCProjectId = VPCProjectId;
        this.VPCName = VPCName;
        this.region = region;
        this.zone = zone;
        this.subnetName = subnetName;
    }

    public String getProjectId() {
        return projectId;
    }

    public String getVPCProjectId() {
        return VPCProjectId;
    }

    public String getVPCName() {
        return VPCName;
    }

    public String getRegion() {
        return region;
    }

    public String getZone() {
        return zone;
    }

    public String getSubnetName() {
        return subnetName;
    }

    public String getInstanceName() {
        return instanceName;
    }
}

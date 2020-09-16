package com.intient.internal;

public class AINotebookReq {

    private final String projectId;
    private final String instanceName;
    private final String VPCProjectId;
    private final String VPCName;
    private final String region;
    private final String zone;
    private final String subnetName;
    private final String serviceAccount;
    private final String machineType;
    private final String imageFamily;
    private final String framework;
    private final Boolean installGpuDriver;
    private final Boolean publicIp;

    public AINotebookReq(String projectId,
                         String VPCProjectId,
                         String VPCName,
                         String region,
                         String zone,
                         String subnetName,
                         String instanceName,
                         String serviceAccount,
                         String machineType,
                         String imageFamily,
                         String framework,
                         Boolean installGpuDriver,
                         Boolean publicIp
    ) {
        this.projectId = projectId;
        this.instanceName = instanceName;
        this.VPCProjectId = VPCProjectId;
        this.VPCName = VPCName;
        this.region = region;
        this.zone = zone;
        this.subnetName = subnetName;
        this.serviceAccount = serviceAccount;
        this.machineType = machineType;
        this.imageFamily = imageFamily;
        this.framework = framework;
        this.installGpuDriver = installGpuDriver;
        this.publicIp = publicIp;
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

    public String getServiceAccount() {
        return serviceAccount;
    }

    public String getMachineType() {
        return machineType;
    }

    public String getImageFamily() {
        return imageFamily;
    }

    public String getFramework() {
        return framework;
    }

    public Boolean getInstallGpuDriver() {
        return installGpuDriver;
    }

    public Boolean getPublicIp() {
        return publicIp;
    }

    public String getInstanceName() {
        return instanceName;
    }
}

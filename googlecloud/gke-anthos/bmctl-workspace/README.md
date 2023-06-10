# Install Anthos Clusters on KVM

## Prerequisites
Please review [Prerequisites](https://cloud.google.com/anthos/clusters/docs/bare-metal/latest/installing/install-prereq).
I followed [installing KVM on Ubuntu](https://www.fosslinux.com/92564/how-to-install-kvm-on-ubuntu.htm) 22.04 and created a VM
with 2 CPUs and 4 GB of RAM. That was the minimal requirements for Ubuntu 20.04 edge profile.
Set the VM to use static IP and test it can access the Internet. I also reserved IPs
less than 192.168.2.100 for the cluster node and control plane VIP. You may do so with your network's router that
allocates IPs based on DHCP server configurations. The VM on KVM needs to be visible to the host's network. 
See the netplan bridges: `br0` configuration in the mentioned KVM installation documentation.

## Create a standalone cluster
`bmctl` [command needs to be downloaded](https://cloud.google.com/anthos/clusters/docs/bare-metal/latest/downloads)
and working to generate the cluster config yaml file.
I follow the steps to [create a standalone cluster](https://cloud.google.com/anthos/clusters/docs/bare-metal/latest/installing/creating-clusters/standalone-cluster-creation#sample_standalone_cluster_configurations).
I recommend creating a [new SSH key pair](https://cloud.google.com/compute/docs/connect/create-ssh-keys#create_an_ssh_key_pair)
without using existing ones. Put the private and public key under the folder `bmctl-workspace`.
Copy the public key to the root user on the target VM. It was not clearly documented but the installation will
create a SSH session on the target VM as root. The name of the cluster you specify is used to create a folder and the yaml
file for the cluster configurations. For example, my configuration file is 

> threadripper-kvm-2cpu/threadripper-kvm-2cpu.yaml

### Edit the configuration file
The mentioned installation documentation covers values to edit in the configuration file. I'm addressing 
why I set to certain values here.

```yaml
spec:
  type: standalone
  profile: edge
---
  controlPlane:
    nodePoolSpec:
      nodes:
      # Control plane node pools only contains a single host as that's the VM on KVM.
      - address: 192.168.2.10
  # Cluster networking configuration
  clusterNetwork:
    # /18 is the smallest IP range. Do not allocate a range that conflicts with the host's network (192.168.2.*)
    pods:
      cidrBlocks:
      - 192.168.64.0/18
    # /24 only gives 255 service IPs
    services:
      cidrBlocks:
      - 192.168.128.0/24
  loadBalancer:
    vips:
      # the IP will be in kubeconfig; kubectl command will connect to it.
      controlPlaneVIP: 192.168.2.50
      # reserve another IP for Kubernetes Ingress.
      ingressVIP: 192.168.2.51
    addressPools:
      - name: pool1
        addresses:
        # There's only 1 node in the standalone cluster. So 1 or 2 IPs are enough.
        - 192.168.2.51-192.168.2.52
```

### Errors encountered

I had [Gnome Encfs installed](https://sites.google.com/site/installationubuntu/security/encfs-in-ubuntu?pli=1) and put
the bmctl-workspace folder in it. Installation would fail with the following error:
```commandline
Error creating cluster: create kind cluster failed: error creating bootstrap cluster: command 
"docker run --name bmctl-control-plane --hostname bmctl-control-plane --label io.x-k8s.kind.role=control-plane 
--privileged --security-opt seccomp=unconfined --security-opt apparmor=unconfined --tmpfs /tmp --tmpfs /run 
--volume /var --volume /lib/modules:/lib/modules:ro -e KIND_EXPERIMENTAL_CONTAINERD_SNAPSHOTTER --detach --tty 
--label io.x-k8s.kind.cluster=bmctl --net kind --restart=on-failure:1 --init=false 
--volume=/home/hil/Encfs/confidential/googlecloud.fr/bmctl-workspace/config.toml:/etc/containerd/config.toml 
--publish=127.0.0.1:38065:6443/TCP 
-e KUBECONFIG=/etc/kubernetes/admin.conf gcr.io/anthos-baremetal-release/kindest/node:v0.17.0-gke.22-v1.25.5-gke.2000"
 failed with error: exit status 125
```
It took me a while to figure out the cause was Encfs. I moved the folder from Encfs to ~/Documents/ and installation
succeeded.

Looking at my logs, I guess installation started at 1:26pm and ended at 2:12pm. That's about 48 minutes.
My allocated 2 CPUs are AMD Ryzen Threadripper 3945wx and the VM's disk is Samsung NVMe M.2 pro 980.

### Start the installation

Once you start executing the installation command `bmctl create cluster -c threadripper-kvm-2cpu`, the logs are piped
to the log file stated on the next line. 

> Please check the logs at bmctl-workspace/threadripper-kvm-2cpu/log/create-cluster-20230422-134628/create-cluster.log

If there was no error but the message below at the end, the installation probably succeeded:
```commandline
Waiting for cluster API provider to install in the created admin cluster OK
[2023-04-22 14:08:26-0700] Moving admin cluster resources to the created admin cluster
[2023-04-22 14:08:29-0700] Waiting for node update jobs to finish OK
[2023-04-22 14:12:39-0700] Flushing logs... OK
[2023-04-22 14:12:39-0700] Deleting bootstrap cluster... OK
```
You can find the kubeconfig generated at `$CLUSTER_NAME/$CLUSTER_NAME-kubeconfig`
> threadripper-kvm-2cpu/threadripper-kvm-2cpu-kubeconfig

Try some kubectl commands with `kubectl --kubeconfig` command to test the cluster.

### Post installation
Follow the guide to [register the cluster in Cloud Console](https://cloud.google.com/anthos/identity/setup/bearer-token-auth).
Some commands are imperative. I created declarative yaml files at `yaml/iam/` You may apply them in the same order
as what's in the mentioned documentation.
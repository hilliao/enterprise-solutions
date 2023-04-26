# CPU Benchmark result contest in simulated containerized workloads 
The tutorial is to simulate enterprise workloads in a containerized environment. Current benchmark software runs on
bare metal to assess the CPU's compute power. However, when a corporation's IT department wants to identify
the hardware specifications to simulate running their existing applications in Kubernetes,
the CPU benchmark software may not provide the most accurate results. Docker runtime has a feature to limit
CPUs and memory allocated to containers which is very similar to Kubernetes' container resource limits on
CPUs and memory. Multiple tests were executed to compare between AMD and Apple's CPUs on Docker and Kubernetes.

## Commands to create a docker container with limits on CPUs and memory
Assume you have configured docker on Ubuntu 22.10 on a AMD64 computer. My hardware specs are just an example.
* AMD Ryzen™ Threadripper™ PRO 3945WX
* Lenovo Thinkstation P620
* Windowing System: Wayland
* GPU: NVidia Quadro T1000
* Disk: Samsung MZVL2512HCJQ-00BL7
* Memory: 32 GiB ECC 3200Mhz

Install the latest docker runtime and allow the current user to execute docker commands.
Execute the following commands to create a docker container with the given numbers of CPUs and memory.
I assume the benchmark software requires less than 512 MiB of memory.
You can adjust the following variables to simulate your deployed workloads.
* NUM_CPUs
* MB_MEMORY

```commandline
export NUM_CPUs=4
export MB_MEMORY=512
export CONTAINER_NAME=gcloud-${NUM_CPUs}cpus
docker run --name $CONTAINER_NAME -d --cpus=$NUM_CPUs --memory=${MB_MEMORY}m gcr.io/google.com/cloudsdktool/cloud-sdk:latest sleep infinity
docker exec -it $CONTAINER_NAME bash
```

The last line above should get you into the container's bash shell.
## Commands to run benchmark software in the container
Execute the following commands in the container
to run the benchmark.
```commandline
apt update && \
apt install -y htop wget unzip libncurses5 curl && \
wget https://www.passmark.com/downloads/pt_linux_x64.zip && \
unzip pt_linux_x64.zip && \
PerformanceTest/pt_linux_x64 -i 1 -d 1 -r 1 -debug && \
cat results_cpu.yml
```

The last line above should output the benchmark results. Here's [the command line arguments](https://www.passmark.com/support/pt_linux_faq.php):

> -p [1-256]: Number of Test Processes to run. Setting more test threads than your system supports will force test duration to Very Long.

> -i [1-100]: Number of Test Iterations to run

> -d [1-4]: [Short, Medium, Long, Very Long]

> -r [1-3]: [CPU only, Memory only, All tests] Autorun tests and export scores to [results_cpu.yml, results_memory.yml, results_all.yml]

> -debug: PerformanceTest will output debug information to debug.log file. Upload is disabled in debug mode since debugging can affect scores.

## Remove the container
0. Execute the following commands to leave the container's bash:
`exit`
1. Execute the following commands to stop and remove the container:
`docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME`

# Interpret the benchmark result
The passmark software has published results for different type of operations.
The top 2 are integer and floating point math. For example, click [AMD Ryzen 5 7600](https://www.cpubenchmark.net/cpu.php?cpu=AMD+Ryzen+5+7600&id=5172).
You can compare the results from the container with the published results. Keep in mind that the results
in the containers are not the same as the published results
because the CPU and memory constraints were set in the container.

## Example results running in a Docker container on AMD
Executing the `docker run` command above, the passmark benchmark results running on the mentioned 
AMD Ryzen™ Threadripper™ PRO 3945WX workstation uses the command
to start a docker container with vCPU limit set to 4, memory limit set to 512 MiB.

### AMD threadripper Docker Passmark.yaml
```yaml
Results:
  Results Complete: true
  NumTestProcesses: 24
  CPU_INTEGER_MATH: 15857.092666666671
  CPU_FLOATINGPOINT_MATH: 9008.7839135014947
  CPU_PRIME: 26.546624360654135
  CPU_SORTING: 0
  CPU_ENCRYPTION: 5465.7904874711085
  CPU_COMPRESSION: 80428.910400515917
  CPU_SINGLETHREAD: 2676.5368618084131
  CPU_PHYSICS: 0
  CPU_MATRIX_MULT_SSE: 4862.2750485384295
  CPU_mm: 476.11308107900862
  CPU_sse: 2181.0554754493596
  CPU_fma: 6936.3564039774355
  CPU_avx: 5469.4132661884951
  CPU_avx512: 0
  m_CPU_enc_SHA: 7635385602.2269716
  m_CPU_enc_AES: 5474155663.7226439
  m_CPU_enc_ECDSA: 4084348912.621902
```

## Example result running on a container on Apple MacMini M2 with 4 CPUs
Compared to the latest Apple silicon M2, the results are drastically different from running the benchmark on bare metal.
Key performance metrics show large scale degradation for the following metric categories. The primary reason is that
the docker container is running as emulated x86.
`uname -a` returns `Linux 1e8c0cf3f9f8 5.15.49-linuxkit #1 SMP PREEMPT Tue Sep 13 07:51:32 UTC 2022 x86_64 GNU/Linux`

### WINNER: AMD

* CPU_INTEGER_MATH: 12134 is a quarter less than AMD's 15857
* CPU_FLOATINGPOINT_MATH: 745 is merely 8% of what AMD's 9008
* CPU_PRIME: 36 is the bright spot, making it 36% higher than AMD's 26.5
* CPU_ENCRYPTION: 309 is shockingly 20 times worse compared to AMD's 5465
* CPU_COMPRESSION: 26812 is 1/3 of AMD's 80428
* CPU_SINGLETHREAD: 557 is 5 times worse than AMD's 2676
* CPU_MATRIX_MULT_SSE: 35 is basically a joke compared to AMD's 4862. It's not even 1%. 
* Encoding and Encryption benchmark scores combined are only half compared to AMD: (238986041+529282543+205998641)/(7635385602+5474155663+4084348912) => 0.05666357147629465

Average metrics comparison: (12134/15857+745/9008+36/26.5+309/5465+26812/80428+557/2676+35/4862+238986041/7635385602+529282543/5474155663+205998641/4084348912)/10
=> 0.299. Overall, the average of metrics shows Apple M2 is **70%** worse than AMD's 

### Mac Mini M2 Docker Passmark.yaml
```yaml
Results:
  Results Complete: true
  NumTestProcesses: 4
  CPU_INTEGER_MATH: 12134.326000000001
  CPU_FLOATINGPOINT_MATH: 745.50531886921135
  CPU_PRIME: 35.977364488597054
  CPU_SORTING: 2905.9332118328389
  CPU_ENCRYPTION: 309.71121022332096
  CPU_COMPRESSION: 26812.821874695481
  CPU_SINGLETHREAD: 557.25375462998431
  CPU_PHYSICS: 101.14048516794189
  CPU_MATRIX_MULT_SSE: 35.360804104862211
  CPU_mm: 35.360804104862211
  CPU_sse: 0
  CPU_fma: 0
  CPU_avx: 0
  CPU_avx512: 0
  m_CPU_enc_SHA: 238986041.19325435
  m_CPU_enc_AES: 529282543.03301334
  m_CPU_enc_ECDSA: 205998641.68711933
```

## Benchmark results in Kubernetes between AMD and Apple M2 with 4 CPUs
The Kubernetes cluster used on AMD Ryzen Threadripper is [Anthos clusters on Bare metal](https://cloud.google.com/anthos/clusters/docs/bare-metal/latest)
which is a Google Cloud product. The Kubernetes cluster used on Apple M2 is [MicroK8s](https://microk8s.io/).
The benchmark results are quite interesting as the Linux container used on Apple M2 is ARM64 based and native to the processor.
I am making an average on the ratio between the mectrics from the 2 processors to design the score.
The Anthos cluster has 8 CPUs allocated to it in KVM. The Microk8s cluster had 6 CPUs allocated to it in
[multipass](https://multipass.run/).

### WINNER: AMD

* Score of the top 9 metrics from CPU_INTEGER_MATH to CPU_MATRIX_MULT_SSE: (18913/21294+31787/15550+61/67+16528/12563+912/5427+33929/85259+3219/2437+1109/1023+6372/7801)/9
=> 0.9940215056724604 shows the Apple M2 is about **.5%** worse than AMD
* Score of the top 9 metrics plus the 3 m_CPU_enc_* metrics: (18913/21294+31787/15550+61/67+16528/12563+912/5427+33929/85259+3219/2437+1109/1023+6372/7801+1545555081/7554238459+409409970/5073027587+915243407/4446784197)/12
=> 0.7864427225740651 shows significant degradation in performance. Apple M2 is **22%** worse than AMD.

### Mac Mini M2 microk8s passmark.yaml
running on pod ubuntu.yaml as gcloud.yaml caused crash loop.
```yaml
  CPU_INTEGER_MATH: 18913.772833333333
  CPU_FLOATINGPOINT_MATH: 31787.635753181163
  CPU_PRIME: 61.139391035153288
  CPU_SORTING: 16528.853220845605
  CPU_ENCRYPTION: 912.41469708545378
  CPU_COMPRESSION: 33929.191349056877
  CPU_SINGLETHREAD: 3219.4068318118771
  CPU_PHYSICS: 1109.5974036046828
  CPU_MATRIX_MULT_SSE: 6372.4983884131889
  CPU_mm: 1152.9657095342102
  CPU_sse: 4616.6193208622017
  CPU_fma: 8128.3774559641752
  CPU_avx: 0
  CPU_avx512: 0
  m_CPU_enc_SHA: 1545555081.7907987
  m_CPU_enc_AES: 409409970.68442398
  m_CPU_enc_ECDSA: 915243407.75800788
```

### AMD Threadripper Anthos K8s passmark.yaml
running on pod gcloud.yaml
```yaml
Results:
  Results Complete: true
  NumTestProcesses: 8
  CPU_INTEGER_MATH: 21294.402833333334
  CPU_FLOATINGPOINT_MATH: 15550.762873294345
  CPU_PRIME: 66.96481227570203
  CPU_SORTING: 12563.285423741843
  CPU_ENCRYPTION: 5427.6943984052141
  CPU_COMPRESSION: 85259.102123164077
  CPU_SINGLETHREAD: 2437.3673388481893
  CPU_PHYSICS: 1023.2969898574404
  CPU_MATRIX_MULT_SSE: 7801.7738157035983
  CPU_mm: 949.51738450057883
  CPU_sse: 3717.052978099593
  CPU_fma: 11386.89534272076
  CPU_avx: 8301.3731262904439
  CPU_avx512: 0
  m_CPU_enc_SHA: 7554238459.3581209
  m_CPU_enc_AES: 5073027587.4781075
  m_CPU_enc_ECDSA: 4446784197.6702099
```

It's uncertain if the higher end Apple M2 processors would make a difference as the tests were executed in pods with
CPU and memory resource limits. One thing for certain is that Apple M2 processors are definitely not designed for
enterprise workloads. A 3 years newer processor should not be 22% worse than AMD's CPU from 2020.

## Stress certain pods to simulate a busy Kubernetes cluster
To simulate CPU heavy workloads in a container or a pod, install and execute the following packages 
in the container. You can have deployments that run the stress test while you benchmark other pods for a more
realistic simulation.
```commandline
apt install s-tui && apt install stress && s-tui
```
Change the mode from monitor to stress to start generating load on CPUs.
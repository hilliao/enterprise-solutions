# Execute CPU benchmark in a CPU and memory limited docker container
The tutorial is to simulate enterprise workloads in a containerized environment. Current benchmark software runs on
bare metal to assess the CPU's compute power. However, when a corporation's IT department wants to identify
the hardware specifications for simulating running their existing applications in Kubernetes,
the CPU benchmark software may not provide the most accurate results. Docker runtime has a feature to limit
CPUs and memory allocated to containers which is very similar to Kubernetes' container resource limits on
CPUs and memory.

## Commands to create a docker container with limits on CPUs and memory
Assume you have configured docker on Ubuntu 22.10 on a computer. My hardware specs are just an example.
* AMD Ryzen™ Threadripper™ PRO 3945WXs
* Lenovo Thinkstation P620
* Windowing System: Wayland
* GPU: NVidia Quadro T1000
* Disk: Samsung MZVL2512HCJQ-00BL7
* Memory: 32 GiB ECC 3200Mhz

Install the latest docker runtime and allow the current user to execute docker commands.
Execute the following commands to create a docker container with the given numbers of CPUs and memory.
I assume the benchmark software requires less than 512 MiB of memory.
Adjust the following variables for desirable results.
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
apt install -y htop && \
apt install -y wget && \
wget https://www.passmark.com/downloads/pt_linux_x64.zip && \
apt install -y unzip && \
unzip pt_linux_x64.zip && \
apt-get install -y libncurses5 && \
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
The top 2 are integer and floating point math. For example, [AMD Ryzen 5 7600](https://www.cpubenchmark.net/cpu.php?cpu=AMD+Ryzen+5+7600&id=5172).
You can compare the results from the container with the published results. Keep in mind that the results
in the containers are not the same as the published results as the latter were running on bare metal. 

## Run stress test on certain containers
To simulate CPU heavy workloads in a container, install and execute the following packages in the container:
```commandline
apt install s-tui && apt install stress && s-tui
```
Change the mode from monitor to stress to start generating load on CPUs.
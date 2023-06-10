#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

# the following command should be installed in Dockerfile
#apt update && apt install sshpass

# execute sshpass to remotely execute commands over SSH on target servers
CMD="ls -Alh && date"
sshpass -p test-password ssh -o StrictHostKeyChecking=no user@192.168.1.100 $CMD
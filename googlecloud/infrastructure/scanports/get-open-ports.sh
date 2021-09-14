#!/bin/bash
set -e # exit the script when execution hits any error
set -x # print the executing lines

sudo netstat -tulpn | grep LISTEN > netstat.log
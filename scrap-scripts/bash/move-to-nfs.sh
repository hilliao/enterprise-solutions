#!/bin/bash

###
# NFS server is configured at Ubuntu 24.04 host amd-a8
# dependency: sudo mount amd-a8:/var/nfs/share /mnt/nfs
# cron job: 0 3 * * * /home/hil/bin/move-to-nfs.sh >> /home/hil/bin/move-to-nfs.log 2>&1
###

# Define source and destination directories
sub_dir="autodelete"
source_dir="/home/hil/Pictures/$sub_dir"
NFS_dir="/mnt/nfs"

# Check if the destination directory exists
if [[ ! -d "$NFS_dir/$sub_dir" ]]; then
  echo "Error: Destination directory "$NFS_dir/$sub_dir" does not exist."
  exit 1
fi

# Check if /mnt/nfs is mounted
if mountpoint -q "$NFS_dir"; then  # -q for quiet output (no mount info message)
  # Move files (use rsync for better error handling)
  rsync -av --remove-source-files "$source_dir" "$NFS_dir"
else
  echo "Error: $NFS_dir is not mounted."
fi

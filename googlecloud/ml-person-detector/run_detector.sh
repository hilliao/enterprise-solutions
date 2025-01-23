#!/bin/bash

set -e # exit the script when execution hits any error
set -x # print the executing lines

export GOOGLE_APPLICATION_CREDENTIALS=confidential/secrets/person-detection-logger@gcp-project-id.iam.gserviceaccount.com
export RTSP_URL="rtsp://user:password@192.168.111.42:554"
export TFLITE_MODEL_PATH="$HOME/git/enterprise-solutions/googlecloud/ml-person-detector/efficientdet_lite2.tflite"
# Setting a high number > 64 is risking the router's ability to handle outgoing connections.
# if the router's simultaneous outgoing connections max out, egress to the Internet would be degraded severely
export MAX_WORKERS=24
export OUTPUT_IMAGE_DIR="/mnt/1tb/ftp/ipcam/autodelete/person-detector"
# WARNING! Set a higher number without GPU configured with Tensorflow.
# any number less than 3 on a AMD Zen3,4 Ryzen 5 CPU may cause the main execution thread to hang, thus unable to get latest RTSP frames
# the suspected reason is that each thread is taking the same priority, causing the main thread taking RTSP feed to suffer
export SKIP_X_FRAMES=3
export OBJ_DETECT_CONFIDENCE_SCORE=0.4
export PERSON_DETECT_CONFIDENCE_SCORE=0.5
export GCS_BUCKET=bucket-name
export GCS_FOLDER=us-amcrest-cam-0
export IS_GPU=0
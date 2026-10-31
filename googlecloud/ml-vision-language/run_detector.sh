#!/bin/bash
# ======================================================================================================================
# run_detector.sh: template; copy it to run_detector_<camera>.sh and edit the values
# ======================================================================================================================
# Runs mediapipe_detector.py on the camera's video stream. Frames with a person are annotated, saved to
# OUTPUT_IMAGE_DIR, and uploaded to gs://GCS_BUCKET/GCS_FOLDER/YYYY-MM-DD/HH/. Full documentation: README.md.
#
# Usage: ./run_detector.sh
#   Ctrl+C stops the detector. After a failure, e.g. when the watchdog exits a detector starved of CPU, it restarts by
#   itself with exponential back-off (5, 10, 20, 40, 80 s), so no `while true` loop is needed.
#
# Mandatory environment variables (the detector exits with an error listing each one that is unset or empty):
#   RTSP_URL                        Camera stream: rtsp://user:password@host:port/path, or http://.../video.cgi
#   TFLITE_MODEL_PATH               Object detection model file, e.g. efficientdet_lite2.tflite in this folder
#   OUTPUT_IMAGE_DIR                Folder for annotated frames with a person; this script creates it if missing
#   OBJ_DETECT_CONFIDENCE_SCORE     Minimum score (0.0 - 1.0) to report any object
#   PERSON_DETECT_CONFIDENCE_SCORE  Minimum score (0.0 - 1.0) to save a frame with a person; higher, fewer false alarms
#   GCS_BUCKET, GCS_FOLDER          Upload destination; mandatory only when GOOGLE_APPLICATION_CREDENTIALS is set
#
# Optional environment variables [default]:
#   GOOGLE_APPLICATION_CREDENTIALS  Service account key file; setting it enables GCS uploads [unset: no uploads]
#   IS_GPU                          1 runs the model on the GPU. If the log shows `renderer: llvmpipe`, the "GPU" is
#                                   emulated on the CPU and slower than 0 [0]
#   MAX_WORKERS                     GCS upload threads. Over 64 can max out the router's simultaneous outgoing
#                                   connections and severely degrade Internet egress [auto: CPU threads + 4, at most 32]
#   SKIP_X_FRAMES                   Frames skipped between detections; more means less CPU. Without a GPU, values under
#                                   3 starved the RTSP reader in earlier versions [auto: re-tuned every 10 s so that
#                                   detection takes at most DETECTION_DUTY_CYCLE of the time]
#   DETECTION_DUTY_CYCLE            Fraction of the time SKIP_X_FRAMES=auto lets detection take [0.5]
#   WATCHDOG_SECONDS                Exit with all stack traces if no detection completes for this long [120]
#   RESTART_RETRIES                 Restarts in a row without a detection before giving up; 0 disables restarts [5]
#   RESTART_BACKOFF_SECONDS         Wait before the first restart, doubled before each further one [5]
#   HEARTBEAT_SECONDS               Status line interval [1 on a terminal, 60 when output is redirected]
#   OPENCV_FFMPEG_CAPTURE_OPTIONS   FFmpeg options, e.g. "rtsp_transport;tcp" to avoid UDP packet loss [UDP]
#
# Notes:
#   * Copies hold the camera password; keep them out of git.
#   * Do not add `set -x`: it would print RTSP_URL, including the camera password.
# ======================================================================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Mandatory
export RTSP_URL="rtsp://user:password@192.168.111.42:554"
export TFLITE_MODEL_PATH="$SCRIPT_DIR/efficientdet_lite2.tflite"
export OUTPUT_IMAGE_DIR="/mnt/1tb/ftp/ipcam/autodelete/person-detector"
export OBJ_DETECT_CONFIDENCE_SCORE=0.4
export PERSON_DETECT_CONFIDENCE_SCORE=0.5

# Optional: Google Cloud Storage uploads
export GOOGLE_APPLICATION_CREDENTIALS=confidential/secrets/person-detection-logger@gcp-project-id.iam.gserviceaccount.com
export GCS_BUCKET=bucket-name
export GCS_FOLDER=us-amcrest-cam-0

# Optional: not set here means automatic or the default listed above
export IS_GPU=0

mkdir -p "$OUTPUT_IMAGE_DIR"
# exec replaces this shell with the detector, so Ctrl+C and kill reach it directly
exec "$SCRIPT_DIR/bin/python" "$SCRIPT_DIR/mediapipe_detector.py"

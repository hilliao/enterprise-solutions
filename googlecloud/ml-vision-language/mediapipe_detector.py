# -*- coding: utf-8 -*-
""" Person Detector
Inspired by
 1. Google AI Edge https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector
 2. Mediapipe Github project https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/object_detection/python/object_detector.ipynb


# Copyright 2025 GoogleCloud.fr LLC. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

# Object Detection with MediaPipe Tasks

Detect person in a RTSP video stream

# Preparation
Commands to execute in a Python3 virtual environment

```bash
cd enterprise-solutions/googlecloud/ml-person-detector
python3 -m venv .
source bin/activate
pip install -r requirements.txt
```

Then download an off-the-shelf model. Check out the [MediaPipe documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model) for more image classification models that you can use.

```bash
wget  -O efficientdet.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite
wget  -O efficientdet.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite
# this is a  more accurate model than the above
wget  -O efficientdet_lite2.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite
```
"""

import os
import sys
import time
from urllib.parse import urlparse

import process_utils

# Mandatory environment variables; the README section at the top of run_detector.sh also lists the optional ones
parameters = ["RTSP_URL", "TFLITE_MODEL_PATH", "OUTPUT_IMAGE_DIR",
              "OBJ_DETECT_CONFIDENCE_SCORE", "PERSON_DETECT_CONFIDENCE_SCORE"]
# Mandatory only for uploads, which setting GOOGLE_APPLICATION_CREDENTIALS turns on
gcs_parameters = ["GCS_BUCKET", "GCS_FOLDER"]

if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    parameters.extend(gcs_parameters)

# Report every problem at once so the configuration is fixed in one go; an empty value counts as not set. Checked before
# the supervisor starts, so a configuration error exits right away instead of being retried
errors = [f"mandatory environment variable {param} is not set"
          + (" (needed because GOOGLE_APPLICATION_CREDENTIALS is set; unset it to skip uploads)"
             if param in gcs_parameters else "")
          for param in parameters if not os.environ.get(param)]
for param, exists, kind in [("TFLITE_MODEL_PATH", os.path.isfile, "file"),
                            ("OUTPUT_IMAGE_DIR", os.path.isdir, "folder"),
                            ("GOOGLE_APPLICATION_CREDENTIALS", os.path.isfile, "file")]:
    if os.environ.get(param) and not exists(os.environ[param]):
        errors.append(f"{param} is set to {os.environ[param]}, which is not an existing {kind}")
if errors:
    for error in errors:
        sys.stderr.write(f"Error: {error}\n")
    sys.stderr.write(f"Mandatory environment variables: {', '.join(parameters)}\n")
    exit(1)

# Now you can safely access the environment variables, knowing they are set
IP_CAM_URL = os.environ.get("RTSP_URL")
TFLITE_MODEL_PATH = os.environ.get("TFLITE_MODEL_PATH")
# MAX_WORKERS and SKIP_X_FRAMES are optional: unset or "auto" picks them automatically
AUTO_MAX_WORKERS = os.environ.get("MAX_WORKERS", "auto") == "auto"
# ThreadPoolExecutor's own default for I/O-bound work: CPU threads + 4 (20 on a Ryzen 7 7700X), never more than 32
MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4) if AUTO_MAX_WORKERS else int(os.environ["MAX_WORKERS"])
OUTPUT_IMAGE_DIR = os.environ.get("OUTPUT_IMAGE_DIR")
AUTO_SKIP_X_FRAMES = os.environ.get("SKIP_X_FRAMES", "auto") == "auto"
# Auto starts from 3, which worked well when set by hand, then follows auto_frames_to_skip()
SKIP_X_FRAMES = 3 if AUTO_SKIP_X_FRAMES else int(os.environ["SKIP_X_FRAMES"])
OBJ_DETECT_CONFIDENCE_SCORE = float(os.environ.get("OBJ_DETECT_CONFIDENCE_SCORE"))
PERSON_DETECT_CONFIDENCE_SCORE = float(os.environ.get("PERSON_DETECT_CONFIDENCE_SCORE"))
GCS_BUCKET = os.environ.get("GCS_BUCKET")
GCS_FOLDER = os.environ.get("GCS_FOLDER")
# Restart the detector when it fails, e.g. when the watchdog exits it: after RESTART_BACKOFF_SECONDS, then twice as
# long after each further failure, giving up after RESTART_RETRIES restarts in a row without a detection. 0 disables it
RESTART_RETRIES = int(os.environ.get("RESTART_RETRIES", "5"))
RESTART_BACKOFF_SECONDS = float(os.environ.get("RESTART_BACKOFF_SECONDS", "5"))

if __name__ == "__main__" and RESTART_RETRIES > 0 and not process_utils.is_supervised():
    # This process only supervises; the detector runs in a child process so it can be restarted after the watchdog
    # exits it. Nothing below runs here, so the supervisor never loads OpenCV, MediaPipe or the model
    sys.exit(process_utils.supervise(RESTART_RETRIES, RESTART_BACKOFF_SECONDS))

"""## Running inference and visualizing the results
Here are the steps to run object detection using MediaPipe.
Check out the [MediaPipe documentation](https://developers.google.com/mediapipe/solutions/vision/object_detector/python) to learn more about configuration options that this solution supports.
"""

import cv2
# Import the functions
from image_utils import visualize
from gcp_utils import gcs_upload_blob, gcs_path_to_http_url

import datetime
import faulthandler
import itertools
import shutil
import signal
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading

# Detection runs synchronously (VIDEO mode) on a dedicated worker thread instead of LIVE_STREAM + result_callback.
# A result_callback is invoked on a MediaPipe-owned native thread that must re-acquire the GIL while the main thread
# is inside detect_async(); after hours of running, that interplay is the suspected cause of the process hanging
# with idle CPU and ignoring Ctrl+C. With VIDEO mode, MediaPipe never calls back into Python.
import concurrent.futures
import queue
import math

# Exit (with all thread stack traces on stderr) if no detection completes within this many seconds.
# The C-level faulthandler watchdog works even when Python threads are deadlocked on the GIL.
WATCHDOG_SECONDS = int(os.environ.get("WATCHDOG_SECONDS", "120"))
RECONNECT_DELAY_SECONDS = 5
# On a terminal, redraw one status line in place; otherwise (e.g. redirected to a log file) print a new line each time
INTERACTIVE = sys.stdout.isatty()
# Report liveness this often; it needs the GIL, so silence means Python is stuck and the watchdog will fire
HEARTBEAT_SECONDS = int(os.environ.get("HEARTBEAT_SECONDS", "1" if INTERACTIVE else "60"))
# Report STALLED instead of OK when no detection completed for this long
STALL_WARNING_SECONDS = 10
# `kill -USR1 <pid>` prints the stack of every thread without stopping the process
faulthandler.register(signal.SIGUSR1, all_threads=True)
# SKIP_X_FRAMES=auto re-tunes this often from what was measured since the last time
AUTO_SKIP_SECONDS = 10
# SKIP_X_FRAMES=auto skips frames so detection takes at most this fraction of the time. SKIP_X_FRAMES=3 on a 30 frames/s
# camera and 70 ms per detection (EfficientDet-Lite2 on a Ryzen 7 7700X CPU) is about 0.5
DETECTION_DUTY_CYCLE = float(os.environ.get("DETECTION_DUTY_CYCLE", "0.5"))
# Progress counters read by the heartbeat; each key is written by a single thread
stats = {"frames_read": 0, "detections": 0, "detect_seconds": 0.0, "last_detection": time.monotonic(),
         "frames_to_skip": SKIP_X_FRAMES}

# Holds only the latest frame so the capture loop never blocks and detection never works on stale frames
frame_slot = queue.Queue(maxsize=1)
# Thread pool for uploading files to Google cloud storage
gcs_executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

if "IS_GPU" in os.environ and os.environ.get("IS_GPU") == "1":
    # This script is headless. An inherited DISPLAY (e.g. Chrome Remote Desktop's virtual X server) makes glvnd pick
    # Mesa's llvmpipe software renderer instead of the NVIDIA driver; without DISPLAY, EGL uses the GPU directly
    os.environ.pop("DISPLAY", None)
    base_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH, delegate=python.BaseOptions.Delegate.GPU)
else:
    base_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH)
options = vision.ObjectDetectorOptions(base_options=base_options, running_mode=vision.RunningMode.VIDEO,
                                       score_threshold=OBJ_DETECT_CONFIDENCE_SCORE)
detector = vision.ObjectDetector.create_from_options(options)


def offer_latest_frame(frame):
    """Replace any frame not yet picked up by the detection worker; never blocks the capture loop."""
    try:
        frame_slot.get_nowait()
    except queue.Empty:
        pass
    try:
        frame_slot.put_nowait(frame)
    except queue.Full:
        pass  # the worker can't add frames, so this only happens if offer_latest_frame is called concurrently


def handle_detection(frame, detection_result: vision.ObjectDetectorResult):
    person_detected = False  # Flag to track person detection
    for detection in detection_result.detections:
        category = detection.categories[0]
        if category.category_name == 'person' and category.score > PERSON_DETECT_CONFIDENCE_SCORE:
            person_detected = True
            break  # No need to check further if a person is found

    if not person_detected:  # Save image only if a person is detected
        return

    print(f"Person detected: {detection_result}")
    annotated_frame = visualize(frame, detection_result)
    formatted_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
    filename = f"annotated_{formatted_datetime}.png"
    file_path = f"{OUTPUT_IMAGE_DIR}/{filename}"

    if not cv2.imwrite(f"{file_path}", annotated_frame):  # check for successful write
        sys.stderr.write(f"Error: Could not write image to {file_path}!\n")
        return
    print(f"Annotated frame saved to file at {file_path}")

    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        # upload the file to Google cloud storage bucket asynchronously
        gcs_folder_date_hour = (f"{formatted_datetime.split('_')[0]}/"
                                f"{formatted_datetime.split('_')[1].split('-')[0]}")
        blob_name = f"{GCS_FOLDER}/{gcs_folder_date_hour}/{filename}"
        gcs_executor.submit(gcs_upload_blob, GCS_BUCKET, file_path, blob_name)
        expected_gcs_path = f"gs://{GCS_BUCKET}/{blob_name}"
        print(
            f"Started asynchronous upload of {filename} to {blob_name} in bucket {GCS_BUCKET};"
            f" expected url: {gcs_path_to_http_url(expected_gcs_path)}")  # Indicate upload start


def detection_worker():
    last_timestamp_ms = 0
    while True:
        frame = frame_slot.get()
        # VIDEO mode requires strictly increasing timestamps in milliseconds; monotonic clock ignores NTP adjustments
        timestamp_ms = max(time.monotonic_ns() // 1_000_000, last_timestamp_ms + 1)
        last_timestamp_ms = timestamp_ms
        try:
            started = time.monotonic()
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            detection_result = detector.detect_for_video(image, timestamp_ms)
            # Re-arm the watchdog: stalls in either RTSP capture or detection stop this line from being reached
            faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
            stats["last_detection"] = time.monotonic()
            stats["detect_seconds"] += stats["last_detection"] - started
            stats["detections"] += 1
            if stats["detections"] == 1:
                process_utils.report_healthy()  # a restart that gets this far resets the supervisor's back-off
            handle_detection(frame, detection_result)
        except Exception as e:
            sys.stderr.write(f"Error: detection failed for frame at {timestamp_ms} ms: {e}\n")


def detection_progress():
    """Snapshot for auto_frames_to_skip(): time, frames read, detections, and total seconds spent detecting."""
    return time.monotonic(), stats["frames_read"], stats["detections"], stats["detect_seconds"]


def auto_frames_to_skip(start, end, frames_to_skip):
    """SKIP_X_FRAMES=auto: skip just enough frames that detection takes at most DETECTION_DUTY_CYCLE of the time.

    Uses the stream's frame rate and the average time per detection between the detection_progress() snapshots start
    and end. Detection slows down on a busy CPU or with a bigger model, so more frames are skipped and the RTSP reader
    and other detectors keep their share of the CPU; on a faster camera or GPU, fewer are skipped.
    """
    start_time, start_frames, start_detections, start_detect_seconds = start
    end_time, end_frames, end_detections, end_detect_seconds = end
    if end_detections == start_detections:
        return frames_to_skip  # nothing to measure while the camera is down or detection is stalled
    frames_per_second = (end_frames - start_frames) / (end_time - start_time)
    seconds_per_detection = (end_detect_seconds - start_detect_seconds) / (end_detections - start_detections)
    return max(0, math.ceil(frames_per_second * seconds_per_detection / DETECTION_DUTY_CYCLE) - 1)


def heartbeat():
    """Report frame/detection rates and thread counts every HEARTBEAT_SECONDS; flag STALLED detection."""
    prev_frames, prev_detections = 0, 0
    spinner = itertools.cycle("|/-\\")
    while True:
        time.sleep(HEARTBEAT_SECONDS)
        frames, detections = stats["frames_read"], stats["detections"]
        idle = time.monotonic() - stats["last_detection"]
        stalled = idle >= STALL_WARNING_SECONDS
        state = f"STALLED: no detection for {idle:.0f} s, watchdog exits at {WATCHDOG_SECONDS} s" if stalled else "OK"
        os_threads = len(os.listdir("/proc/self/task")) if os.path.isdir("/proc/self/task") else "unknown"
        status = (f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {state} | "
                  f"{(frames - prev_frames) / HEARTBEAT_SECONDS:.1f} frames/s read, "
                  f"{(detections - prev_detections) / HEARTBEAT_SECONDS:.1f} detections/s, "
                  f"skip {stats['frames_to_skip']}{' (auto)' if AUTO_SKIP_X_FRAMES else ''} | "
                  f"threads: {threading.active_count()} Python, {os_threads} OS")
        if INTERACTIVE:
            # Clear the line, draw the status, then return to column 0 so the next output overwrites it. Cut the status
            # to the terminal width: \r only returns to the start of a wrapped line's last row, leaving the rest behind
            columns = shutil.get_terminal_size().columns
            sys.stdout.write(f"\r\033[K{next(spinner)} {status[:columns - 3]}\r")
            sys.stdout.flush()
        elif stalled:
            sys.stderr.write(f"WARNING: {status}\n")
        else:
            print(f"Heartbeat {status}", flush=True)
        prev_frames, prev_detections = frames, detections


def open_video_capture():
    # Bounded open/read timeouts so a camera that stops sending makes read() return False instead of blocking
    timeouts = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000]
    parsed_url = urlparse(IP_CAM_URL)
    # Check if the URL is an HTTP stream from a CGI script, which often requires FFMPEG backend
    if parsed_url.scheme in ['http', 'https'] and parsed_url.path.endswith('/video.cgi'):
        print(f"Using FFMPEG backend for HTTP/CGI stream: {IP_CAM_URL}")
    else:
        print(f"Using FFMPEG backend for stream: {IP_CAM_URL}")
    return cv2.VideoCapture(IP_CAM_URL, cv2.CAP_FFMPEG, timeouts)


if __name__ == "__main__":
    frames_to_skip = SKIP_X_FRAMES  # Skip every X frames
    frame_count = 0
    video_capture = None
    interrupted = False
    faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
    threading.Thread(target=detection_worker, name="detection_worker", daemon=True).start()
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()

    print(f"Uploading with up to {MAX_WORKERS} threads{' (auto)' if AUTO_MAX_WORKERS else ''}; skipping "
          f"{frames_to_skip} frames between detections{', re-tuned automatically' if AUTO_SKIP_X_FRAMES else ''}")

    try:
        video_capture = open_video_capture()
        progress = detection_progress()

        while True:
            ret, frame = video_capture.read()
            if not ret:
                sys.stderr.write(
                    f"An error occurred reading the video input source at {IP_CAM_URL}; "
                    f"reconnecting in {RECONNECT_DELAY_SECONDS} seconds\n")
                video_capture.release()
                time.sleep(RECONNECT_DELAY_SECONDS)
                video_capture = open_video_capture()
                continue

            frame_count += 1
            stats["frames_read"] = frame_count
            if AUTO_SKIP_X_FRAMES and time.monotonic() - progress[0] >= AUTO_SKIP_SECONDS:
                previous, progress = progress, detection_progress()
                frames_to_skip = stats["frames_to_skip"] = auto_frames_to_skip(previous, progress, frames_to_skip)
            if frame_count % (frames_to_skip + 1) == 0:  # Process only every (frames_to_skip + 1)th frame
                offer_latest_frame(frame)

    except KeyboardInterrupt as e:
        interrupted = True
        sys.stderr.write(f":KeyboardInterrupt caught: {e}\n")
    finally:  # Restore terminal settings
        faulthandler.cancel_dump_traceback_later()
        cv2.destroyAllWindows()
        # Release the video capture and destroy windows.
        if video_capture:
            video_capture.release()
        detector.close()
        gcs_executor.shutdown(wait=False)
        print("main execution exiting...")  # Indicate clean exit

    if interrupted:
        # Die by SIGINT instead of exiting 0, so the supervisor and any calling shell loop stop instead of restarting
        process_utils.exit_by_signal(signal.SIGINT)

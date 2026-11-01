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
cd enterprise-solutions/googlecloud/ml-vision-language
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

import restart_supervisor

# Mandatory environment variables; the README section at the top of run_detector_template.sh also lists the optional ones
mandatory_variables = ["RTSP_URL", "TFLITE_MODEL_PATH", "OUTPUT_IMAGE_DIR",
                       "OBJ_DETECT_CONFIDENCE_SCORE", "PERSON_DETECT_CONFIDENCE_SCORE"]
# Mandatory only for uploads, which setting GOOGLE_APPLICATION_CREDENTIALS turns on
upload_variables = ["GCS_BUCKET", "GCS_FOLDER"]

if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    mandatory_variables.extend(upload_variables)

# Report every problem at once so the configuration is fixed in one go; an empty value counts as not set. Checked before
# the supervisor starts, so a configuration error exits right away instead of being retried
config_errors = [f"mandatory environment variable {variable} is not set"
                 + (" (needed because GOOGLE_APPLICATION_CREDENTIALS is set; unset it to skip uploads)"
                    if variable in upload_variables else "")
                 for variable in mandatory_variables if not os.environ.get(variable)]
for variable, exists, kind in [("TFLITE_MODEL_PATH", os.path.isfile, "file"),
                               ("OUTPUT_IMAGE_DIR", os.path.isdir, "folder"),
                               ("GOOGLE_APPLICATION_CREDENTIALS", os.path.isfile, "file")]:
    if os.environ.get(variable) and not exists(os.environ[variable]):
        config_errors.append(f"{variable} is set to {os.environ[variable]}, which is not an existing {kind}")
if config_errors:
    for config_error in config_errors:
        sys.stderr.write(f"Error: {config_error}\n")
    sys.stderr.write(f"Mandatory environment variables: {', '.join(mandatory_variables)}\n")
    exit(1)

# Now you can safely access the environment variables, knowing they are set
RTSP_URL = os.environ.get("RTSP_URL")
TFLITE_MODEL_PATH = os.environ.get("TFLITE_MODEL_PATH")
# MAX_WORKERS and SKIP_X_FRAMES are optional: unset or "auto" picks them automatically
AUTO_MAX_WORKERS = os.environ.get("MAX_WORKERS", "auto") == "auto"
# ThreadPoolExecutor's own default for I/O-bound work: CPU threads + 4 (20 on a Ryzen 7 7700X), never more than 32
MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4) if AUTO_MAX_WORKERS else int(os.environ["MAX_WORKERS"])
OUTPUT_IMAGE_DIR = os.environ.get("OUTPUT_IMAGE_DIR")
AUTO_SKIP_X_FRAMES = os.environ.get("SKIP_X_FRAMES", "auto") == "auto"
# Auto starts from 3, which worked well when set by hand, then follows tune_frames_to_skip()
SKIP_X_FRAMES = 3 if AUTO_SKIP_X_FRAMES else int(os.environ["SKIP_X_FRAMES"])
OBJ_DETECT_CONFIDENCE_SCORE = float(os.environ.get("OBJ_DETECT_CONFIDENCE_SCORE"))
PERSON_DETECT_CONFIDENCE_SCORE = float(os.environ.get("PERSON_DETECT_CONFIDENCE_SCORE"))
GCS_BUCKET = os.environ.get("GCS_BUCKET")
GCS_FOLDER = os.environ.get("GCS_FOLDER")
# Restart the detector when it fails, e.g. when the watchdog exits it: after RESTART_BACKOFF_SECONDS, then twice as
# long after each further failure, giving up after RESTART_RETRIES restarts in a row without a detection. 0 disables it
RESTART_RETRIES = int(os.environ.get("RESTART_RETRIES", "5"))
RESTART_BACKOFF_SECONDS = float(os.environ.get("RESTART_BACKOFF_SECONDS", "5"))

if __name__ == "__main__" and RESTART_RETRIES > 0 and not restart_supervisor.is_supervised():
    # This process only supervises; the detector runs in a child process so it can be restarted after the watchdog
    # exits it. Nothing below runs here, so the supervisor never loads OpenCV, MediaPipe or the model
    sys.exit(restart_supervisor.supervise(RESTART_RETRIES, RESTART_BACKOFF_SECONDS))

"""## Running inference and visualizing the results
Here are the steps to run object detection using MediaPipe.
Check out the [MediaPipe documentation](https://developers.google.com/mediapipe/solutions/vision/object_detector/python) to learn more about configuration options that this solution supports.
"""

import cv2
from draw_detections import draw_detection_boxes
from gcs_upload import upload_file, gcs_path_to_browser_url

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
progress = {"frames_read": 0, "detections": 0, "detect_seconds": 0.0, "last_detection": time.monotonic(),
         "frames_to_skip": SKIP_X_FRAMES}

# Holds only the latest frame so the capture loop never blocks and detection never works on stale frames
latest_frame = queue.Queue(maxsize=1)
# Thread pool for uploading files to Google cloud storage
upload_executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

if "IS_GPU" in os.environ and os.environ.get("IS_GPU") == "1":
    # This script is headless. An inherited DISPLAY (e.g. Chrome Remote Desktop's virtual X server) makes glvnd pick
    # Mesa's llvmpipe software renderer instead of the NVIDIA driver; without DISPLAY, EGL uses the GPU directly
    os.environ.pop("DISPLAY", None)
    model_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH, delegate=python.BaseOptions.Delegate.GPU)
else:
    model_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH)
detector_options = vision.ObjectDetectorOptions(base_options=model_options, running_mode=vision.RunningMode.VIDEO,
                                                score_threshold=OBJ_DETECT_CONFIDENCE_SCORE)
detector = vision.ObjectDetector.create_from_options(detector_options)


def offer_latest_frame(frame):
    """Replace any frame not yet picked up by the detection worker; never blocks the capture loop."""
    try:
        latest_frame.get_nowait()
    except queue.Empty:
        pass
    try:
        latest_frame.put_nowait(frame)
    except queue.Full:
        pass  # the worker can't add frames, so this only happens if offer_latest_frame is called concurrently


def save_frame_if_person(frame, detection_result: vision.ObjectDetectorResult):
    """Save the frame with its detections drawn, and upload it, if it has a person scoring over the threshold."""
    if not any(detection.categories[0].category_name == 'person'
               and detection.categories[0].score > PERSON_DETECT_CONFIDENCE_SCORE
               for detection in detection_result.detections):
        return

    print(f"Person detected: {detection_result}")
    annotated_frame = draw_detection_boxes(frame, detection_result)
    now = datetime.datetime.now()
    filename = f"annotated_{now:%Y-%m-%d_%H-%M-%S.%f}.png"
    file_path = f"{OUTPUT_IMAGE_DIR}/{filename}"

    if not cv2.imwrite(file_path, annotated_frame):
        sys.stderr.write(f"Error: Could not write image to {file_path}!\n")
        return
    print(f"Annotated frame saved to file at {file_path}")

    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        # Upload in the background, into a folder per date and hour: GCS_FOLDER/YYYY-MM-DD/HH/
        object_name = f"{GCS_FOLDER}/{now:%Y-%m-%d/%H}/{filename}"
        upload_executor.submit(upload_file, GCS_BUCKET, file_path, object_name)
        print(f"Started asynchronous upload of {filename} to {object_name} in bucket {GCS_BUCKET};"
              f" expected url: {gcs_path_to_browser_url(f'gs://{GCS_BUCKET}/{object_name}')}")


def detection_worker():
    last_timestamp_ms = 0
    while True:
        frame = latest_frame.get()
        # VIDEO mode requires strictly increasing timestamps in milliseconds; monotonic clock ignores NTP adjustments
        timestamp_ms = max(time.monotonic_ns() // 1_000_000, last_timestamp_ms + 1)
        last_timestamp_ms = timestamp_ms
        try:
            started = time.monotonic()
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            detection_result = detector.detect_for_video(image, timestamp_ms)
            # Re-arm the watchdog: stalls in either RTSP capture or detection stop this line from being reached
            faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
            progress["last_detection"] = time.monotonic()
            progress["detect_seconds"] += progress["last_detection"] - started
            progress["detections"] += 1
            if progress["detections"] == 1:
                restart_supervisor.report_healthy()  # a restart that gets this far resets the supervisor's back-off
            save_frame_if_person(frame, detection_result)
        except Exception as error:
            sys.stderr.write(f"Error: detection failed for frame at {timestamp_ms} ms: {error}\n")


def progress_snapshot():
    """Snapshot for tune_frames_to_skip(): time, frames read, detections, and total seconds spent detecting."""
    return time.monotonic(), progress["frames_read"], progress["detections"], progress["detect_seconds"]


def tune_frames_to_skip(start, end, frames_to_skip):
    """SKIP_X_FRAMES=auto: skip just enough frames that detection takes at most DETECTION_DUTY_CYCLE of the time.

    Uses the stream's frame rate and the average time per detection between the progress_snapshot() snapshots start
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
    previous_frames, previous_detections = 0, 0
    spinner = itertools.cycle("|/-\\")
    while True:
        time.sleep(HEARTBEAT_SECONDS)
        frames, detections = progress["frames_read"], progress["detections"]
        seconds_since_detection = time.monotonic() - progress["last_detection"]
        stalled = seconds_since_detection >= STALL_WARNING_SECONDS
        state = (f"STALLED: no detection for {seconds_since_detection:.0f} s, watchdog exits at {WATCHDOG_SECONDS} s"
                 if stalled else "OK")
        os_threads = len(os.listdir("/proc/self/task")) if os.path.isdir("/proc/self/task") else "unknown"
        status = (f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {state} | "
                  f"{(frames - previous_frames) / HEARTBEAT_SECONDS:.1f} frames/s read, "
                  f"{(detections - previous_detections) / HEARTBEAT_SECONDS:.1f} detections/s, "
                  f"skip {progress['frames_to_skip']}{' (auto)' if AUTO_SKIP_X_FRAMES else ''} | "
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
        previous_frames, previous_detections = frames, detections


def without_password(url):
    """The URL with its password replaced by ***, so that logs never hold the camera password."""
    parsed_url = urlparse(url)
    if not parsed_url.password:
        return url
    return parsed_url._replace(netloc=parsed_url.netloc.replace(f":{parsed_url.password}@", ":***@", 1)).geturl()


def open_video_capture():
    # Bounded open/read timeouts so a camera that stops sending makes read() return False instead of blocking
    timeouts = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000]
    parsed_url = urlparse(RTSP_URL)
    # Check if the URL is an HTTP stream from a CGI script, which often requires FFMPEG backend
    if parsed_url.scheme in ['http', 'https'] and parsed_url.path.endswith('/video.cgi'):
        print(f"Using FFMPEG backend for HTTP/CGI stream: {without_password(RTSP_URL)}")
    else:
        print(f"Using FFMPEG backend for stream: {without_password(RTSP_URL)}")
    return cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG, timeouts)


if __name__ == "__main__":
    frames_to_skip = SKIP_X_FRAMES
    frames_read = 0
    video_capture = None
    interrupted = False
    faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
    threading.Thread(target=detection_worker, name="detection_worker", daemon=True).start()
    threading.Thread(target=heartbeat, name="heartbeat", daemon=True).start()

    print(f"Uploading with up to {MAX_WORKERS} threads{' (auto)' if AUTO_MAX_WORKERS else ''}; skipping "
          f"{frames_to_skip} frames between detections{', re-tuned automatically' if AUTO_SKIP_X_FRAMES else ''}")

    try:
        video_capture = open_video_capture()
        last_tuning = progress_snapshot()

        while True:
            frame_read, frame = video_capture.read()
            if not frame_read:
                sys.stderr.write(
                    f"An error occurred reading the video input source at {without_password(RTSP_URL)}; "
                    f"reconnecting in {RECONNECT_DELAY_SECONDS} seconds\n")
                video_capture.release()
                time.sleep(RECONNECT_DELAY_SECONDS)
                video_capture = open_video_capture()
                continue

            frames_read += 1
            progress["frames_read"] = frames_read
            if AUTO_SKIP_X_FRAMES and time.monotonic() - last_tuning[0] >= AUTO_SKIP_SECONDS:
                previous_tuning, last_tuning = last_tuning, progress_snapshot()
                frames_to_skip = progress["frames_to_skip"] = tune_frames_to_skip(previous_tuning, last_tuning,
                                                                                  frames_to_skip)
            if frames_read % (frames_to_skip + 1) == 0:  # Process only every (frames_to_skip + 1)th frame
                offer_latest_frame(frame)

    except KeyboardInterrupt as error:
        interrupted = True
        sys.stderr.write(f":KeyboardInterrupt caught: {error}\n")
    finally:  # Restore terminal settings
        faulthandler.cancel_dump_traceback_later()
        cv2.destroyAllWindows()
        # Release the video capture and destroy windows.
        if video_capture:
            video_capture.release()
        detector.close()
        upload_executor.shutdown(wait=False)
        print("main execution exiting...")  # Indicate clean exit

    if interrupted:
        # Die by SIGINT instead of exiting 0, so the supervisor and any calling shell loop stop instead of restarting
        restart_supervisor.exit_by_signal(signal.SIGINT)

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

import cv2
# Import the functions
from image_utils import visualize
from gcp_utils import gcs_upload_blob, gcs_path_to_http_url

# Parameters must be set for each environment variable
parameters = ["RTSP_URL", "TFLITE_MODEL_PATH", "MAX_WORKERS", "OUTPUT_IMAGE_DIR", "SKIP_X_FRAMES",
              "OBJ_DETECT_CONFIDENCE_SCORE", "PERSON_DETECT_CONFIDENCE_SCORE"]

if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    parameters.extend(["GCS_BUCKET", "GCS_FOLDER"])

for param in parameters:  # Iterate through the parameters list
    if os.environ.get(param) is None:  # Check if the environment variable is set
        sys.stderr.write(
            f"Error: required environment variable {param} is not set. you must set all {parameters}!\n")  # Print to stderr with the parameter name
        exit(1)

# Now you can safely access the environment variables, knowing they are set
IP_CAM_URL = os.environ.get("RTSP_URL")
TFLITE_MODEL_PATH = os.environ.get("TFLITE_MODEL_PATH")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS"))
OUTPUT_IMAGE_DIR = os.environ.get("OUTPUT_IMAGE_DIR")
SKIP_X_FRAMES = int(os.environ.get("SKIP_X_FRAMES"))
OBJ_DETECT_CONFIDENCE_SCORE = float(os.environ.get("OBJ_DETECT_CONFIDENCE_SCORE"))
PERSON_DETECT_CONFIDENCE_SCORE = float(os.environ.get("PERSON_DETECT_CONFIDENCE_SCORE"))
GCS_BUCKET = os.environ.get("GCS_BUCKET")
GCS_FOLDER = os.environ.get("GCS_FOLDER")

"""## Running inference and visualizing the results
Here are the steps to run object detection using MediaPipe.
Check out the [MediaPipe documentation](https://developers.google.com/mediapipe/solutions/vision/object_detector/python) to learn more about configuration options that this solution supports.
"""

import datetime
import faulthandler
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
# `kill -USR1 <pid>` prints the stack of every thread without stopping the process
faulthandler.register(signal.SIGUSR1, all_threads=True)

# Holds only the latest frame so the capture loop never blocks and detection never works on stale frames
frame_slot = queue.Queue(maxsize=1)
# Thread pool for uploading files to Google cloud storage
gcs_executor = concurrent.futures.ThreadPoolExecutor(max_workers=math.ceil(MAX_WORKERS))

if "IS_GPU" in os.environ and os.environ.get("IS_GPU") == "1":
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
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            detection_result = detector.detect_for_video(image, timestamp_ms)
            # Re-arm the watchdog: stalls in either RTSP capture or detection stop this line from being reached
            faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
            handle_detection(frame, detection_result)
        except Exception as e:
            sys.stderr.write(f"Error: detection failed for frame at {timestamp_ms} ms: {e}\n")


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
    faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
    threading.Thread(target=detection_worker, name="detection_worker", daemon=True).start()

    try:
        video_capture = open_video_capture()

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
            if frame_count % (frames_to_skip + 1) == 0:  # Process only every (frames_to_skip + 1)th frame
                offer_latest_frame(frame)

    except KeyboardInterrupt as e:
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

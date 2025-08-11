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
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import threading
import sys

# Implement asynchronous processing for image detection
import concurrent.futures
import queue
import math

results_queue = queue.Queue()
# Thread pool for uploading files to Google cloud storage
gcs_executor = concurrent.futures.ThreadPoolExecutor(max_workers=math.ceil(MAX_WORKERS))


def detector_callback(detection_result: vision.ObjectDetectorResult,
                      output_image: mp.Image, timestamp_ms: int):
    person_detect_confidence_score = PERSON_DETECT_CONFIDENCE_SCORE
    detection_result.timestamp_ms = timestamp_ms
    person_detected = False  # Flag to track person detection
    for detection in detection_result.detections:
        category = detection.categories[0]
        if category.category_name == 'person' and category.score > person_detect_confidence_score:
            person_detected = True
            break  # No need to check further if a person is found

    if person_detected:  # Save image only if a person is detected
        print(f"Person detected: {detection_result}")
        annotated_frame = visualize(output_image.numpy_view().copy(), detection_result)  # Only visualize if saving
        formatted_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
        filename = f"annotated_{formatted_datetime}.png"
        file_path = f"{OUTPUT_IMAGE_DIR}/{filename}"

        if cv2.imwrite(f"{file_path}", annotated_frame):  # check for successful write
            print(f"Annotated frame saved to file at {file_path}")
        else:
            sys.stderr.write(f"Error: Could not write image to {file_path}!\n")
            filename = None

        # Put results in queue for processing. Only if a person is found
        results_queue.put((detection_result, filename, formatted_datetime))
    else:
        results_queue.put((None, None, None))  # Signal that no person detected, helps prevent queue buildup


if "IS_GPU" in os.environ and os.environ.get("IS_GPU") == "1":
    base_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH, delegate=python.BaseOptions.Delegate.GPU)
else:
    base_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH)
options = vision.ObjectDetectorOptions(base_options=base_options, running_mode=vision.RunningMode.LIVE_STREAM,
                                       score_threshold=OBJ_DETECT_CONFIDENCE_SCORE, result_callback=detector_callback)
detector = vision.ObjectDetector.create_from_options(options)

if __name__ == "__main__":
    frames_to_skip = SKIP_X_FRAMES  # Skip every X frames
    frame_count = 0
    video_capture = None

    try:
        parsed_url = urlparse(IP_CAM_URL)
        # Check if the URL is an HTTP stream from a CGI script, which often requires FFMPEG backend
        if parsed_url.scheme in ['http', 'https'] and parsed_url.path.endswith('/video.cgi'):
            print(f"Using FFMPEG backend for HTTP/CGI stream: {IP_CAM_URL}")
            video_capture = cv2.VideoCapture(IP_CAM_URL, cv2.CAP_FFMPEG)
        else:
            print(f"Using default backend for stream: {IP_CAM_URL}")
            video_capture = cv2.VideoCapture(IP_CAM_URL)

        while True:
            ret, frame = video_capture.read()
            if not ret:
                sys.stderr.write(
                    f"An error occurred opening the video input source at {IP_CAM_URL} in the main execution")
                break

            frame_count += 1
            if frame_count % (frames_to_skip + 1) == 0:  # Process only every (frames_to_skip + 1)th frame
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
                # Detect objects in the current frame.
                detector.detect_async(image, int(time.time_ns() / 1000))

            # Process results from the queue (non-blocking)
            print(f"Active thread count: {threading.active_count()}", end="\r")
            if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
                try:
                    detection_result, filename, formatted_datetime = results_queue.get_nowait()
                    if filename:  # Execution gets here if a person was detected and annotated image saved to a file
                        # upload the file to Google cloud storage bucket asynchronously
                        gcs_folder_date_hour = (f"{formatted_datetime.split('_')[0]}/"
                                                f"{formatted_datetime.split('_')[1].split('-')[0]}")
                        blob_name = f"{GCS_FOLDER}/{gcs_folder_date_hour}/{filename}"
                        gcs_executor.submit(gcs_upload_blob, GCS_BUCKET, f"{OUTPUT_IMAGE_DIR}/{filename}", blob_name)
                        expected_gcs_path = f"gs://{GCS_BUCKET}/{blob_name}"
                        print(
                            f"Started asynchronous upload of {filename} to {blob_name} in bucket {GCS_BUCKET};"
                            f" expected url: {gcs_path_to_http_url(expected_gcs_path)}")  # Indicate upload start
                except queue.Empty:
                    pass  # No new results yet


    except KeyboardInterrupt as e:
        sys.stderr.write(f":KeyboardInterrupt caught: {e}\n")
    finally:  # Restore terminal settings

        cv2.destroyAllWindows()
        # Release the video capture and destroy windows.
        if video_capture:
            video_capture.release()
        print("main execution exiting...")  # Indicate clean exit

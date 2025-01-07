# -*- coding: utf-8 -*-
""" Person Detector

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
wget  -O efficientdet.tflite -q https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite
wget  -O efficientdet.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite
# this is a  more accurate model than the above
wget  -O efficientdet_lite2.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite
```
"""

import os, sys
import cv2
import numpy as np

# Parameters must be set for each environment variable
parameters = ["RTSP_URL", "TFLITE_MODEL_PATH", "MAX_WORKERS", "OUTPUT_IMAGE_DIR", "SKIP_X_FRAMES",
              "OBJ_DETECT_CONFIDENCE_SCORE", "PERSON_DETECT_CONFIDENCE_SCORE",
              "GCS_BUCKET", "GCS_FOLDER"]

for param in parameters:  # Iterate through the parameters list
    if os.environ.get(param) is None:  # Check if the environment variable is set
        sys.stderr.write(
            f"Error: required environment variable {param} is not set. you must set all {parameters}!\n")  # Print to stderr with the parameter name
        exit(1)

# Now you can safely access the environment variables, knowing they are set
RTSP_URL = os.environ.get("RTSP_URL")
TFLITE_MODEL_PATH = os.environ.get("TFLITE_MODEL_PATH")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS"))
OUTPUT_IMAGE_DIR = os.environ.get("OUTPUT_IMAGE_DIR")
SKIP_X_FRAMES = int(os.environ.get("SKIP_X_FRAMES"))
OBJ_DETECT_CONFIDENCE_SCORE = float(os.environ.get("OBJ_DETECT_CONFIDENCE_SCORE"))
PERSON_DETECT_CONFIDENCE_SCORE = float(os.environ.get("PERSON_DETECT_CONFIDENCE_SCORE"))
GCS_BUCKET = os.environ.get("GCS_BUCKET")
GCS_FOLDER = os.environ.get("GCS_FOLDER")

# Visualization parameters (group them together)
MARGIN = 10  # pixels
ROW_SIZE = 10  # pixels
FONT_SIZE = 1
FONT_THICKNESS = 1
TEXT_COLOR = (255, 0, 0)  # red


# functions to visualize the object detection results
def visualize(
        image,
        detection_result
) -> np.ndarray:
    """Draws bounding boxes on the input image and return it.
    Args:
      image: The input RGB image.
      detection_result: The list of all "Detection" entities to be visualized.
    Returns:
      Image with bounding boxes.
    """
    for detection in detection_result.detections:
        # Draw bounding_box
        bbox = detection.bounding_box
        start_point = bbox.origin_x, bbox.origin_y
        end_point = bbox.origin_x + bbox.width, bbox.origin_y + bbox.height
        cv2.rectangle(image, start_point, end_point, TEXT_COLOR, 3)

        # Draw label and score
        category = detection.categories[0]
        category_name = category.category_name
        probability = round(category.score, 2)
        result_text = category_name + ' (' + str(probability) + ')'
        text_location = (MARGIN + bbox.origin_x,
                         MARGIN + ROW_SIZE + bbox.origin_y)
        cv2.putText(image, result_text, text_location, cv2.FONT_HERSHEY_PLAIN,
                    FONT_SIZE, TEXT_COLOR, FONT_THICKNESS)

    return image


"""## Running inference and visualizing the results
Here are the steps to run object detection using MediaPipe.
Check out the [MediaPipe documentation](https://developers.google.com/mediapipe/solutions/vision/object_detector/python) to learn more about configuration options that this solution supports.
"""

# STEP 1: Import the necessary modules.
import datetime
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Allow user to press q to quit
import threading
import sys
import termios
import tty


def is_debugger_attached():
    return 'pydevd' in sys.modules


if not is_debugger_attached():
    original_terminal_settings = termios.tcgetattr(sys.stdin)  # Store the original settings


    def get_key():  # Function to get a single character from the terminal
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch


    key_pressed = None  # Global variable to store key press


    def get_key_thread():
        global key_pressed
        while True:  # Keep listening for key presses
            key_pressed = get_key()


    # Start the keypress listener thread
    key_thread = threading.Thread(target=get_key_thread, daemon=True)
    key_thread.start()

# Implement asynchronous processing for image detection
import concurrent.futures
import queue

results_queue = queue.Queue()
# Thread pool for asynchronous tasks of image object detection
detector_executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)  # Adjust per CPU core as needed
# Thread pool for uploading files to Google cloud storage
import math

gcs_executor = concurrent.futures.ThreadPoolExecutor(max_workers=math.ceil(MAX_WORKERS / 4))

# STEP 2: Create an ObjectDetector object.
base_options = python.BaseOptions(model_asset_path=TFLITE_MODEL_PATH)
options = vision.ObjectDetectorOptions(base_options=base_options, score_threshold=OBJ_DETECT_CONFIDENCE_SCORE)
detector = vision.ObjectDetector.create_from_options(options)


def detect_and_save_img(image, frame, PERSON_CONFIDENCE_SCORE=0.5):
    detection_result = detector.detect(image)
    person_detected = False  # Flag to track person detection
    for detection in detection_result.detections:
        category = detection.categories[0]
        if category.category_name == 'person' and category.score > PERSON_CONFIDENCE_SCORE:
            person_detected = True
            break  # No need to check further if a person is found

    if person_detected:  # Save image only if a person is detected
        print(f"Person detected: {detection_result}")
        annotated_frame = visualize(frame, detection_result)  # Only visualize if saving
        formatted_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
        filename = f"annotated_frame_{formatted_datetime}.png"
        if not cv2.imwrite(f"{OUTPUT_IMAGE_DIR}/{filename}", annotated_frame):  # check for successful write
            sys.stderr.write(f"Error: Could not write image to {OUTPUT_IMAGE_DIR}/{filename}!\n")
            # Handle the error appropriately (e.g., log, retry, skip)
        else:
            print(f"Annotated frame saved to file at {OUTPUT_IMAGE_DIR}/{filename}")

        results_queue.put(
            (detection_result, filename))  # Put results in queue for processing. Only if a person is found
    else:
        results_queue.put((None, None))  # Signal that no person detected, helps prevent queue buildup


# upload detected images to GCS buckets in a async thread
from google.cloud import storage


def gcs_upload_blob(bucket_name, source_file_name, destination_blob_name):
    """
    Uploads a file to the bucket.
    :param bucket_name: Google cloud storage bucket name
    :param source_file_name: /local/path/to/file.png
    :param destination_blob_name: folder-path/storage-object-name.png
    :return: gs://bucket_name/destination_blob_name
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        # Optional: set a generation-match precondition to avoid potential race conditions
        # and data corruptions. The request to upload is aborted if the object's
        # generation number does not match your precondition. For a destination
        # object that does not yet exist, set the if_generation_match precondition to 0.
        # If the destination object already exists in your bucket, set instead a
        # generation-match precondition using its generation number.
        generation_match_precondition = 0

        blob.upload_from_filename(source_file_name, if_generation_match=generation_match_precondition)
        gs_path = f"gs://{bucket_name}/{destination_blob_name}"

        return gs_path

    except Exception as e:
        sys.stderr.write(
            f"Google Cloud Storage upload failed for {source_file_name} to {destination_blob_name} in bucket {bucket_name}: {e}!\n")  # Log or handle
        return None  # Or return a specific error value


def gcs_path_to_http_url(gcs_path):
    """Converts a Google Cloud Storage path to a publicly accessible HTTP URL.

    Args:
        gcs_path: The Google Cloud Storage path (e.g., gs://bucket/path/to/file.txt)

    Returns:
        A publicly accessible HTTP URL for the GCS object,
        or None if the path is not valid.

    Raises:
        ValueError: If the GCS path is not formatted correctly.
    """

    # Check if the path starts with "gs://"
    if not gcs_path.startswith("gs://"):
        raise ValueError("Invalid GCS path. Must start with 'gs://'")

    # Extract bucket and object names
    parts = gcs_path.split("/", 3)
    if len(parts) < 4:
        raise ValueError("Invalid GCS path format")

    bucket_name = parts[2]
    object_name = "/".join(parts[3:])

    # Publicly accessible objects don't require additional configuration
    return f"https://storage.cloud.google.com/{bucket_name}/{object_name}"


# STEP 3: Load the input video, Detect objects in the input image.

if __name__ == "__main__":
    frames_to_skip = SKIP_X_FRAMES  # Skip every X frames
    frame_count = 0
    video_capture = None

    try:
        video_capture = cv2.VideoCapture(RTSP_URL)
        while True:
            ret, frame = video_capture.read()
            if not ret:
                sys.stderr.write(
                    f"An error occurred opening the video input source at {RTSP_URL} in the main execution")
                break

            frame_count += 1
            if frame_count % (frames_to_skip + 1) == 0:  # Process only every (frames_to_skip + 1)th frame
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
                # Detect objects in the current frame.
                # Submit detection and saving task to the executor
                detector_executor.submit(detect_and_save_img, image, frame.copy(),
                                         PERSON_DETECT_CONFIDENCE_SCORE)  # .copy() important to prevent data corruption

            # Process results from the queue (non-blocking)
            if is_debugger_attached():
                print(f"Active thread count for tasks like "
                      f"image detection and uploading to Google cloud storage: {threading.active_count()}", end="\r")
            try:
                detection_result, filename = results_queue.get_nowait()
                if detection_result:  # This is where you print. You'll only get here if a person was detected
                    # Submit GCS upload to the executor
                    formatted_datetime = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")
                    gcs_folder_date_hour = (f"{formatted_datetime.split('_')[0]}/"
                                            f"{formatted_datetime.split('_')[1].split('-')[0]}")
                    blob_name = f"{GCS_FOLDER}/{gcs_folder_date_hour}/{filename}"
                    gcs_executor.submit(gcs_upload_blob, GCS_BUCKET, f"{OUTPUT_IMAGE_DIR}/{filename}",
                                        blob_name)
                    expected_gcs_path = f"gs://{GCS_BUCKET}/{blob_name}"
                    print(
                        f"Started asynchronous upload of {filename} to {blob_name} in bucket {GCS_BUCKET};"
                        f" expected url: {gcs_path_to_http_url(expected_gcs_path)}")  # Indicate upload start
            except queue.Empty:
                pass  # No new results yet

            if not is_debugger_attached():
                if key_pressed:  # Check if any key was pressed
                    if key_pressed == 'q':
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)
                        break  # Exit if 'q' is pressed
                    else:
                        print(f"Key pressed: {key_pressed}")  # Or handle other keypresses if needed.
                        # You might want to reset key_pressed here if you only want to react to new keypresses.
                        key_pressed = None  # Reset key_pressed
                        # ... potentially handle other key presses

    except (Exception, KeyboardInterrupt) as e:
        sys.stderr.write(f"An error occurred in the main execution or program interrupted: {e}\n")
    finally:  # Restore terminal settings
        if not is_debugger_attached():
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_terminal_settings)

        cv2.destroyAllWindows()
        # Release the video capture and destroy windows.
        if video_capture:
            video_capture.release()
        print("main execution exiting...")  # Indicate clean exit

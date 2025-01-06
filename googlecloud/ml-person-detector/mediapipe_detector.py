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
pip install mediapipe

Then download an off-the-shelf model. Check out the [MediaPipe documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model) for more image classification models that you can use.

wget  -O efficientdet.tflite -q https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite
wget  -O efficientdet.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite
# this is a  more accurate model than the above
wget  -O efficientdet_lite2.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite

"""

"""
# Parameters must be set for each environment
"""
import os, sys
import cv2
import numpy as np

RTSP_URL = os.environ.get("RTSP_URL")
if not RTSP_URL:
    sys.stderr.write("Error: RTSP_URL environment variable is not set.\n")  # Print to stderr
    exit(1)
TFLITE_MODEL_PATH = "/home/hil/git/enterprise-solutions/googlecloud/ml-person-detector/efficientdet_lite2.tflite"
MAX_WORKERS = 20
OUTPUT_IMAGE_DIR = "/mnt/1tb/ftp/ipcam/autodelete/person-detector"
SKIP_X_FRAMES = 3  # when the number is too low, execution of the program will cause significant lag for image detection.
OBJ_DETECT_CONFIDENCE_SCORE = 0.4
PERSON_DETECT_CONFIDENCE_SCORE = 0.5

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
# Executor for asynchronous tasks of image object detection
executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)  # Adjust as needed

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
        annotated_frame = visualize(frame, detection_result)  # Only visualize if saving
        filename = f"annotated_frame_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
        cv2.imwrite(f"{OUTPUT_IMAGE_DIR}/{filename}", annotated_frame)
        results_queue.put(
            (detection_result, filename))  # Put results in queue for processing. Only if a person is found
    else:
        results_queue.put((None, None))  # Signal that no person detected, helps prevent queue buildup


# STEP 3: Load the input video.
# STEP 4: Detect objects in the input image.

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
                executor.submit(detect_and_save_img, image, frame.copy(),
                                PERSON_DETECT_CONFIDENCE_SCORE)  # .copy() important to prevent data corruption

            # Process results from the queue (non-blocking)
            try:
                detection_result, filename = results_queue.get_nowait()
                if detection_result:  # This is where you print. You'll only get here if a person was detected
                    print(f"{detection_result} at filename {filename}")
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

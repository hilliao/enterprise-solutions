# Machine learning person detector using Mediapipe library

* **[MediaPipe Models](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/object_detection/python/object_detector.ipynb):** Download a TensorFlow Lite [object detection model](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector).  EfficientDet-Lite models are recommended for their balance of speed and accuracy.  Place the model in your project directory. See `mediapipe_detector.py` for examples.
* **RTSP Stream:**  You'll need access to an RTSP or FFMPEG HTTP/CGI video stream.  The URL, username, and password are configured in environment variables (see below).
* **Output Directory:**  Ensure the output directory (`OUTPUT_IMAGE_DIR`) for saving annotated images exists and is writable.
* **(Optional) Google Cloud Storage:** To enable uploads to GCS, you'll need a GCS bucket and appropriate credentials.

## Configuration

Environment variables are used to configure the script. These are set within the `run_detector.sh` script.

| Variable | Description                                                                                                                                                                                                        | Example                                                                                   |
|---|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to your Google Cloud service account credentials file (optional).  Required only for GCS uploads.                                                                                                             | `confidential/secrets/person-detection-logger@gcp-project-id.iam.gserviceaccount.com`     |
| `RTSP_URL` | URL of the RTSP or FFMPEG HTTP/CGI video stream.                                                                                                                                                                   | `rtsp://user:password@192.168.111.42:554`, http://admin:pass@192.168.123.123:82/video.cgi |
| `TFLITE_MODEL_PATH` | Path to the TensorFlow Lite model file.                                                                                                                                                                            | `$HOME/git/enterprise-solutions/googlecloud/ml-person-detector/efficientdet_lite2.tflite` |
| `MAX_WORKERS` | Number of threads for asynchronous GCS uploads (optional, defaults to the number of processors).  Recommended to keep this number reasonably low to avoid overwhelming the router if also used as edge deployment. | `24`                                                                                      |
| `OUTPUT_IMAGE_DIR` | Path to the directory where annotated images will be saved.                                                                                                                                                        | `/mnt/1tb/ftp/ipcam/autodelete/person-detector`                                           |
| `SKIP_X_FRAMES` | Number of frames to skip between detections. Higher values reduce processing load.                                                                                                                                 | `3`                                                                                       |
| `OBJ_DETECT_CONFIDENCE_SCORE` | Minimum confidence score for object detection (0.0 - 1.0).                                                                                                                                                         | `0.4`                                                                                     |
| `PERSON_DETECT_CONFIDENCE_SCORE` | Minimum confidence score specifically for person detection (0.0 - 1.0).                                                                                                                                            | `0.5`                                                                                     |
| `GCS_BUCKET` | Name of your Google Cloud Storage bucket (optional).                                                                                                                                                               | `bucket-name`                                                                             |
| `GCS_FOLDER` | Folder within the GCS bucket for storing uploaded images (optional).                                                                                                                                               | `us-amcrest-cam-0`                                                                        |
| `IS_GPU` | Set to 1 to use GPU delegation (optional). Only useful with a real GPU; if the log shows `renderer: llvmpipe` (e.g. Ryzen 5 5500 without integrated graphics), the "GPU" runs in software on the CPU, so keep `0`. | `0`                                                                                       |
| `WATCHDOG_SECONDS` | Exit with all thread stack traces on stderr if no detection completes within this many seconds (optional, defaults to `120`). See [Hang protection](#hang-protection).                                        | `120`                                                                                     |
| `OPENCV_FFMPEG_CAPTURE_OPTIONS` | FFmpeg capture options read by OpenCV (optional). Use TCP for RTSP to avoid UDP packet loss logged as `RTP: bad cseq` and h264 decode errors.                                                          | `rtsp_transport;tcp`                                                                      |


## Running the Detector

1. **Set Environment Variables:**  Edit the `run_detector.sh` script to configure the necessary environment variables.
2. **Download the model**

Download an off-the-shelf model. Check out the [MediaPipe documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model) for more image classification models that you can use.

```bash
wget  -O efficientdet.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite
wget  -O efficientdet.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite
# this is a  more accurate model than the above
wget  -O efficientdet_lite2.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite
```

3. **Execute the Script:**  Run the script: `./run_detector.sh`
4. **Monitoring:** The script will print status updates to the console.

## Hang protection

Earlier versions used MediaPipe `LIVE_STREAM` mode with a `result_callback`, and after a few hours the process could hang: CPU idle, no new output, Ctrl+C ignored, only `kill` worked. The suspected cause (not confirmed) is the callback, which runs on a MediaPipe-owned thread, deadlocking with `detect_async()` on the main thread over the Python GIL. `mediapipe_detector.py` now:

* Runs detection synchronously in `VIDEO` mode (`detect_for_video`) on a dedicated worker thread, so MediaPipe never calls back into Python.
* Reads frames continuously on the main thread and hands only the latest frame to the worker, so a slow detection never starves the RTSP reader.
* Uses 10 second open/read timeouts on the video stream and reconnects every 5 seconds when reading fails, instead of exiting.
* Arms a `faulthandler` watchdog: if no detection completes within `WATCHDOG_SECONDS`, it prints every thread's stack trace to stderr and exits with code 1. The watchdog runs in C, so it works even if Python threads are deadlocked.
* Prints every thread's stack trace on demand without stopping: `kill -USR1 <pid>`.

To recover automatically after a watchdog exit, restart the detector in a loop in `run_detector.sh` (without `set -e`, or keep the `|| true`):

```bash
while true; do
  ./mediapipe_detector.py || true
  sleep 5
done
```



## Asynchronous Uploads (Optional)

If `GOOGLE_APPLICATION_CREDENTIALS`, `GCS_BUCKET`, and `GCS_FOLDER` are set, annotated images containing detected persons will be asynchronously uploaded to your specified Google Cloud Storage bucket. The upload tasks are managed by a thread pool to avoid blocking the detection worker. The files are organised within the GCS bucket in the format:  `GCS_FOLDER/YYYY-MM-DD/HH/annotated_YYYY-MM-DD_HH-MM-SS.ffffff.png`. Public URL can be generated with `gcp_utils.gcs_path_to_http_url(gs://bucket-name/full/path/to/file.png)`

## Additional Notes

* The script handles `KeyboardInterrupt` to allow clean exit and terminal restoration.
* The script checks whether a person is detected before saving the frame. It also visualises the detections only for the frames being saved to disk, to improve performance.
* Consider tuning `SKIP_X_FRAMES`, `OBJ_DETECT_CONFIDENCE_SCORE`, and `PERSON_DETECT_CONFIDENCE_SCORE` to balance detection accuracy and processing requirements. I've found that `SKIP_X_FRAMES` must be 3 or greater running without GPU and on AMD Ryzen 5 4600G, Ryzen pro threadripper 3945wx. 
* EfficientDet-Lite models are recommended for their performance on edge devices. You can experiment with other models, but ensure they're compatible with TensorFlow Lite. Check [the available models](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model).

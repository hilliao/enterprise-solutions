# Machine learning person detector using Mediapipe library

* **[MediaPipe Models](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/object_detection/python/object_detector.ipynb):** Download a TensorFlow Lite [object detection model](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector).  EfficientDet-Lite models are recommended for their balance of speed and accuracy.  Place the model in your project directory. See `mediapipe_detector.py` for examples.
* **RTSP Stream:**  You'll need access to an RTSP or FFMPEG HTTP/CGI video stream.  The URL, username, and password are configured in environment variables (see below).
* **Output Directory:**  Ensure the output directory (`OUTPUT_IMAGE_DIR`) for saving annotated images exists and is writable.
* **(Optional) Google Cloud Storage:** To enable uploads to GCS, you'll need a GCS bucket and appropriate credentials.

## Configuration

Environment variables are used to configure the script. These are set within the `run_detector.sh` script; the README section at the top of each `run_detector*.sh` lists them too. **Mandatory:** `RTSP_URL`, `TFLITE_MODEL_PATH`, `OUTPUT_IMAGE_DIR`, `OBJ_DETECT_CONFIDENCE_SCORE`, `PERSON_DETECT_CONFIDENCE_SCORE`, plus `GCS_BUCKET` and `GCS_FOLDER` when `GOOGLE_APPLICATION_CREDENTIALS` is set. All others are optional. If a mandatory variable is unset or empty, or `TFLITE_MODEL_PATH`, `OUTPUT_IMAGE_DIR` or `GOOGLE_APPLICATION_CREDENTIALS` does not exist, the detector prints an `Error:` line for each problem and exits with code 1 without restarting.

| Variable | Description                                                                                                                                                                                                        | Example                                                                                   |
|---|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to your Google Cloud service account credentials file (optional).  Required only for GCS uploads.                                                                                                             | `confidential/secrets/person-detection-logger@gcp-project-id.iam.gserviceaccount.com`     |
| `RTSP_URL` | **Mandatory.** URL of the RTSP or FFMPEG HTTP/CGI video stream.                                                                                                                                                                   | `rtsp://user:password@192.168.111.42:554`, http://admin:pass@192.168.123.123:82/video.cgi |
| `TFLITE_MODEL_PATH` | **Mandatory.** Path to the TensorFlow Lite model file.                                                                                                                                                                            | `$HOME/git/enterprise-solutions/googlecloud/ml-person-detector/efficientdet_lite2.tflite` |
| `MAX_WORKERS` | Number of threads for asynchronous GCS uploads (optional, defaults to `auto`: Python's `ThreadPoolExecutor` default for I/O-bound work, the number of CPU threads + 4, at most 32, so 20 on a Ryzen 7 7700X). Keep this number reasonably low (64 or less) to avoid overwhelming the router if also used as edge deployment. | `auto`, `24` |
| `OUTPUT_IMAGE_DIR` | **Mandatory.** Path to the directory where annotated images will be saved.                                                                                                                                                        | `/mnt/1tb/ftp/ipcam/autodelete/person-detector`                                           |
| `SKIP_X_FRAMES` | Number of frames to skip between detections (optional, defaults to `auto`). Higher values reduce processing load. `auto` starts at `3`, then every 10 seconds measures the stream's frame rate and the average time per detection, and skips just enough frames that detection takes at most `DETECTION_DUTY_CYCLE` of the time. A busy CPU or a bigger model makes detection slower, so `auto` skips more frames and leaves the RTSP reader and other detectors their share of the CPU. The status line shows the current value, e.g. `skip 4 (auto)`. | `auto`, `3` |
| `OBJ_DETECT_CONFIDENCE_SCORE` | **Mandatory.** Minimum confidence score for object detection (0.0 - 1.0).                                                                                                                                                         | `0.4`                                                                                     |
| `PERSON_DETECT_CONFIDENCE_SCORE` | **Mandatory.** Minimum confidence score specifically for person detection (0.0 - 1.0).                                                                                                                                            | `0.5`                                                                                     |
| `GCS_BUCKET` | Name of your Google Cloud Storage bucket (mandatory if `GOOGLE_APPLICATION_CREDENTIALS` is set, otherwise unused).                                                                                                                                                               | `bucket-name`                                                                             |
| `GCS_FOLDER` | Folder within the GCS bucket for storing uploaded images (mandatory if `GOOGLE_APPLICATION_CREDENTIALS` is set, otherwise unused).                                                                                                                                               | `us-amcrest-cam-0`                                                                        |
| `IS_GPU` | Set to 1 to use GPU delegation (optional). The script unsets `DISPLAY` so EGL is not routed to a remote-desktop X server. Check the log for `renderer:`; if it shows `llvmpipe`, the "GPU" runs in software on the CPU (slower than `0`), so keep `0`. | `0`                                                                                       |
| `HEARTBEAT_SECONDS` | Report liveness (frame and detection rates, Python and OS thread counts) this often (optional, defaults to `1` on a terminal, `60` otherwise). See [Hang protection](#hang-protection). | `1` |
| `WATCHDOG_SECONDS` | Exit with all thread stack traces on stderr if no detection completes within this many seconds (optional, defaults to `120`). See [Hang protection](#hang-protection).                                        | `120`                                                                                     |
| `DETECTION_DUTY_CYCLE` | Fraction of the time `SKIP_X_FRAMES=auto` lets detection take (optional, defaults to `0.5`). A 30 frames/s camera with EfficientDet-Lite2 on a Ryzen 7 7700X CPU (about 70 ms per detection) gets `skip 4` (6 detections/s); `0.6` gives `skip 3`. | `0.5` |
| `RESTART_RETRIES` | Restart the detector this many times in a row when it fails, e.g. when the watchdog exits it, before giving up (optional, defaults to `5`; `0` disables restarting). See [Automatic restart](#automatic-restart). | `5` |
| `RESTART_BACKOFF_SECONDS` | Wait this long before the first restart, then twice as long before each further one (optional, defaults to `5`, so 5, 10, 20, 40, 80 seconds). See [Automatic restart](#automatic-restart). | `5` |
| `OPENCV_FFMPEG_CAPTURE_OPTIONS` | FFmpeg capture options read by OpenCV (optional). Use TCP for RTSP to avoid UDP packet loss logged as `RTP: bad cseq` and h264 decode errors.                                                          | `rtsp_transport;tcp`                                                                      |


## Running the Detector

1. **Set Environment Variables:**  Copy the `run_detector.sh` template to `run_detector_<camera>.sh` and edit the values; the README section at the top of the script explains each variable. The copies hold the camera password, so keep them out of git.
2. **Download the model**

Download an off-the-shelf model. Check out the [MediaPipe documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model) for more image classification models that you can use.

```bash
wget  -O efficientdet.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/int8/1/efficientdet_lite0.tflite
wget  -O efficientdet.tflite https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/latest/efficientdet_lite0.tflite
# this is a  more accurate model than the above
wget  -O efficientdet_lite2.tflite  https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float32/latest/efficientdet_lite2.tflite
```

3. **Execute the Script:**  Run the script, e.g. `./run_detector_<camera>.sh`. It creates `OUTPUT_IMAGE_DIR` if missing, then replaces itself (`exec`) with the virtual environment's `bin/python` running `mediapipe_detector.py` from the script's folder.
4. **Monitoring:** The script will print status updates to the console.

## Hang protection

Earlier versions used MediaPipe `LIVE_STREAM` mode with a `result_callback`, and after a few hours the process could hang: CPU idle, no new output, Ctrl+C ignored, only `kill` worked. The suspected cause (not confirmed) is the callback, which runs on a MediaPipe-owned thread, deadlocking with `detect_async()` on the main thread over the Python GIL. `mediapipe_detector.py` now:

* Runs detection synchronously in `VIDEO` mode (`detect_for_video`) on a dedicated worker thread, so MediaPipe never calls back into Python.
* Reads frames continuously on the main thread and hands only the latest frame to the worker, so a slow detection never starves the RTSP reader.
* Uses 10 second open/read timeouts on the video stream and reconnects every 5 seconds when reading fails, instead of exiting.
* Arms a `faulthandler` watchdog: if no detection completes within `WATCHDOG_SECONDS`, it prints every thread's stack trace to stderr and exits with code 1. The watchdog runs in C, so it works even if Python threads are deadlocked.
* Prints every thread's stack trace on demand without stopping: `kill -USR1 <pid>`.
* Reports liveness every `HEARTBEAT_SECONDS`, for example `| 2026-10-31 11:53:16 OK | 30.0 frames/s read, 6.0 detections/s, skip 4 (auto) | threads: 3 Python, 35 OS`. On a terminal, this is one status line redrawn in place with a spinning `|/-\` prefix, cut to the terminal width so it never wraps; when output is redirected (e.g. to a log file), a new `Heartbeat ...` line is printed instead. `OK` becomes `STALLED: no detection for N s, ...` after 10 seconds without a completed detection (camera down or detection stuck); when redirected, stalled lines go to stderr as `WARNING: ...`. The heartbeat needs the Python GIL, so if the spinner freezes, Python is stuck and the watchdog fires.
* On Ctrl+C, cleans up and then exits by SIGINT rather than with status 0, so neither the supervisor (see [Automatic restart](#automatic-restart)) nor a calling shell loop such as `while true; do ./run_detector.sh; done` starts a new detector.

When the watchdog fires, stderr shows `Timeout (0:02:00)!` followed by a `Thread 0x... (most recent call first):` block per thread, then the detector process exits with code 1 and is restarted, see [Automatic restart](#automatic-restart). A camera outage longer than `WATCHDOG_SECONDS` also triggers it, because no detection can complete. So does CPU starvation: on 2026-10-29, a 4K YouTube video playing on the same machine slowed the detector until frames/s read fell to 1-3 and the watchdog fired. `SKIP_X_FRAMES=auto` skips more frames when detection slows down, and the supervisor restarts the detector after the watchdog fires. The thread whose stack ends in a lock acquire or a native MediaPipe/OpenCV call is where the hang is.

## Automatic restart

`mediapipe_detector.py` restarts itself after the watchdog exits it, so a shell loop around it is no longer needed. The watchdog has to exit the whole process, because a hung detector may hold the Python GIL, so the script runs the detector in a child process and supervises it:

* When the detector fails (the watchdog fired, it crashed, or it was killed with SIGKILL, e.g. by the out-of-memory killer), the supervisor waits `RESTART_BACKOFF_SECONDS` and starts a new one, doubling the wait after each further failure: 5, 10, 20, 40, then 80 seconds by default. stderr shows, for example, `Supervisor: mediapipe_detector.py exited with code 1; restart 1 of 5 in 5 s`.
* A restarted detector that completes its first detection resets the count, so after a failure hours later the wait starts again at 5 seconds.
* After `RESTART_RETRIES` restarts in a row that failed before their first detection (camera unreachable, wrong password, bad model path), the supervisor gives up and exits with the detector's status. With the defaults, that is about 15 minutes of failures: 6 runs that each last about `WATCHDOG_SECONDS`, plus 155 seconds of waits.
* The detector stops for good, without a restart, when it exits with status 0, on Ctrl+C, and on SIGTERM or SIGHUP, whether sent to the supervisor or the detector. The supervisor passes SIGTERM and SIGHUP on to the detector, and `kill -USR1` too, so stack traces can be printed through either process ID. Each start logs `Supervisor: started mediapipe_detector.py as process <pid>`.
* Missing environment variables are reported before the supervisor starts, so a configuration error is not retried.

Set `RESTART_RETRIES=0` to run the detector in a single process without restarts, as before.

## Asynchronous Uploads (Optional)

If `GOOGLE_APPLICATION_CREDENTIALS`, `GCS_BUCKET`, and `GCS_FOLDER` are set, annotated images containing detected persons will be asynchronously uploaded to your specified Google Cloud Storage bucket. The upload tasks are managed by a thread pool to avoid blocking the detection worker. The files are organised within the GCS bucket in the format:  `GCS_FOLDER/YYYY-MM-DD/HH/annotated_YYYY-MM-DD_HH-MM-SS.ffffff.png`. Public URL can be generated with `gcp_utils.gcs_path_to_http_url(gs://bucket-name/full/path/to/file.png)`

## Additional Notes

* The script handles `KeyboardInterrupt` to allow clean exit and terminal restoration.
* The script checks whether a person is detected before saving the frame. It also visualises the detections only for the frames being saved to disk, to improve performance.
* Consider tuning `SKIP_X_FRAMES`, `OBJ_DETECT_CONFIDENCE_SCORE`, and `PERSON_DETECT_CONFIDENCE_SCORE` to balance detection accuracy and processing requirements. I've found that `SKIP_X_FRAMES` must be 3 or greater running without GPU and on AMD Ryzen 5 4600G, Ryzen pro threadripper 3945wx. `SKIP_X_FRAMES=auto` (the default) adapts to the CPU, camera, and model; on a Ryzen 7 7700X without GPU it settles at 4 for a 30 frames/s camera. 
* EfficientDet-Lite models are recommended for their performance on edge devices. You can experiment with other models, but ensure they're compatible with TensorFlow Lite. Check [the available models](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model).

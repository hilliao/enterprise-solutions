# Machine learning person detector using Mediapipe library

* **MediaPipe Models:** Download a TensorFlow Lite object detection model.  EfficientDet-Lite models are recommended for their balance of speed and accuracy.  Place the model in your project directory. See `mediapipe_detector.py` for examples.
* **RTSP Stream:**  You'll need access to an RTSP video stream.  The URL, username, and password are configured in environment variables (see below).
* **Output Directory:**  Ensure the output directory (`OUTPUT_IMAGE_DIR`) for saving annotated images exists and is writable.
* **(Optional) Google Cloud Storage:** To enable uploads to GCS, you'll need a GCS bucket and appropriate credentials.

## Configuration

Environment variables are used to configure the script. These are set within the `run_detector.sh` script.

| Variable | Description | Example |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to your Google Cloud service account credentials file (optional).  Required only for GCS uploads. | `confidential/secrets/person-detection-logger@gcp-project-id.iam.gserviceaccount.com` |
| `RTSP_URL` | URL of the RTSP video stream. | `rtsp://user:password@192.168.111.42:554` |
| `TFLITE_MODEL_PATH` | Path to the TensorFlow Lite model file. | `$HOME/git/enterprise-solutions/googlecloud/ml-person-detector/efficientdet_lite2.tflite` |
| `MAX_WORKERS` | Number of threads for asynchronous GCS uploads (optional, defaults to the number of processors).  Recommended to keep this number reasonably low to avoid overwhelming the router if also used as edge deployment. | `24` |
| `OUTPUT_IMAGE_DIR` | Path to the directory where annotated images will be saved. | `/mnt/1tb/ftp/ipcam/autodelete/person-detector` |
| `SKIP_X_FRAMES` | Number of frames to skip between detections. Higher values reduce processing load. | `3` |
| `OBJ_DETECT_CONFIDENCE_SCORE` | Minimum confidence score for object detection (0.0 - 1.0). | `0.4` |
| `PERSON_DETECT_CONFIDENCE_SCORE` | Minimum confidence score specifically for person detection (0.0 - 1.0). | `0.5` |
| `GCS_BUCKET` | Name of your Google Cloud Storage bucket (optional). | `bucket-name` |
| `GCS_FOLDER` | Folder within the GCS bucket for storing uploaded images (optional). | `us-amcrest-cam-0` |
| `IS_GPU` | Set to 1 to use GPU delegation (optional). | `1` |


## Running the Detector

1. **Set Environment Variables:**  Edit the `run_detector.sh` script to configure the necessary environment variables.
2. **Execute the Script:**  Run the script: `./run_detector.sh`
3. **Monitoring:** The script will print status updates to the console.



## Asynchronous Uploads (Optional)

If `GOOGLE_APPLICATION_CREDENTIALS`, `GCS_BUCKET`, and `GCS_FOLDER` are set, annotated images containing detected persons will be asynchronously uploaded to your specified Google Cloud Storage bucket. The upload tasks are managed by a thread pool to avoid blocking the main detection process. The files are organised within the GCS bucket in the format:  `GCS_FOLDER/YYYY-MM-DD/HH/annotated_YYYY-MM-DD_HH-MM-SS.ffffff.png`. Public URL can be generated with `gcp_utils.gcs_path_to_http_url(gs://bucket-name/full/path/to/file.png)`

## Additional Notes

* The script handles `KeyboardInterrupt` to allow clean exit and terminal restoration.
* The script checks whether a person is detected before saving the frame. It also visualises the detections only for the frames being saved to disk, to improve performance.
* Consider tuning `SKIP_X_FRAMES`, `OBJ_DETECT_CONFIDENCE_SCORE`, and `PERSON_DETECT_CONFIDENCE_SCORE` to balance detection accuracy and processing requirements. I've found that `SKIP_X_FRAMES` must be 3 or greater running without GPU and on AMD Ryzen 5 4600G, Ryzen pro threadripper 3945wx. 
* EfficientDet-Lite models are recommended for their performance on edge devices. You can experiment with other models, but ensure they're compatible with TensorFlow Lite. Check [the available models](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector#efficientdet-lite2_model).

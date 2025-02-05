# Machine learning person detector using Mediapipe library

* **[MediaPipe Models](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/object_detection/python/object_detector.ipynb):** Download a TensorFlow Lite [object detection model](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector).  EfficientDet-Lite models are recommended for their balance of speed and accuracy.  Place the model in your project directory. See `mediapipe_detector.py` for examples.
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


# Dog Image Detection and Deletion with BLIP VQA

This section provides a comprehensive guide on how to use the provided scripts for dog detection and image deletion. Remember to test the scripts thoroughly and use them responsibly!
This project uses a combination of a Python script (`blip-vqa-dogs.py`) edited from [the Hugging Face BLIP VQA model](https://huggingface.co/Salesforce/blip-vqa-base) and a Bash script (`process_dog_images.sh`) to detect dogs in images and automatically delete images that do not contain any dogs.

## Overview

The system works as follows:

1.  **Bash Script (`process_dog_images.sh`):**
    *   Iterates through all image files in a specified directory (default: `~/Pictures/dogs`).
    *   For each image, it sets the `IMAGE_PATH` environment variable.
    *   Calls the Python script (`blip-vqa-dogs.py`) to analyze the image.
    *   Captures the output of the Python script.
    *   If the last line of the output is "0" (indicating no dogs detected), it deletes the image.

2.  **Python Script (`blip-vqa-dogs.py`):**
    *   Uses the Salesforce BLIP VQA (Visual Question Answering) model from the Hugging Face Transformers library.
    *   Takes an image path and a question as input (from environment variables `IMAGE_PATH` and `QUESTION`).
    *   Asks the model the question "how many dogs are in the picture?".
    *   Prints the model's answer to standard output.
    *   If CUDA (GPU) is available, it utilizes it for faster processing and prints GPU specifications.

## Prerequisites

*   **Python 3.7+**
*   **Bash**
*   **Required Python Packages:**
    ```bash
    pip install transformers Pillow requests torch # packages are in requirements.txt
    ```
*   **(Optional) NVIDIA GPU with CUDA:** For faster processing.

## Files

*   **`blip-vqa-dogs.py`:** The Python script that performs the dog detection using the BLIP VQA model.
*   **`process_dog_images.sh`:** The Bash script that iterates through images, calls the Python script, and deletes images without dogs.
*   **`README.md`:** This file.

## Setup

1.  **Clone the Repository (if applicable):**
    If you obtained this code from a Git repository, clone it to your local machine:
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Install Python Packages:**
    ```bash
    pip install -r requirements.txt 
    ```
    (If a `requirements.txt` file is provided. Otherwise, install the packages listed above manually.)

3.  **Place Images:**
    Place the images you want to process in the `~/Pictures/dogs` directory. You can change this directory in the `process_dog_images.sh` script if needed.

## Usage

1.  **Edit `process_dog_images.sh` (Mandatory to change environment variables):**
    *   Modify the `image_dir` variable if you want to process images in a different directory.
    *   The default question is "how many dogs are in the picture?". You can change the `QUESTION` variable if necessary, but this might require adjustments to the deletion logic in the script.

2.  **Make `process_dog_images.sh` Executable:**
    ```bash
    chmod +x process_dog_images.sh
    ```

3.  **Run the Script:**
    ```bash
    ./process_dog_images.sh
    ```

**Important Notes:**

*   **Deletion is Permanent:** The script permanently deletes files. **Make sure you have backups of any important images before running it.**
*   **Error Handling:** The script includes basic error handling, but you might want to add more robust error handling and logging for production use.
*   **Output:** The script will print output to the console indicating which files are being processed, the model's answer, and whether a file was deleted.
*   **GPU Usage:** If you have a compatible NVIDIA GPU and CUDA is installed, the Python script will automatically use the GPU for faster processing.
*   **Model Accuracy:** The accuracy of the dog detection depends on the BLIP VQA model's performance. It might not be perfect in all cases.

## Customization

*   **Different Question:** You can modify the `QUESTION` variable in `process_dog_images.sh` to ask a different question to the BLIP VQA model. However, you'll also need to adjust the logic that checks the model's answer and decides whether to delete the image.
*   **Different Model:** You can replace the BLIP VQA model in `blip-vqa-dogs.py` with a different vision-language model from the Hugging Face Transformers library. This will likely require code changes in both the Python and Bash scripts.
*   **Different Directory:** Change the `image_dir` in `process_dog_images.sh` to process images in a different location.

## Troubleshooting

*   **"CUDA out of memory":** If you encounter this error, try reducing the batch size (if applicable) or using a smaller model.
*   **"Error deleting image":** Make sure the script has the necessary permissions to delete files in the specified directory. Check for any error messages printed to the console.
*   **"command not found: python":** Ensure that Python 3 is installed and that the `python` command is in your `PATH`. You might need to use `python3` instead of `python` in the Bash script.

# Image Processing with LLaVA and Ollama

This Bash script `run_llm-vl-find-dogs.sh` processes images in a specified directory, uses the LLaVA model (via Ollama) to determine if a dog is present in each image, and moves the image to a different directory if no dog is detected.

## Overview

The script performs the following actions for each image:

1.  **Loads images:** specified by the `base_path` environment variable.
2.  **Queries the LLaVA model:** using `ollama run llava` with a prompt defined in the `PROMPT` environment variable.
3.  **Checks the model's response:** to determine if it contains `dogs: 1` or `dogs: 0`. If no dogs are detected, the image file is deleted.
4.  **Moves the image:** if the model's response does not indicate the presence of a dog, the script moves the image to a directory specified by environment variable `dogs_path`.
5.  **Prints output:** to the console, indicating whether a dog was detected and if the file was moved.

## Prerequisites

*   **Bash:** The script is written in Bash and requires a Bash environment to run.
*   **Ollama:** You must have Ollama installed and configured on your system. Ollama allows you to run large language models locally.
    *   **Installation and Setup:** Follow the instructions on the official Ollama website to install and set up Ollama on your specific operating system: [https://ollama.com/](https://ollama.com/)
    *   **LLaVA Model:** You need to have the LLaVA model installed within Ollama. You can pull it using the following command:
        ```bash
        ollama pull llava
        ```
    *   **Verification:** Before running the script, ensure that you can successfully run the LLaVA model using the following command in your terminal:
        ```bash
        ollama run llava "What's in this image? the image file path: /home/user/Pictures/test-img.png"
        ```
        The output should describe the image. Verify that the image is added to the model for analysis.
*   **jq:** `jq` is a command-line JSON processor, used in the script to parse the output from the `ollama` command. To install `jq`:
    *   **Debian/Ubuntu:** `sudo apt-get update && sudo apt-get install jq`
    *   **macOS (not tested, using Homebrew):** `brew install jq`
    *   **Other systems:** Refer to the jq website for instructions: [https://stedolan.github.io/jq/](https://stedolan.github.io/jq/)

## Environment Variables

The script uses the following environment variables. You'll need to set them according to your needs **before** running the script.
**Important:** Ensure the `MOVE_TO_DIR` directory exists before running the script. You might need to create it manually: `mkdir "$MOVE_TO_DIR"`

*   **`base_path`:** The directory containing the images you want to process (e.g., `~/Pictures/dogs`).
*   **`dogs_path`:** The directory where images without dogs will be moved (e.g., `~/Pictures/no_dogs`). **Make sure this directory exists before running the script.**
*   **`ollama_output`:** The prompt you want to send to the LLaVA model. An example is `"Is there a dog in this image? Answer yes or no."`

## How to Use

1.  **Save the Script:** Save the provided Bash script to a file, for example, `run_llm-vl-find-dogs.sh`.

2.  **Make the Script Executable:**
    ```bash
    chmod +x run_llm-vl-find-dogs.sh
    ```

3.  **Set Environment Variables in the script**

4.  **Run the Script:**
    ```bash
    ./run_llm-vl-find-dogs.sh
    ```
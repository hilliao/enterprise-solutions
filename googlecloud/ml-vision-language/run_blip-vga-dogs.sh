#!/bin/bash
set -e
#set -x
# Directory containing the images
image_dir="$HOME/Pictures/dogs"

# Question to ask the model
export QUESTION="how many dogs are in the picture?"

# Python script name
python_script="blip-vqa-dogs.py"

# Loop through all files in the directory
find "$image_dir" -type f -print0 | while IFS= read -r -d $'\0' image_path; do
  echo "Processing: ${image_path}"

  # Set the current image path as an environment variable
  export IMAGE_PATH="$image_path"

  # Run the Python script and capture the output
  output=$(python "$python_script")

  # Extract the last line of the output
  last_line=$(echo "$output" | tail -n 1)

  # Check if the last line is "0"
  if [[ "$last_line" == "0" ]]; then
    echo "No dogs detected in the image. Deleting ${IMAGE_PATH}..."
    rm "${IMAGE_PATH}"
    if [[ $? -eq 0 ]]; then
      echo "Image deleted successfully."
    else
      echo "Error deleting image ${IMAGE_PATH}."
    fi
  else
    echo "Dogs detected or output is not 0. Image will not be deleted."
    echo "Output was: ${last_line}"
  fi

  # Optionally, print the entire output for debugging
  # echo "Full output:"
  # echo "$output"

  echo "------------------------"
done
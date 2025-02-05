#!/bin/bash

#set -x
set -e

# Initialize the array
file_array=()

# Base path for the images
base_path="$HOME/Pictures/person-detector"
# Destination path for images with dogs
dogs_path="$HOME/Pictures/dogs"
# Create the destination directory if it doesn't exist
mkdir -p "$dogs_path"

# Navigate to the directory
pushd "$base_path/" >/dev/null

# Add all files to the array
file_array=(*)

# Go back to the previous directory
popd >/dev/null

# Loop through the array, but only for a maximum of 10 iterations
counter=0
for file in "${file_array[@]}"; do
  if ((counter >= 9223372036854775807)); then
    break
  fi

  image_path="$base_path/$file"
  ollama_output=$(ollama run llava "how many people and white dogs are in the image? Only Count dogs when you detect a clear and visible white dog in the image; produce a json output like '{\"people\": 1, \"dogs\": 0}'; the output json is in 1 line; the image file path: $image_path" | tr '\n' ' ' | sed 's/.*{\(.*\)}.*$/\1/')
  ollama_output="{ $ollama_output }"
  echo $ollama_output

  # Check if 'dogs' is 0 using jq, handling jq errors
  if output=$(echo "$ollama_output" | jq -e '.dogs'); then
    if [[ "$output" == "0" ]]; then
      # echo "No dogs (dogs == 0)"
      rm -v "$image_path"
    elif [[ "$output" =~ ^[0-9]+$ ]] && ((output > 0)); then
      echo "Dogs found (dogs != 0)"
      mv -v "$image_path" "$dogs_path/"
    fi
  fi

  ((counter++)) || true
done

exit 0

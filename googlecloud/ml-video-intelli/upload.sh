#!/bin/bash
set -e # exit the script when execution hits any error

# The following environment variables are required:
#
# export BASE_DIR=/mnt/1tb/ftp/ipcam/autodelete
# export PROJECT_ID=test-vpc-341
# export GCS_FOLDER_PATH=gs://$PROJECT_ID-vertex-ai/machine-learning/us-home
# export STAGING_DIR=/mnt/1tb/ftp/ipcam/staging
# export GOOGLE_APPLICATION_CREDENTIALS=$HOME/secrets/keyfile.json
# iwatch -r -t "(\.mkv|\.mp4)$" -e moved_to,close_write -c "/mnt/1tb/ftp/hil/upload.sh -p %f -g $GCS_FOLDER_PATH" $BASE_DIR &


while getopts 'p:g:h' opt; do
  case "$opt" in

  p)
    arg="$OPTARG"
    echo "Passed video file path: '${OPTARG}'"
    FILE_PATH=${OPTARG}
    ;;
  g)
    arg="$OPTARG"
    echo "Passed Google Cloud Storage URI path: '${OPTARG}'"
    GCS_URI=${OPTARG}
    ;;

  ? | h)
    echo "Usage: $(basename $0) [-p dir/dir/file_path] [-g gs://project_id-vertex-ai/machine-learning/]"
    exit 1
    ;;
  *)
    echo "Unknown option: $opt" >&2
    exit 1
    ;;
  esac
done
shift "$(($OPTIND - 1))"

if [ -z "$FILE_PATH" ] || [ -z "$GCS_URI" ]; then
  echo "Missing argument to pass input file or gsutil URI. Execute $0 -h to see usage"
  exit 1
fi

echo "filename is '$FILE_PATH'"

if [[ $FILE_PATH == *.mp4 ]] || [[ $FILE_PATH == *.mkv ]]; then
  RENAMED_FILE=$(echo $FILE_PATH | sed 's/\[/_/g' | sed 's/\]/_/g')
  BASE_FILENAME=$(basename $RENAMED_FILE)
  cp -v $FILE_PATH $STAGING_DIR/$BASE_FILENAME
else
  echo "Filename does not end with .mp4 or .mkv: '$FILE_PATH' so abort"
  exit 0
fi

gsutil mv $STAGING_DIR/$BASE_FILENAME $GCS_URI/

nohup $STAGING_DIR/gcp/bin/python3 $STAGING_DIR/detect_people.py \
  --gcs_uri "$GCS_FOLDER_PATH/$BASE_FILENAME" --alarm_status disarmed \
  &> $STAGING_DIR/detect_people.txt &

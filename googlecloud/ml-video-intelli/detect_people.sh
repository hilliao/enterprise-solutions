#!/bin/bash
set -e # exit the script when execution hits any error

# The following environment variables are required:
#
# export BASE_DIR=/mnt/1tb/ftp/ipcam/autodelete
# export PROJECT_ID=test-vpc-341
# export GCS_FOLDER_PATH=gs://$PROJECT_ID-vertex-ai/machine-learning/us-home
# export STAGING_DIR=/mnt/1tb/ftp/ipcam/staging
# export GOOGLE_APPLICATION_CREDENTIALS=$HOME/secrets/keyfile.json
# iwatch -r -t "\.mp4$|\.mkv$" -e moved_to,close_write -c "$STAGING_DIR/detect_people.sh -p %f -g $GCS_FOLDER_PATH" $BASE_DIR &

while getopts 'p:g:cah' opt; do
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
  c)
    echo "Enable video file format validation by using 'ffprobe -i' "
    if ! command -v ffprobe &>/dev/null; then
      echo "command ffprobe could not be found"
      exit 1
    fi
    USE_ffprobe=TRUE
    ;;
  a)
    echo "While executing detect_people.py, set --alarm_status armed; otherwise, default is disarmed"
    IS_ALARM_ARMED=TRUE
    ;;

  ? | h)
    echo "Usage: $(basename $0) [-p dir0/dir1/video_file_path] [-g gs://project_id-vertex-ai/machine-learning] [-c] [-a]"
    echo "-p specifies the full video file path such as /mnt/samsung-1tb/videos/camera-2/recording-12.mp4"
    echo "-g specifies a Google Cloud Storage folder path such as gs://bucket_name/dir1/dir2"
    echo "-c depends on the command ffprobe to check if the file given in -p has a video format. Abort if the detected file has no video content"
    echo "-a sets '--alarm_status armed' to detect_people.py to handle the alarm status"
    exit 0
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

if [ "$USE_ffprobe" = "TRUE" ]; then
  echo "Executing ffprobe to check if the input file has a video format"
  if ! ffprobe -i "$FILE_PATH" &>/dev/null; then
    echo "Failed to detect video file at $FILE_PATH"
    exit 1
  fi
fi

# get rid of [ and ] characters in filenames as they cause gsutil to fail
RENAMED_FILE=$(echo $FILE_PATH | sed 's/\[/_/g' | sed 's/\]/_/g')
BASE_FILENAME=$(basename $RENAMED_FILE)
cp -v $FILE_PATH $STAGING_DIR/$BASE_FILENAME

gsutil mv $STAGING_DIR/$BASE_FILENAME $GCS_URI/

if [ "$IS_ALARM_ARMED" = "TRUE" ]; then
  ALARM_STATUS="armed"
else
  ALARM_STATUS="disarmed"
fi

nohup $STAGING_DIR/gcp/bin/python3 $STAGING_DIR/detect_people.py \
  --gcs_uri "$GCS_FOLDER_PATH/$BASE_FILENAME" --alarm_status $ALARM_STATUS \
  &>$STAGING_DIR/${BASE_FILENAME}_detect_people.txt &

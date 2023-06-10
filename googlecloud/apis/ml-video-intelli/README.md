# Burglar intrusion detection

The solution implements [Google Video Intelligence API](https://cloud.google.com/video-intelligence/docs/annotate-video-command-line)'s
[people detection](https://cloud.google.com/video-intelligence/docs/people-detection) feature to process uploaded video
files and detect human's existence.

## Assumption
The intruders captured in the video files need to be detected as humans. If the intruders dress as a bear, the API can't
detect humans out of the uploaded videos. If the intruders deploy robots to detect and steal items, the API can't detect
them and thus would not trigger the alarm. 

## Dependencies
The program executes on BASH 5 shell. Some syntax depends on BASH version 5.1.16(1).
The development environment was Ubuntu Linux 22.10 with default Desktop environment installed.
Default software packages like Python 3.10 were installed

### iWatch
`iwatch` is used to detect file moved_to and close_write events and execute `detect_people.sh`. To install `iwatch`, execute the
following commands:

```commandline
sudo apt update && sudo apt install iwatch python3.10-venv
```
Confirm the installation and choose `No configuration` in the Postfix configuration screen.

### Google Cloud SDK
Refer to [the gcloud CLI installation page](https://cloud.google.com/sdk/docs/install) to install it.

### TCP IP cameras to generate video files
[Amcrest](https://www.amazon.com/gp/product/B0145OQTPG/ref=ppx_yo_dt_b_search_asin_image?ie=UTF8&psc=1) cameras have
0. features to write to .mp4 files if motion is detected. Final files are renamed to .mp4 from .mp4_; that's why `iwatch`
command watches for the moved_to event.
1. [Motion](https://hilliao.medium.com/webcam-iot-diy-64827dad3e9d) webcams write to the host's `/var/lib/motion` path.
`rsync -av --remove-source-files -e ssh /var/lib/motion/* $USER@$FILE_SERVER:$DEST_DIR/` executes to move the video
files to the file server's $DEST_DIR where iwatch executes and watches over.

A Google Cloud project is required with billing configured to call [Google Video Intelligence API](https://cloud.google.com/video-intelligence/docs/annotate-video-command-line).
Set the project ID as the environment variables during deployment.

## Deploy the solution
### Python3
Clone the code; create a Python virtual environment to install the dependencies; test dependent packages are installed 
and functional. Read the comments in the following code block to install and test the Python dependencies.
```commandline
git clone https://github.com/hilliao/enterprise-solutions.git && \
mkdir $HOME/staging && cd $HOME/staging

python3 -m venv gcp && \
. gcp/bin/activate # this enters into Python's virtual environment

(gcp) pip install -r $HOME/enterprise-solutions/googlecloud/ml-video-intelli/requirements.txt
(gcp) deactivate

# test the installed Python dependencies
gcp/bin/python3
Python 3.10.7 (main, Mar 10 2023, 10:47:39) [GCC 12.2.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from google.cloud import logging
>>> Ctrl+D

# verify there is no error from Python import
```
Do not paste the whole block of code into BASH. Execute line by line and check if execution succeeds. 
### Google Cloud project
0. Create a Cloud Storage bucket in the region closest to the server with all the video files.
1. Create a service account and grant it `Logs Writer` IAM role.
2. Generate a JSON key and store it securely. Assuming it's stored at `$HOME/keyfile.json`
3. Grant `Storage Object Admin` to the service account at the bucket level.

Execute the following command to activate the service account's credentials:
```commandline
gcloud auth activate-service-account --key-file=$HOME/keyfile.json # https://cloud.google.com/sdk/gcloud/reference/auth/activate-service-account

# Verify if the service account is activated. Expect to see the service account in the output
gcloud auth list
```

### BASH Environment Variables
Set the following environment variables
```commandline
head $HOME/enterprise-solutions/googlecloud/ml-video-intelli/detect_people.sh # inspect environment variables to set

export BASE_DIR=$HOME/Videos # is where you want to watch for incoming video files
export PROJECT_ID=***???*** # execute `gcloud config list` to find out or choose a Google cloud project ID 
export GCS_FOLDER_PATH=gs://$PROJECT_ID-vertex-ai/machine-learning/location-0 # the bucket you created in the GCP project to store video files
export STAGING_DIR=$HOME/staging # video files are copied here before sent to the bucket
export GOOGLE_APPLICATION_CREDENTIALS=$HOME/keyfile.json # https://cloud.google.com/docs/authentication/application-default-credentials#GAC
```
BASE_DIR is the directory where the video files are dumped via FTP or SSH. It's recommended to implement a cron job
that deletes files older than a few weeks such as the [Sample script](https://github.com/hilliao/enterprise-solutions/blob/master/python-utils/autodelete.py)
in Python running as root or the user.

### Execute the iwatch command
Configure environment variables in `detect_people.sh`: 
```commandline
# verify gsutil is installed
gsutil --help
cp -v $HOME/enterprise-solutions/googlecloud/ml-video-intelli/* $STAGING_DIR/
```
The following command watches for file events of rename and write on files ending with .mkv or .mp4 under the $BASE_DIR
recursively. The command returns immediately and runs in the background. Don't quit the command line but keep it open.
To test if the file is working properly, move a .mp4|.mkv file to $BASE_DIR or a sub path under it.

```commandline
# make sure the script exists first
ls $STAGING_DIR/detect_people.sh

# command returns immediately. keep the terminal open for checking standard output.
iwatch -r -t "\.mp4$|\.mkv$" -e moved_to,close_write -c "$STAGING_DIR/detect_people.sh -p %f -g $GCS_FOLDER_PATH" $BASE_DIR &
```
`-t` is the argument to set regular expression `(\.mkv|\.mp4)$` for files ending with .mkv or .mp4.
As videos files come, you may see errors from the command standard output and need to debug accordingly.
Grab a .mp4 or .mkv file and copy it to the `$BASE_DIR` as a test.
If no errors observed, open a separate terminal window and execute the following command to check the output from
executing detect_people.py.

```commandline
ls $HOME/staging/*_detect_people.txt
```
#### If no humans are detected, expect to see the following content:

```editorconfig
Processing video for person detection annotations at timeout 300 on uri gs://test-vpc-
341000-vertex-ai/machine-learning/location-test-0/no_humans.mkv

Finished processing.

human detection returned results:
No humans detected
```

#### If humans are detected, expect to see the following content:

```editorconfig
Processing video for person detection annotations at timeout 300 on uri gs://test-vpc-341000-vertex-ai/machine-learning/location-test-0/humans-detected-0.mp4

Finished processing.

Person detected:
Segment: 6.3s to 9.4s
Bounding box:
	left  : 0.0031250000465661287
	top   : 0.23425926268100739
	right : 0.19427083432674408
	bottom: 0.9842592477798462
Attribute name, value at confidence:
	UpperCloth:Yellow at confidence 0.012738533318042755
	UpperCloth:White at confidence 0.10291171073913574
	UpperCloth:TankTop at confidence 0.06126238778233528
	UpperCloth:T-Shirt at confidence 0.15210019052028656
	UpperCloth:Sweater at confidence 0.008961044251918793
	UpperCloth:Suit at confidence 0.011695599183440208
	UpperCloth:Striped at confidence 0.02489546686410904
	UpperCloth:Spotted at confidence 0.013720671646296978
	UpperCloth:ShortSleeve at confidence 0.35860010981559753
	UpperCloth:Shirt at confidence 0.05466344580054283
	UpperCloth:Red at confidence 0.13173207640647888
	UpperCloth:Purple at confidence 0.016767466440796852
	UpperCloth:Plain at confidence 0.577063798904419
	UpperCloth:Plaid at confidence 0.0023696087300777435
	UpperCloth:Orange at confidence 0.005100647918879986
	UpperCloth:NoSleeve at confidence 0.0669323205947876
	UpperCloth:MultiColor at confidence 0.09078216552734375
	UpperCloth:LongSleeve at confidence 0.32198596000671387
	UpperCloth:Jacket at confidence 0.03936340659856796
	UpperCloth:Green at confidence 0.01875496655702591
	UpperCloth:Gray at confidence 0.041187088936567307
	UpperCloth:Graphics at confidence 0.025139475241303444
	UpperCloth:Floral at confidence 0.019468633458018303
	UpperCloth:Dress at confidence 0.027285832911729813
	UpperCloth:Coat at confidence 0.007535507436841726
	UpperCloth:Brown at confidence 0.0015650998102501035
	UpperCloth:Blue at confidence 0.03575363755226135
	UpperCloth:Black at confidence 0.44896525144577026
	LowerCloth:ShortSkirt at confidence 0.011821413412690163
	LowerCloth:ShortPants at confidence 0.03609020635485649
...
```
## Edit the code to include other video filename extensions
The following code block in `detect_people.py` filters on the .mp4 and .mkv file extensions. You can add more file
extensions in the if statement to include more filename extensions. This is in addition to the `iwatch` `-t` regular
expression filter.
```python
if [[ $FILE_PATH == *.mp4 ]] || [[ $FILE_PATH == *.mkv ]]; then
  RENAMED_FILE=$(echo $FILE_PATH | sed 's/\[/_/g' | sed 's/\]/_/g')
  BASE_FILENAME=$(basename $RENAMED_FILE)
  cp -v $FILE_PATH $STAGING_DIR/$BASE_FILENAME
else
  echo "Filename does not end with .mp4 or .mkv: '$FILE_PATH' so abort"
  exit 0
fi
```

## Verify and tune the detection results
`detect_people.sh` passed to iwatch command defaults to `--alarm_status disarmed` if `-a` is not passed. Execute
`detect_people.sh -h` to see usage.

If any humans were detected, Google Cloud Console logging page would show the logged entries. Use the following filter
to find the logs:
```jql
jsonPayload.is_alarm_armed="false"
```
The severity is `Notice`. If you edit detect_people.sh and set `--alarm_status armed`, the logs can be found with filter:
```jql
jsonPayload.is_alarm_armed="true"
severity=WARNING
```
Otherwise, use the following filter to find logs:
```jql
human_detection_outcome
```
You can create [log based alerts](https://cloud.google.com/logging/docs/alerting/log-based-alerts) to notify those who
may care such as the hired security guards.

## Known issues
1. Amcrest video file moved_to event is ignored: the `iwatch` command would not capture Amcrest IP camera's move 
file event from *.mp4_ to *.mp4 after certain depth of directories and after certain number of hours.
Execute a cron job to move *.mp4 files to higher levels of directories to circumvent the problem.
For example, the directories for 2 Amcrest cameras are 
`/mnt/640g/ftp/ipcam/autodelete/amcrest/office/AMC057C6_8F4709/[date]/[hour]/mp4` and
`/mnt/640g/ftp/ipcam/autodelete/amcrest/entrance/AMC057C8_943B45/[date]/[hour]/mp4`,
execute the following commands to move *.mp4 to their higher level directories.
```shell
$ find /mnt/640g/ftp/ipcam/autodelete/amcrest/office/AMC057C6_8F4709/ -name *.mp4 -exec mv -v {} /mnt/640g/ftp/ipcam/autodelete/amcrest/office/ \;
$ find /mnt/640g/ftp/ipcam/autodelete/amcrest/entrance/AMC057C8_943B45/ -name *.mp4 -exec mv -v {} /mnt/640g/ftp/ipcam/autodelete/amcrest/entrance/ \;
```

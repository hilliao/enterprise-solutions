#!/usr/bin/python3
# Python variables to change: LOG_FILENAME, parentdir, week
# Bash variables to change: $WORKING_DIR: the directory where files and folders are deleted, STDOUT_TXT: .txt output of what's deleted
#
# Copy autodelete.py to /usr/local/bin/
# chmod a+x /usr/local/bin/autodelete.py
#
# Example crontab
# 0 3 * * * export WORKING_DIR=/mnt/disk_dir/ftp/autodelete && STDOUT_TXT="$WORKING_DIR/autodelete.txt" && /usr/local/bin/autodelete.py > $STDOUT_TXT 2>&1 && echo "Finding and deleting empty directories..." >> $STDOUT_TXT && find $WORKING_DIR/can-be-deleted -type d -empty -delete -print >> $STDOUT_TXT 2>&1
import time, glob, os, logging, sys

### SET mandatory environment variables ###

# Get the value of the WORKING_DIR environment variable.
parentdir = os.getenv("WORKING_DIR")
# delete files and directories over 1 week
week = 60 * 60 * 24 * 7
LOG_FILENAME = f"{parentdir}/autodelete.log"

### NOT Necessary to modify code below ###

# Check if the environment variable is set.
if parentdir is None:
    print("Error: The WORKING_DIR environment variable is not set.", file=sys.stderr)  # Print to stderr for errors
    sys.exit(1)  # Exit with a non-zero status code (1 indicates an error)

# fresh start of log file
if os.path.isfile(LOG_FILENAME):
    os.remove(LOG_FILENAME)
logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG)
# dir without trailing slash /

for filename in glob.glob(os.path.join(parentdir, '**'), recursive=True):
    # skip the directory itself
    if filename == parentdir + '/':
        continue

    timediff = time.time() - os.path.getmtime(filename)
    logging.debug(filename + ' is ' + str(timediff) + ' seconds old')

    if (timediff > week):
        try:
            if os.path.isfile(filename):
                print('deleting ' + filename)
                os.remove(filename)
            # report directories without files in them
            if os.path.isdir(filename):
                if not os.listdir(filename):
                    print('empty dir: ' + filename)
                    # os.rmdir(filename)
        except OSError as err:
            print("OS error deleting " + filename + ": {0}".format(err))

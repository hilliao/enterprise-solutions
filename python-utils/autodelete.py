#!/usr/bin/python3
# Python variables to change: LOG_FILENAME, parentdir, week
# Bash variables to change: $WORKING_DIR: the directory where files and folders are deleted, STDOUT_TXT: .txt output of what's deleted
#
# Copy autodelete.py to /usr/local/bin/
# chmod a+x /usr/local/bin/autodelete.py
#
# Example crontab
# 0 3 * * * STDOUT_TXT=/var/log/autodelete.txt && WORKING_DIR=/mnt/disk_dir/ftp/autodelete && /usr/local/bin/autodelete.py > $STDOUT_TXT 2>&1 && echo "Finding and deleting empty directories..." >> $STDOUT_TXT && find $WORKING_DIR -type d -empty -delete -print >> $STDOUT_TXT 2>&1 && mkdir -p $WORKING_DIR
import time, glob, os, logging

# fresh start of log file
LOG_FILENAME = '/var/log/autodelete.log'
if os.path.isfile(LOG_FILENAME):
    os.remove(LOG_FILENAME)
logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG)
# dir without trailing slash /
parentdir = '$WORKING_DIR'

for filename in glob.glob(os.path.join(parentdir, '**'), recursive=True):
    # skip the directory itself
    if filename == parentdir + '/':
        continue

    timediff = time.time() - os.path.getmtime(filename)
    logging.debug(filename + ' is ' + str(timediff) + ' seconds old')
    # delete files and directories over 1 week
    week = 60 * 60 * 24 * 7

    if (timediff > week):
        try:
            if os.path.isfile(filename):
                print('deleting ' + filename)
                os.remove(filename)
            # delete directories without files in them
            if os.path.isdir(filename):
                if not os.listdir(filename):
                    print('deleting ' + filename)
                    os.rmdir(filename)
        except OSError as err:
            print("OS error deleting " + filename + ": {0}".format(err))

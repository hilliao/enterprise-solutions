#!/usr/bin/python3
# Example crontab 0 3 * * * /home/hil/autodelete.py > /home/hil/autodelete.txt 2>&1 && echo "Finding and deleting empty directories..." >> /home/hil/autodelete.txt && find /mnt/1tb/ftp/hil -type d -empty -delete -print >> /home/hil/autodelete.txt 2>&1 && chown hil:hil /home/hil/autodelete.log && chown hil:hil /home/hil/autodelete.txt
import time, glob, os, logging

# fresh start of log file
LOG_FILENAME = '/home/hil/autodelete.log'
if os.path.isfile(LOG_FILENAME):
    os.remove(LOG_FILENAME)
logging.basicConfig(filename=LOG_FILENAME, level=logging.DEBUG)
# dir without trailing slash /
parentdir = '/mnt/1tb/ftp/hil'

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

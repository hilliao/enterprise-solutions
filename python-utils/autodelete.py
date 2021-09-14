#!/usr/bin/python3
#
# crontab does not support $HOME
# replace $_HOME with /root, $WORKING_DIR with the directory to auto delete
# Copy autodelete.py to $_HOME/bin
# chmod a+x $_HOME/bin/autodelete.py
#
# Example crontab
# 0 3 * * * $_HOME/bin/autodelete.py > $_HOME/bin/autodelete.txt 2>&1 && echo "Finding and deleting empty directories..." >> $_HOME/bin/autodelete.txt && find $WORKING_DIR -type d -empty -delete -print >> $_HOME/bin/autodelete.txt 2>&1
# (date && df -h && tail $_HOME/bin/autodelete.txt $_HOME/bin/autodelete.log) | txt2html > /var/www/html/autodelete.html # make the html writeable for the current user and txt2html is installed
import time, glob, os, logging

# fresh start of log file
LOG_FILENAME = '$_HOME/bin/autodelete.log'
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

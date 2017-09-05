#!/usr/bin/python3
import time, glob, os, logging

# fresh start of log file
LOG_FILENAME = '/home/hil/autodelete.log'
if os.path.isfile(LOG_FILENAME):
  os.remove(LOG_FILENAME)
logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)
parentdir = '/mnt/1tb/ftp/hil'

for filename in glob.glob(os.path.join(parentdir, '**'), recursive=True):
  # skip the directory itself
  if filename == '/mnt/1tb/ftp/hil/':
    continue
  
  timediff = time.time() - os.path.getmtime(filename)
  logging.debug(filename + ' is ' + str(timediff) + ' seconds old')
  # delete files and directories over 1 week
  week = 60*60*24*7
  if(timediff>week):
    # print('deleting ' + filename)
    try:
      if os.path.isfile(filename):
        print('deleting ' + filename)
        os.remove(filename)
      if os.path.isdir(filename):
        if not os.listdir(filename):
          print('deleting ' + filename)
          os.rmdir(filename)
    except OSError as err:
      print("OS error deleting " + filename + ": {0}".format(err))

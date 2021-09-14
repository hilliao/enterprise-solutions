import re
import os
import signal

# netstat -tulpn | grep LISTEN > netstat.log
file_openports = open("netstat.log", "r")
openport_str = file_openports.readlines()

for openport in openport_str:
    if 'sshd' not in openport:
        openport = openport.rstrip()
        found = re.match("(.+)(LISTEN      )(\d+)/(.+)", openport)

        if found:
            pid = int(found.group(3))
            print(f"identified process ID is {pid} for '{openport}'")
            os.kill(pid, signal.SIGTERM)

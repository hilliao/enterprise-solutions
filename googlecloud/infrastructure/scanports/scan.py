#!/usr/bin/env python
# sudo apt update
# sudo apt install python3-pip
# pip3 install --upgrade python-nmap
# sudo apt-get install nmap
#
# sample output: hosts scanned: ['10.128.0.2', '10.128.0.3']
# host 10.128.0.2 has TCP ports running: {22: {'state': 'open', 'reason': 'syn-ack', 'name': 'ssh', 'product': 'OpenSSH', 'version': '7.9p1 Ubuntu 10', 'extrainfo': 'Ubuntu Linux; protocol 2.0', 'conf': '10', 'cpe': 'cpe:/o:linux:linux_kernel'}, 80: {'state': 'open', 'reason': 'syn-ack', 'name': 'http', 'product': '', 'version': '', 'extrainfo': '', 'conf': '3', 'cpe': ''}}
# host 10.128.0.3 has TCP ports running: {22: {'state': 'open', 'reason': 'syn-ack', 'name': 'ssh', 'product': 'OpenSSH', 'version': '7.4p1 Debian 10+deb9u7', 'extrainfo': 'protocol 2.0', 'conf': '10', 'cpe': 'cpe:/o:linux:linux_kernel'}}


import nmap

if __name__ == "__main__":
    nm = nmap.PortScanner()
    nm.scan('10.128.0.0/20', '20-88')  # scan the IP range on TCP port 20-88
    print('hosts scanned: {}'.format(nm.all_hosts()))
    for host in nm.all_hosts():
        print('host {} has TCP ports running: {}'.format(host, nm[host]['tcp']))

import urllib3
import time
import sys

url_nordstrom = 'http://shop.nordstrom.com/s/fresh-mask-ritual-complexion-kit-limited-edition-89-value/4493367?origin=keywordsearch-personalizedsort'
initialPrice = 89


def downloadContent(url):
    http = urllib3.PoolManager()
    response = http.request('GET', url)
    if response.status != 200:
        return response.status

    return str(response.data)


timeLapsed = int(0)
sleepInterval = 3600
while (True):

    content = downloadContent(url_nordstrom)
    if '$' + str(initialPrice) in content:
        print('price has not change at ' + str(timeLapsed) + ' second\r', end="")
        sys.stdout.flush()
        timeLapsed += sleepInterval
        time.sleep(sleepInterval)
    else:
        print('Either price changed or HTTP status != 200')
        if isinstance(content, int):
            print('HTTP status code is ' + str(content))
            exit(content)
        else:
            print('content or price changed! Check url manually for lower price alert')
            exit(0)

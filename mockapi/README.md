# Mock REST API in Python3
There are powerful Mock API services like https://apiary.io/ out there. But all the Mock API services require active and stable Internet connection. Developers still suffer from connection latency. This project is to host a localhost Mock API that returns a json file in the response.

## Getting Started

Linux, Mac OS computer with Python > 3.5 can easily run and deploy the Mock API with a few commands. Have a directory of .json files ready for use with Mock API.

### Prerequisites

Latest Flask is recommended; pipenv is recommended to install Flask.

```
sudo -H pip3 install pipenv
```
You may debug with JetBrains Pycharm which should install all the dependencies.

### Installing

Clone the repository first. Then run the commands below. Fix errors before running the next command.

```
pipenv install
pipenv shell
python3 mockapi.py
```

## Running the tests

The last command should give you the output similar to 

```
hil@xeon:~/github/PlayTest/mockapi$ python3 mockapi.py 
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```
Browse to http://127.0.0.1:5000/ and you'd expect to see 404 not found. That's good. The web server has started. If you see something else like 500, you may have to check the console output or debug with Pycharm. Submit a bug report or contact me if that happens.
Grab a .json file and put it at path like /home/hil/tmp/excursions.json; set the query string f to the path:

```
http://127.0.0.1:5000/?f=/home/hil/tmp/excursions.json
```
You should see the json file from the browser or Postman. I tested with a json file of 1 MB. The response time is 111ms on [my computer](https://browser.geekbench.com/v4/cpu/4525863)

## Deployment

Deployment of the Mock API has not been tested. I suppose it's possible to put it in a Docker container and deploye to Kubernetes. The container needs to map to a path of .json files for the Mock API to read from.


This project is licensed under the [Apache license 2.0](https://www.apache.org/licenses/LICENSE-2.0)

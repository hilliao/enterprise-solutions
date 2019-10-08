# Build

## with Google Cloud Platform cloud build

gcloud builds submit --tag gcr.io/**$YOUR_PROJECT_ID**/rainbow:**$TAG**
.

## locally

docker build -t localhost/rainbow:**$TAG** .

# Debug in Pycharm
Create a new flask server in the debug configuration. choose
target type: script, target: primarysponsor/views.py, check FLASK_DEBUG.

# debug URL

http://127.0.0.1:5000/tickets/10-10-2019?reg-token=eyJtZXNzYWdlIjoiaGVsbG8gd29ybGQifQ==&overlay_font_px=12

## Test Dockerfile
run the command to point to host port 5001 to container port 5000
assuming 5001 is unused.
 
docker run --detach --name tmp -p 5001:5000 localhost/rainbow:**$TAG**

# Deploy

mkdir ~/static # create a static dir to put images of format
**MM-DD-YYYY**

docker run -d -p 80:5000 -v $HOME/static:/app/primarysponsor/static
--name=test gcr.io/**$YOUR_PROJECT_ID**/rainbow:**$TAG**
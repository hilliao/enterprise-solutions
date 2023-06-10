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

http://127.0.0.1:5000/tickets/10-10-2019?reg-token=ewogICJmaXJzdF9uYW1lIjogImZpcnN0IG5hbWUiLAogICJsYXN0X25hbWUiOiAibGFzdCBuYW1lIiwKICAicGhvbmUiOiAiMTIzLTQ1Ni03ODkwIiwKICAic2VhdCI6IDQ1Cn0=&overlay_font_px=22

## Test Dockerfile
run the command to point to host port 5001 to container port 5000
assuming 5001 is unused.
 
docker run --detach --name **$container_name** -p 5001:5000 localhost/rainbow:**$TAG**

# Deploy

mkdir ~/static # create a static dir to put images of format
**MM-DD-YYYY**

docker run -d -p 80:5000 -v $HOME/static:/app/primarysponsor/static
--name=**$container_name** gcr.io/**$YOUR_PROJECT_ID**/rainbow:**$TAG**

Sample deployment at
http://oracle0.techsightteam.com/tickets/10-10-2019?reg-token=ewogICJmaXJzdF9uYW1lIjogImZpcnN0IG5hbWUiLAogICJsYXN0X25hbWUiOiAibGFzdCBuYW1lIiwKICAicGhvbmUiOiAiMTIzLTQ1Ni03ODkwIiwKICAic2VhdCI6IDQ1Cn0=&overlay_font_px=22
where reg-token query string value is the base64 encoded string and
overlay_font_px is the font size.
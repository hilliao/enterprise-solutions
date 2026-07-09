# GoogleCloud.fr static website served by nginx.
#
# The site is plain HTML/CSS/JS — no build step. nginx:alpine serves
# everything copied into /usr/share/nginx/html on port 80.
#
# Build locally (run from this html/ directory):
#   docker build -t googlecloud-fr .
#
# Run locally and browse to http://localhost:8080 :
#   docker run --rm -d -p 8080:80 --name html googlecloud-fr
#
# CI/CD: cloudbuild.yaml (in this directory) builds this image with the
# build context set to the html/ folder, pushes it to Artifact Registry
# ($_LOCATION-docker.pkg.dev/$PROJECT_ID/$_REPOSITORY/$_IMAGE), then
# deploys it over SSH to the web server as a container named "html"
# published on port 80. Trigger it from the repository root:
#   gcloud builds submit --config html/cloudbuild.yaml \
#     --substitutions=_LOCATION=<region>,_REPOSITORY=<repo>,_IMAGE=<image>,_SSH_WEB_SERVER=<user@host>
FROM nginx:alpine
COPY . /usr/share/nginx/html

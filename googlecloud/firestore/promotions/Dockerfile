# Use the official Python image at https://hub.docker.com/_/python
FROM python:3.9
# IMAGE=us-central1-docker.pkg.dev/$PROJECT_ID/helloworld-docker-repo/hil-promo-dev:0.1 && \
# docker build . -t $IMAGE && \
# docker push $IMAGE && \
# gcloud run deploy hil-promo --image $IMAGE --region us-central1 --platform managed \
#      --no-allow-unauthenticated --memory 512M --project $PROJECT_ID \
#      --update-env-vars FIRESTORE_PROJECT_ID=$PROJECT_ID --update-env-vars PROJECT_ID=$PROJECT_ID
# docker run -d -p 5001:5000 --name promo -e PORT=5000 -e BASIC_AUTH=auth_token -e PROJECT_ID=$PROJECT_ID -e FIRESTORE_PROJECT_ID=$PROJECT_ID $IMAGE

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . .

# Install cloud run production dependencies.
RUN pip install gunicorn
# install app dependencies
RUN pip install -r requirements.txt

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 api:app
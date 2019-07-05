# Use the official Python image at https://hub.docker.com/_/python
FROM python:3.7

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . .

# Install cloud run production dependencies.
RUN pip install gunicorn
# install app dependencies
RUN pip install -r requirements.txt

# Run the web service on container startup. use the gunicorn webserver
# tested with one worker process and 8 threads.
# For Cloud run on GKE environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 api:app
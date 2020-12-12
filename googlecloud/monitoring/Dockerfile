FROM python:3.8

# Copy local code to the container image.
ENV APP_HOME monitoring
COPY . /$APP_HOME
WORKDIR /$APP_HOME

# Install production dependencies.
RUN pip install gunicorn
RUN pip install -r requirements.txt
RUN pip install google-cloud-monitoring --upgrade

CMD exec gunicorn --bind :$PORT --workers 4 --threads 20 gke_cpu:app
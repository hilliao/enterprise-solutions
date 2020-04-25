FROM python:3.7-slim

# Copy local code to the container image.
ENV APP_HOME gsakey
COPY . /$APP_HOME
WORKDIR /$APP_HOME

# Install production dependencies.
RUN pip install gunicorn
RUN pip install -r requirements.txt

CMD exec gunicorn --bind :$PORT --workers 4 --threads 20 managekey:app
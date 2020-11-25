FROM python:3.7-slim

# Copy local code to the container image
ENV APP_HOME oauth2py
COPY . /$APP_HOME
WORKDIR /$APP_HOME

# Install production dependencies
RUN pip install gunicorn
RUN pip install -r requirements.txt

ENV OAUTHLIB_INSECURE_TRANSPORT 1

CMD exec gunicorn --bind :$PORT --workers 4 --threads 20 oauth2:app
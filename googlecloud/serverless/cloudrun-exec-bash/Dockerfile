# docker build $PATH -t $CONTAINER-cloud-run:$TAG
# docker run --name $CONTAINER -d -p 127.0.0.1:81:8080 --env PORT=8080  $CONTAINER-cloud-run:$TAG
# test with http://localhost:81

FROM gcr.io/google.com/cloudsdktool/cloud-sdk:latest

RUN apt update && apt install -y sshpass

# Copy local code to the container image
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install & Configure Python dependencies
ENV PYTHONUNBUFFERED True
RUN apt install python3-pip -y
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir -r requirements.txt
RUN python3 -V
RUN pip --version

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app

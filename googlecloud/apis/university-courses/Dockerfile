FROM python:3.9-slim-buster

# Set working directory
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy your Python application files
COPY . /app

# Set environment variable
ENV DB_PASSWORD 'pass at run time'
ENV DB_HOST "pass at deployment time"

# Expose port 5002
EXPOSE 5002

# Run the Flask app
CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0", "--port=5002"]


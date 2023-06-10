FROM python:3.7

COPY ./requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
RUN pip install gunicorn
COPY ./primarysponsor /app/primarysponsor
WORKDIR /app/primarysponsor
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "views:app", "--workers 16"]

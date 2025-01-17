FROM python:3.10

WORKDIR /app

COPY requirements.txt /app
RUN pip install -r requirements.txt

RUN mkdir logs

COPY src /app/src
COPY logging.json /app
COPY launcher.py /app

CMD ["python3", "launcher.py"]
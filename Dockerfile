FROM python:3.10 AS deps

WORKDIR /app

COPY requirements.txt /app
RUN pip install -r requirements.txt

FROM python:3.10-alpine3.21 AS runtime

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app

RUN mkdir logs && chown -R appuser:appgroup /app/logs

COPY src /app/src
COPY logging.json /app
COPY launcher.py /app
COPY --from=deps /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages

USER appuser

CMD ["python3", "launcher.py"]

FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir flask

CMD ["python", "/app/run.sh"]

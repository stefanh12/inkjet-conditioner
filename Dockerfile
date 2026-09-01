FROM python:3.12-slim

WORKDIR /app
COPY . /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEBUI_PORT=8000 \
    WEBUI_USERNAME=admin \
    APPDATA_DIR=/config \
    DOCUMENTS_DIR=/share \
    OPTIONS_PATH=/config/options.json

RUN apt-get update \
    && apt-get install -y --no-install-recommends cups-client cups-daemon \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir flask zeroconf

VOLUME ["/config", "/share"]

EXPOSE 8000/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('WEBUI_PORT', '8000') + '/healthz', timeout=3); exit(0 if response.status == 200 else 1)"

CMD ["sh", "/app/run.sh"]

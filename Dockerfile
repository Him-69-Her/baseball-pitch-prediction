FROM python:3.11-slim
WORKDIR /app

ENV PIP_ROOT_USER_ACTION=ignore
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY app.py cloudsql_api.py chain_api.py openadr_vtn.py \
     smart_meter.py fraud_detection.py websocket_handler.py \
     vnm_reporting.py ./
COPY district91_buildings.json district91_names.json ./
COPY templates/ ./templates/
COPY docker-entrypoint-cloudrun.sh .
RUN chmod +x docker-entrypoint-cloudrun.sh

ENTRYPOINT ["./docker-entrypoint-cloudrun.sh"]
CMD exec gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:${PORT:-8080} app:app

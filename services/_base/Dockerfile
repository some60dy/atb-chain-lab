# Shared base for all Python ATB lab services.
# Build once:  docker build -t atb-base:latest -f services/_base/Dockerfile .
# (build context = repo root, so we can copy services/_lib)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 ATB_LOG_DIR=/var/log/atb

RUN pip install --no-cache-dir flask==3.0.3 requests==2.32.3 \
        pymysql==1.1.1 psycopg2-binary==2.9.9 cryptography==43.0.1 \
    && mkdir -p /var/log/atb /app

COPY services/_lib/atblog.py /app/atblog.py
ENV PYTHONPATH=/app
WORKDIR /app

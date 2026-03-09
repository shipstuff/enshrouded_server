FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY tools/probes /app/probes
COPY tools/services/api /app/services/api

USER 10000:10000

ENTRYPOINT ["python3", "/app/services/api/live_stats_api.py"]

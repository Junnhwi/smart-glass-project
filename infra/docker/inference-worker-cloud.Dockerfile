FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY apps/inference-server/requirements-cloud.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/inference-server /app

CMD ["celery", "-A", "src.queue.tasks", "worker", "--loglevel=info", "-P", "solo"]

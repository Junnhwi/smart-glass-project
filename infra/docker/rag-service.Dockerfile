FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY apps/rag-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/rag-service /app

RUN mkdir -p /app/data

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

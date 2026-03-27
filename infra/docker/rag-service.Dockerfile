FROM python:3.12-slim

WORKDIR /app

COPY apps/rag-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/rag-service /app

CMD ["python", "-m", "http.server", "8000"]

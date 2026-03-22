# PyTorch와 CUDA가 설치된 공식 이미지 사용
FROM pytorch/pytorch:2.2.1-cuda12.1-cudnn8-runtime

WORKDIR /app

# 시스템 의존성 설치 (이미지 처리를 위한 libgl1 등)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Celery 워커 실행 명령
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-P", "solo"]
# PyTorch 2.6.0 기반의 최신 이미지 사용
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

WORKDIR /app

# 이미지 처리에 필요한 시스템 라이브러리 설치
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 설치 (torch는 이미 포함되어 있으므로 제외)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Celery 워커 실행 (GPU 충돌 방지를 위해 -P solo 사용)
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info", "-P", "solo"]
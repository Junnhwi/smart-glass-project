import os

os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")

from src.queue.tasks import process_vision_inference

print(f"Broker: {os.environ['CELERY_BROKER_URL']}")

result = process_vision_inference.delay("test01.jpg", "ghpark_01")

print(f"✅ 작업 전송 완료! Task ID: {result.id}")
print("이제 Docker 로그 창을 확인해 보세요.")

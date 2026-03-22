# test_task.py
from tasks import process_vision_inference

# 비동기적으로 워커에게 작업 요청 (S3 파일명, 사용자 ID)
result = process_vision_inference.delay("test01.jpg", "ghpark_01")

print(f"✅ 작업 전송 완료! Task ID: {result.id}")
print("이제 Docker 로그 창을 확인해 보세요.")
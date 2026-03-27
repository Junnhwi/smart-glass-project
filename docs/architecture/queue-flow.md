# Queue Flow

1. API 서버가 추론 요청을 큐에 적재합니다.
2. `apps/inference-server`의 Celery 워커가 작업을 가져옵니다.
3. 워커가 S3에서 이미지를 가져와 모델 추론을 수행합니다.
4. 결과를 API 서버 또는 저장소로 반환합니다.

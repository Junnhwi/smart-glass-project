# Queue Flow

1. API 서버가 추론 요청을 큐에 적재합니다.
2. `apps/inference-server`의 Celery 워커가 작업을 가져옵니다.
3. 워커는 raw boto3 client 대신 `src.storage.s3`의 `StorageService` 경계를 통해 이미지를 읽습니다.
4. `api-server`는 `captures/{userId}/{yyyy}/{mm}/{dd}/{captureId}-{fileName}` 구조로 object key를 생성하거나 명시적 `imageKey`를 정규화합니다.
5. 로컬 업로드/스모크 스크립트도 같은 `StorageService`를 통해 이미지를 업로드합니다.
6. `StorageService`가 object storage client 생성, 기본 bucket 해석, 예외 매핑을 담당합니다.
7. 워커는 받은 이미지 바이트로 모델 추론을 수행하고 결과를 반환합니다.

Object key 세부 규칙은 [object-storage-keys.md](./object-storage-keys.md)에 정리되어 있습니다.

## Operational Logs

`process_vision_inference` emits structured JSON logs through
`apps/inference-server/src/core/logging.py`.

Successful task logs include request and model context such as:

- `request_id`
- `image_key`
- `memory_id`
- `user_id`
- `model_key`
- `model_mode`
- `quantization`
- `settings_source`
- `soft_time_limit_sec`
- `hard_time_limit_sec`
- `fallback_model_key`
- `fallback_triggered`
- `latency_sec`
- `peak_memory_mb`

Failure and retry logs add operational decision fields:

- `error_code`
- `retryable`
- `failure_category`
- `retry_count`
- `max_retries`
- `retry_delay_sec`

Logs intentionally avoid storage credentials, raw image bytes, prompts, and
access URLs.

```mermaid
flowchart LR
  A["POST /tasks/vision"] --> B["Celery queue"]
  B --> C["process_vision_inference"]
  C --> D["get_storage_service()"]
  D --> E["StorageService.read_object(image_key)"]
  E --> F["Object storage client get_object(...)"]
  F --> G["image bytes + content type"]
  G --> H["PIL image decode"]
  H --> I["caption / VLM inference"]
  I --> J["VlmInferenceResult"]

  K["upload_local_image_to_s3.py"] --> L["StorageService.write_object(...)"]
  M["smoke_qwen_e2e.py"] --> L
  L --> N["Object storage client put_object(...)"]
```

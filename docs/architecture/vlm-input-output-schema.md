# VLM Input/Output Schema

## 목적

`VLM 입출력 스키마 정의` 백로그의 현재 결정사항을 정리합니다.

이번 단계의 목표는 최종 캡셔닝 모델을 확정하는 것이 아니라, 모델이 바뀌어도 유지할 수 있는 공통 계약을 먼저 고정하는 것입니다.

즉, 아래 3가지를 우선 달성합니다.

- inference worker가 downstream으로 넘기는 결과 형태를 표준화
- RAG 적재 계층이 받을 최소 안정 필드를 정의
- 모델별 편차와 실험용 메타데이터를 코어 계약과 분리

## 배경

현재 저장소에는 이미 아래 흐름의 초안이 존재합니다.

- 이미지가 S3에 저장됨
- Celery worker가 비동기로 이미지 추론 수행
- 추론 결과 일부가 캡션 중심으로 반환됨
- RAG 서비스는 `MemoryRecordPayload` 중심으로 메모리를 적재하고 검색함

하지만 모델이 아직 연구 중이기 때문에, 지금 시점에 특정 모델 출력 형식을 그대로 계약으로 고정하면 이후 교체 비용이 커집니다.

그래서 이번 결정은 아래 원칙을 따릅니다.

- `caption`, `positionHint`는 공통 안정 계약으로 본다
- `detectedObjects`, `tags`는 structured metadata capability가 있는 경로에서 안정 필드로 본다
- `sceneSummary`, `ocrText`, `location`은 스키마에는 두되 capability가 있을 때만 적극적으로 소비한다
- provider 고유 정보는 `providerMetadata`로 격리한다
- 원시 응답은 기본 저장하지 않는다

## 이번에 확정한 범위

### 1. 공통 VLM 결과 계약

공용 타입은 아래 파일에 정리했습니다.

- [packages/shared-types/src/inference/index.ts](/home/ghpark/projects/smart-glass-project/packages/shared-types/src/inference/index.ts)

핵심 타입:

- `VlmInferenceRequest`
- `VlmInferenceResult`
- `VlmInferenceSuccess`
- `VlmInferenceError`

성공 결과는 아래 구조를 기준으로 합니다.

```ts
interface VlmInferenceSuccess {
  status: "success";
  requestId: string;
  taskType: "caption" | "metadata";
  memoryId?: string | null;
  userId: string;
  capturedAt: string | null;
  sourceImage: {
    imageKey?: string | null;
    imageUrl?: string | null;
    contentType?: string | null;
  };
  metadata: {
    caption: string | null;
    sceneSummary: string | null;
    detectedObjects: string[];
    tags: string[];
    ocrText: string | null;
    positionHint: string | null;
    location: {
      name?: string | null;
      address?: string | null;
      latitude?: number | null;
      longitude?: number | null;
    } | null;
  };
  providerMetadata: {
    capabilities?: {
      caption?: boolean;
      positionHint?: boolean;
      sceneSummary?: boolean;
      detectedObjects?: boolean;
      tags?: boolean;
      ocrText?: boolean;
      location?: boolean;
      pipelineOutput?: boolean;
    } | null;
    executionPolicy?: {
      settingsSource?: string | null;
      profilePath?: string | null;
      selectedModelKey?: string | null;
      softTimeLimitSec?: number | null;
      hardTimeLimitSec?: number | null;
      fallbackModelKey?: string | null;
      fallbackTriggered?: boolean | null;
    } | null;
    modelKey?: string | null;
    modelId?: string | null;
    modelFamily?: string | null;
    quantization?: string | null;
    dtype?: string | null;
    provider?: string | null;
    raw?: Record<string, unknown> | null;
  };
  runtime: {
    latencySec?: number | null;
    peakMemoryMb?: number | null;
    loadTimeSec?: number | null;
  };
}
```

### 2. inference worker 반환값 정렬

아래 파일에서 Celery worker 반환 형식을 `VlmInferenceResult`에 맞췄습니다.

- [apps/inference-server/src/queue/tasks.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/queue/tasks.py)
- [apps/inference-server/src/contracts/vlm.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/contracts/vlm.py)

변경 전:

- `status`
- `caption`
- `model_key`
- `quantization`
- `latency_sec`
- `peak_memory_mb`

변경 후:

- 성공/실패 모두 `requestId`, `userId`, `memoryId`, `capturedAt`, `sourceImage` 유지
- 캡션 결과는 `metadata.caption`으로 이동
- 모델/런타임 정보는 `providerMetadata`, `runtime`으로 분리
- 실행 정책 정보는 `providerMetadata.executionPolicy`로 분리
- 오류도 동일한 컨텍스트를 유지한 채 `errorCode`, `message`, `retryable` 반환
- timeout 및 storage 실패도 같은 오류 계약 위에서 구분 가능한 코드로 정리
- metadata는 caption/Qwen 경로와 무관하게 같은 키 집합과 값 형태로 정규화

### 3. RAG 적재 어댑터 추가

아래 파일에서 `VlmInferenceResult -> MemoryRecordPayload` 변환 어댑터를 추가했습니다.

- [apps/rag-service/src/ingestion/vlm_adapter.py](/home/ghpark/projects/smart-glass-project/apps/rag-service/src/ingestion/vlm_adapter.py)

현재 어댑터 정책:

- `status == success`인 결과만 적재 가능
- `memoryId`, `userId`는 필수
- 안정 계약 필드만 `MemoryRecordPayload`로 매핑
- `providerMetadata`는 적재 payload로 넘기지 않음

## 핵심 설계 결정

### 모델 미확정 상태에서도 스키마를 먼저 정의한 이유

지금 필요한 것은 "최종 모델의 출력 문장 형식"이 아니라 "시스템 경계에서 어떤 의미 단위를 주고받을지"를 정하는 것입니다.

모델이 바뀌어도 유지되어야 하는 것은 아래입니다.

- 어떤 이미지에 대한 결과인지
- 어떤 사용자/메모리에 속하는지
- 검색 가능한 최소 텍스트 단서가 무엇인지
- 어떤 모델 설정으로 생성됐는지
- 재시도/장애 분석이 가능한지

반대로 아직 고정하면 안 되는 것은 아래입니다.

- bbox, polygon, mask
- provider별 원시 응답 형태
- 모델 고유 prompt format
- 후처리되지 않은 object label 배열

### 안정 계약으로 유지할 필드

최종 모델 선정 전까지는 아래만 안정 계약으로 유지합니다.

- 모든 경로 공통:
  - `caption`
  - `positionHint`
- structured metadata capability가 있는 경로:
  - `detectedObjects`
  - `tags`

의도는 명확합니다.

- `caption`: 검색/RAG의 가장 기본 텍스트 단서
- `detectedObjects`: 이후 detector가 붙어도 계속 유지될 개념
- `tags`: 검색 친화적인 정규화 필드
- `positionHint`: "책상 옆", "서랍 안" 같은 공간 단서

### 결과 payload 정규화 규칙

이번 단계에서 result contract는 아래 규칙을 따릅니다.

- 성공 결과의 `metadata`는 항상 같은 핵심 키를 모두 포함합니다.
  - `caption`
  - `sceneSummary`
  - `detectedObjects`
  - `tags`
  - `ocrText`
  - `positionHint`
  - `location`
- 문자열 필드는 공백을 정리하고, 의미 없는 빈 문자열은 `null`로 낮춥니다.
- `detectedObjects`, `tags`는 중복과 빈 값을 제거한 배열로 정규화합니다.
- `positionHint`가 비어 있으면 `caption` 기반 규칙 추출로 보완합니다.
- `location`은 `name`, `address`, `latitude`, `longitude`를 정규화한 뒤 모두 비어 있으면 `null`로 반환합니다.

의도:

- 모델 구현체가 일부 키를 빼먹거나 값 형태가 조금 달라도, 시스템 경계에서는 더 안정된 payload를 보장합니다.
- downstream은 "어떤 키가 있을지"보다 "그 키의 의미가 무엇인지"에 집중할 수 있습니다.

### `providerMetadata.raw` 저장 정책

기본 정책은 `저장하지 않음`입니다.

이유:

- provider raw 응답은 크기가 커질 수 있음
- 모델 교체 시 구조가 자주 바뀜
- 저장소와 검색 인덱스를 오염시킬 수 있음
- 운영 로그/적재 payload에 민감 정보가 섞일 수 있음

현재 구현은 아래 환경변수를 켰을 때만 소형 디버그 정보만 포함합니다.

```bash
VISION_PROVIDER_METADATA_INCLUDE_RAW=true
```

현재 raw에 들어가는 값:

- `device`
- `prompt`

즉, "디버깅을 위한 opt-in 메타"이지, 기본 계약 필드는 아닙니다.

## 기본 실패 / timeout 정책

현재 inference worker는 실패를 아래처럼 최소 구분합니다.

- `source_image_not_found`
- `storage_config_error`
- `storage_access_error`
- `invalid_source_image`
- `invalid_inference_request`
- `inference_timeout`
- `model_runtime_error`
- `inference_task_error`

의도:

- 상위 서비스가 재시도 가치가 있는 실패와 즉시 사용자/운영자 개입이 필요한 실패를 구분할 수 있게 합니다.
- `retryable`은 Celery 자동 재시도 설정이 아니라, 제품 계층이 후속 정책을 정할 때 쓰는 힌트입니다.
- timeout은 worker task 경계에서 기본 soft/hard limit로 다루며, 현재 기본값은 `120초 / 150초`입니다.

### `providerMetadata.capabilities` 계약

이번 단계부터는 `providerMetadata.capabilities`를 통해 “이 모델/경로가 어떤 필드를 책임질 수 있는지”를 함께 내려보냅니다.

예시:

- caption 경로
  - `caption: true`
  - `positionHint: true`
  - `sceneSummary: false`
  - `ocrText: false`
  - `location: false`
- Qwen VLM 경로
  - `caption: true`
  - `positionHint: true`
  - `sceneSummary: true`
  - `detectedObjects: true`
  - `tags: true`
  - `pipelineOutput: true`

이 값의 목적은 아래 두 상태를 구분하는 것입니다.

- 미지원이라서 비어 있음
- 지원하지만 이번 이미지에서 값이 비어 있음

### `providerMetadata.executionPolicy` 계약

이번 단계부터는 `providerMetadata.executionPolicy`를 통해 “어떤 실행 정책으로 이 결과가 생성됐는지”를 함께 내려보냅니다.

핵심 필드:

- `settingsSource`
  - `env`
  - `profile`
  - `legacy_default`
  - preload 경로에서는 `preload_env`
- `profilePath`
- `selectedModelKey`
- `softTimeLimitSec`
- `hardTimeLimitSec`
- `fallbackModelKey`
- `fallbackTriggered`

의도:

- worker result만 보고도 어떤 source에서 모델 설정이 왔는지 알 수 있게 합니다.
- fallback이 실제로 발동했는지 로그가 아닌 payload 수준에서 추적할 수 있게 합니다.
- health/preload/result가 같은 정책 언어를 쓰도록 맞춥니다.

## 현재 구현 상태

### inference worker

- API 경유 요청에서는 enqueue 단계에서 이미 해석된 `requestId`를 worker가 그대로 받음
- worker direct call 또는 비-API 경로에서는 `requestId`가 없으면 worker가 UUID 기반으로 생성
- `positionHint`는 caption에서 단순 규칙 기반으로 추출
- `detectedObjects`, `tags`는 현재 빈 배열 기본값
- `sceneSummary`, `ocrText`, `location`은 현재 `None`

이 상태는 의도된 보수적 구현입니다.

지금은 모델이 확정되지 않았기 때문에, 잘못된 의미를 가진 필드를 억지로 채우는 것보다 빈 값으로 유지하는 편이 안전합니다.

### RAG 적재 어댑터

현재 어댑터는 아래만 적극 매핑합니다.

- `memory_id`
- `user_id`
- `image_key`
- `image_url`
- `captured_at`
- `caption`
- `detected_objects`
- `tags`
- `position_hint`

아래는 일부러 비워 둡니다.

- `scene_summary` (capability가 있을 때만)
- `ocr_text` (capability가 있을 때만)
- `location` (capability가 있을 때만)
- `note`

## 검증 결과

### 코드/테스트

통과:

- `git diff --check`
- `PYTHONPATH=apps/rag-service python3 -m unittest apps/rag-service/tests/test_vlm_adapter.py`
- `PYTHONPATH=apps/inference-server python3 -m py_compile apps/inference-server/src/contracts/vlm.py apps/inference-server/src/queue/tasks.py`
- `PYTHONPATH=apps/rag-service python3 -m py_compile apps/rag-service/src/ingestion/vlm_adapter.py`

제약:

- inference 단위테스트는 작성했지만 로컬 실행 환경에 `Pillow`가 없어 직접 실행은 못 했습니다.

### Docker 빌드

실제 Compose 기반 이미지 빌드 성공:

- `docker compose -f infra/compose/docker-compose.local.yml build rag-service inference-api`
- `docker compose -f infra/compose/docker-compose.local.yml build inference-worker`

즉, 현재 변경사항은 컨테이너 빌드 경로 기준으로는 문제 없습니다.

## 이번 단계에서 하지 않은 것

아래는 일부러 이번 범위에서 제외했습니다.

- API 서버와 worker/RAG를 실제로 연결하는 orchestration
- `providerMetadata.raw`의 저장소 적재
- object detection 결과 병합
- OCR 결과 병합
- 위치 추론 고도화
- bbox/grounding 스키마 확정

이 부분은 팀 정책과 모델 선정 방향을 더 논의한 뒤 이어가는 것이 맞습니다.

## 남은 액션

다음 단계 후보는 아래 순서가 현실적입니다.

1. API 서버에서 worker 결과를 받아 `vlm_adapter`로 RAG 적재 연결
2. detector/OCR이 붙는 시점에 capability 정의와 함께 `detectedObjects`, `tags`, `ocrText` 채우기
3. 위치 추론 후처리와 capability 분리 방식 강화
4. 모델 최종 선정 후 `sceneSummary`와 optional metadata 사용 범위 재검토

## 참고 파일

- 공통 타입: [packages/shared-types/src/inference/index.ts](/home/ghpark/projects/smart-glass-project/packages/shared-types/src/inference/index.ts)
- API 계약 문서: [docs/architecture/api-spec.md](/home/ghpark/projects/smart-glass-project/docs/architecture/api-spec.md)
- worker 계약 포맷터: [apps/inference-server/src/contracts/vlm.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/contracts/vlm.py)
- worker task: [apps/inference-server/src/queue/tasks.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/queue/tasks.py)
- RAG 어댑터: [apps/rag-service/src/ingestion/vlm_adapter.py](/home/ghpark/projects/smart-glass-project/apps/rag-service/src/ingestion/vlm_adapter.py)
- 캡셔닝 벤치마크 문서: [docs/architecture/caption-model-benchmarking.md](/home/ghpark/projects/smart-glass-project/docs/architecture/caption-model-benchmarking.md)

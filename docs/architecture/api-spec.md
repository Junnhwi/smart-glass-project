# API Spec

## 목적

API 서버, inference worker, RAG 적재 계층 사이에서 비전-언어 모델(VLM) 결과를 주고받을 때 사용할 공통 계약을 정리합니다.

현재 캡셔닝 모델은 연구 중이므로, 아래 스키마는 `모델 고정`이 아니라 `모델 교체 가능`을 전제로 설계합니다.

## 지금 정의해도 되는 범위

아래 필드는 현 저장소 기준으로 이미 실제 코드 경로가 있거나, 바로 그 위에 얹을 수 있는 안정 필드입니다.

- 요청 식별자: `requestId`
- 소유자/메모리 식별자: `userId`, `memoryId`
- 이미지 참조: `imageKey`, `imageUrl`
- 촬영 시각: `capturedAt`
- 텍스트 결과: `caption`, `sceneSummary`, `ocrText`, `positionHint`
- 검색 보조 메타데이터: `detectedObjects`, `tags`, `location`
- 운영 메타데이터: `modelKey`, `quantization`, `dtype`, `latencySec`, `peakMemoryMb`
- 실패 정보: `errorCode`, `message`, `retryable`

반대로 아래는 아직 모델 연구 단계이므로 공용 계약의 필수 필드로 고정하지 않습니다.

- bbox, polygon, mask 같은 정밀 시각 grounding
- token logprob, hidden state, attention map 같은 모델 내부 산출물
- 특정 모델만 가지는 prompt template 규칙
- provider별 원시 응답 전체 구조

이런 값은 `providerMetadata.raw` 같은 확장 필드에 넣고, 다운스트림 저장/검색 계약에서는 의존하지 않는 것이 안전합니다.

## 공유 타입 위치

- 공통 타입: [packages/shared-types/src/inference/index.ts](/home/ghpark/projects/smart-glass-project/packages/shared-types/src/inference/index.ts)
- 현재 inference task 구현: [apps/inference-server/src/queue/tasks.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/queue/tasks.py)
- 현재 RAG 적재 스키마: [apps/rag-service/src/api/schemas.py](/home/ghpark/projects/smart-glass-project/apps/rag-service/src/api/schemas.py)

## 스키마 원칙

1. 코어 검색 필드는 모델과 무관해야 합니다.
2. 모델별 차이는 `providerMetadata`와 `generation`으로 격리합니다.
3. `caption`은 자유 텍스트로 저장하고, 문장 형식 자체를 계약으로 강제하지 않습니다.
4. `detectedObjects`, `tags`는 검색 친화적인 정규화 결과를 담고, 모델 출력 원문 배열을 그대로 계약화하지 않습니다.
5. 실패 응답도 동일한 식별자와 이미지 참조를 유지해 재처리와 추적이 가능해야 합니다.

## 요청 추적 규칙

- `POST /tasks/vision`에서 클라이언트가 `requestId`를 보내면 그 값을 그대로 사용합니다.
- 클라이언트가 `requestId`를 보내지 않으면 API 미들웨어가 생성한 `x-request-id` / `request.state.request_id`를 inference 요청 식별자로 재사용합니다.
- 이 값은 Celery task kwargs, worker 로그, 최종 `VlmInferenceResult.requestId`로 그대로 전파됩니다.
- `taskId`는 polling 식별자이고, `requestId`는 end-to-end correlation id입니다.

## VLM 입력 스키마

```ts
interface VlmInferenceRequest {
  requestId: string;
  taskType: "caption" | "metadata";
  memoryId?: string | null;
  userId: string;
  capturedAt?: string | null;
  sourceImage: {
    imageKey?: string | null;
    imageUrl?: string | null;
    contentType?: string | null;
  };
  generation?: {
    modelKey?: string;
    quantization?: "none" | "8bit" | "4bit";
    dtype?: "float16" | "bfloat16" | "float32";
    prompt?: string | null;
    maxNewTokens?: number;
    numBeams?: number;
  };
}
```

설계 의도:

- `sourceImage`는 S3 key 기반 처리와 외부 URL 기반 처리 둘 다 수용합니다.
- `generation.modelKey`는 실험 모델 선택에 쓰되, 없으면 서버 기본값을 사용합니다.
- `taskType`은 지금은 캡셔닝 중심이지만, 이후 OCR/scene metadata 조합 작업으로 확장할 수 있게 둡니다.

## VLM 출력 스키마

```ts
type VlmInferenceResult = VlmInferenceSuccess | VlmInferenceError;

interface VlmInferenceSuccess {
  status: "success";
  requestId: string;
  taskType: "caption" | "metadata";
  memoryId?: string | null;
  userId: string;
  sourceImage: {
    imageKey?: string | null;
    imageUrl?: string | null;
    contentType?: string | null;
  };
  metadata: {
    caption?: string | null;
    sceneSummary?: string | null;
    detectedObjects: string[];
    tags: string[];
    ocrText?: string | null;
    positionHint?: string | null;
    location?: {
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

```ts
interface VlmInferenceError {
  status: "error";
  requestId: string;
  taskType: "caption" | "metadata";
  memoryId?: string | null;
  userId: string;
  sourceImage: {
    imageKey?: string | null;
    imageUrl?: string | null;
    contentType?: string | null;
  };
  errorCode: string;
  message: string;
  retryable?: boolean;
  providerMetadata?: {
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
    modelKey?: string | null;
    modelId?: string | null;
    modelFamily?: string | null;
    quantization?: string | null;
    dtype?: string | null;
    provider?: string | null;
    raw?: Record<string, unknown> | null;
  };
}
```

## 비동기 태스크 API

### `POST /tasks/vision`

- 목적: 비전 추론 작업 enqueue
- 응답: `202 Accepted`

```ts
interface VisionInferenceEnqueueResponse {
  taskId: string;
  state: string;
  requestId: string;
}
```

의도:

- `taskId`: `GET /tasks/{taskId}` polling 식별자
- `requestId`: HTTP -> Celery -> worker -> result 전체를 묶는 correlation id

### `GET /tasks/{taskId}`

- 목적: 비전 추론 작업 상태 확인

```ts
interface VisionInferenceTaskStatusResponse {
  taskId: string;
  state: string;
  ready: boolean;
  successful: boolean;
  resultStatus?: "success" | "error" | null;
  requestId?: string | null;
  result?: VlmInferenceResult | null;
  error?: string | null;
  taskStatus: "pending" | "running" | "completed" | "failed";
}
```

의도:

- 작업 완료 후에는 `result.requestId`와 같은 값을 top-level `requestId`에서도 바로 확인할 수 있습니다.
- 작업 미완료 상태에서는 `requestId`가 아직 없을 수 있습니다.
- `state`는 raw Celery 상태를 유지하고, `taskStatus`는 제품 관점 정규화 상태를 뜻합니다.
- `resultStatus`는 결과 payload가 있을 때 실제 inference outcome(`success` / `error`)을 보여줍니다.
- worker가 에러 payload를 정상 반환한 경우에도 polling 응답은 `taskStatus: "failed"`와 `successful: false`로 정규화됩니다.

## 현재 코드와의 대응

- inference worker는 이미 `caption`, `model_key`, `quantization`, `latency_sec`, `peak_memory_mb`를 반환합니다.
  - 참고: [apps/inference-server/src/queue/tasks.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/queue/tasks.py)
- RAG 적재 스키마는 이미 `caption`, `scene_summary`, `detected_objects`, `tags`, `ocr_text`, `position_hint`, `location`을 받습니다.
  - 참고: [apps/rag-service/src/api/schemas.py](/home/ghpark/projects/smart-glass-project/apps/rag-service/src/api/schemas.py)

즉, 지금 필요한 것은 새 필드를 마구 늘리는 것이 아니라, 이미 존재하는 저장/검색 필드를 기준으로 inference 결과를 정렬하는 일입니다.

## Capability 계약

`providerMetadata.capabilities`는 현재 inference 경로가 어떤 의미 필드를 책임질 수 있는지 선언합니다.

- `caption`, `positionHint`: 현재 시스템에서 안정적으로 기대하는 공통 필드
- `sceneSummary`, `ocrText`, `location`: capability가 있을 때만 downstream이 적극적으로 신뢰해야 하는 필드
- `pipelineOutput`: 디버그/실험성 구조화 payload 지원 여부

의도:

- 빈 값과 미지원 상태를 구분합니다.
- downstream이 optional field를 무조건 저장하거나 무조건 버리지 않게 합니다.
- 모델 변경 시에도 field ownership을 한 곳에서 관리할 수 있게 합니다.

## 운영 관점 권장사항

- DB나 벡터스토어에는 `metadata`의 안정 필드만 1차 저장합니다.
- `providerMetadata.raw`는 기본값으로 저장하지 않습니다. 현재 구현은 `VISION_PROVIDER_METADATA_INCLUDE_RAW=true`일 때만 `device`, `prompt` 같은 소형 디버그 필드만 포함합니다.
- 모델 변경 시에도 `caption`, `positionHint` 의미가 유지되도록 post-processing 계층을 둡니다.
- `sceneSummary`, `ocrText`, `location`은 `providerMetadata.capabilities`를 확인한 뒤 저장/검색에 반영합니다.
- 재처리를 위해 `requestId`, `memoryId`, `imageKey`, `modelKey` 조합은 반드시 로그에 남깁니다.

## 결론

지금은 "최종 모델이 없으니 스키마를 미루는 단계"가 아니라, "모델-독립 코어 스키마를 먼저 고정하고 모델별 편차는 확장 필드로 격리하는 단계"로 보는 것이 맞습니다.

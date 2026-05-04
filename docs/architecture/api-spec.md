# API Spec

## Purpose

This document describes the current API contract between:

- `api-server`
- `inference-server`
- PostgreSQL-backed memory storage inside `api-server`

There is no separate search service in the default application flow anymore.

## Capture Flow

1. A client uploads the original image to object storage.
2. The client registers the capture with `POST /media/captures`.
3. `api-server` dispatches the inference worker.
4. The worker returns a normalized VLM result.
5. `api-server` stores the normalized memory document in PostgreSQL.

When capture upload and inference are owned by another team, steps 1-4 can
happen outside `api-server`. In that integration mode, the external pipeline
posts the final successful VLM result to `POST /memories/inference-results`.

## Main Endpoints

### `POST /media/captures`

Registers a captured image, runs the inference worker, and persists the result when memory storage is enabled.

Relevant request fields:

- `captureId`
- `requestId`
- `memoryId`
- `userId`
- `taskType`
- `capturedAt`
- `fileName`
- `imageKey`
- `imageUrl`
- `contentType`
- `sourceImage`
- `generation`

Relevant response sections:

- `capture`
- `worker`
- `memoryStore`

### `POST /memories/inference-results`

Stores a successful VLM result that was produced by an external
device/storage/inference pipeline.

This endpoint is the stable handoff contract from the inference side to the
memory/search/chat side. It does not upload images and does not run inference;
it only validates the result payload and persists the normalized memory
document in PostgreSQL.

Required request fields:

- `status: "success"`
- `requestId`
- `taskType: "caption" | "metadata"`
- `memoryId`
- `userId`
- `capturedAt`
- `sourceImage.imageKey`
- `metadata`

Canonical request example:

```json
{
  "status": "success",
  "requestId": "req-earbuds-001",
  "taskType": "metadata",
  "memoryId": "mem-earbuds-001",
  "userId": "user-1",
  "capturedAt": "2026-04-30T09:00:00Z",
  "sourceImage": {
    "imageKey": "captures/user-1/2026/04/30/cap-earbuds.jpg",
    "imageUrl": null,
    "contentType": "image/jpeg"
  },
  "metadata": {
    "caption": "earbuds on the desk next to the laptop",
    "sceneSummary": "desk scene with earbuds",
    "detectedObjects": ["earbuds", "desk", "laptop"],
    "tags": ["earbuds", "workspace"],
    "ocrText": null,
    "positionHint": "next to laptop",
    "location": {
      "name": "workspace",
      "address": null,
      "latitude": null,
      "longitude": null
    }
  },
  "pipelineOutput": {
    "scene_summary": "desk scene with earbuds",
    "location_context": "workspace",
    "objects": [
      {
        "name": "earbuds",
        "nearby_objects": ["laptop"],
        "visual_features": {
          "brand": null,
          "color": null,
          "text": null
        }
      }
    ]
  },
  "providerMetadata": {
    "modelKey": "qwen2.5-vl-7b",
    "modelId": "Qwen/Qwen2.5-VL-7B-Instruct",
    "modelFamily": "qwen-vl",
    "quantization": "4bit",
    "dtype": "float16",
    "provider": "huggingface-transformers",
    "capabilities": {
      "detectedObjects": true,
      "tags": true,
      "positionHint": true,
      "sceneSummary": true,
      "ocrText": true,
      "location": true
    }
  },
  "runtime": {
    "latencySec": 1.25,
    "peakMemoryMb": 512.0,
    "loadTimeSec": 0.4
  }
}
```

Response:

```json
{
  "status": "stored",
  "memoryId": "mem-earbuds-001",
  "userId": "user-1",
  "imageKey": "captures/user-1/2026/04/30/cap-earbuds.jpg",
  "capturedAt": "2026-04-30T09:00:00Z",
  "storedCount": 1,
  "totalUserMemories": {
    "user-1": 3
  }
}
```

### `POST /search`

Searches stored memories for one user.

Request:

```json
{
  "userId": "user-1",
  "query": "my wallet",
  "topK": 5
}
```

The endpoint also accepts the legacy snake_case aliases:

```json
{
  "user_id": "user-1",
  "query": "my wallet",
  "top_k": 5
}
```

Response fields:

- `query`
- `totalHits`
- `hits[]`

Each hit includes:

- `memoryId`
- `score`
- `lexicalScore`
- `matchedTerms`
- `imageKey`
- `imageUrl`
- `capturedAt`
- `caption`
- `sceneSummary`
- `positionHint`
- `location`
- `detectedObjects`
- `tags`

### `POST /chat`

Builds a grounded answer from the current search results.

Request:

```json
{
  "userId": "user-1",
  "query": "where was my wallet?",
  "topK": 3
}
```

Response fields:

- `answer`
- `answerMode`
- `query`
- `totalHits`
- `hits[]`
- `citedMemoryIds`
- `confidence`
- `reason`

The current default answer mode is template-based and does not require a separate LLM service.

## VLM Result Contract

The worker result is normalized around:

- `status`
- `requestId`
- `taskType`
- `memoryId`
- `userId`
- `capturedAt`
- `sourceImage`
- `metadata`
- `pipelineOutput`
- `providerMetadata`
- `runtime`

For memory ingestion, only successful results are accepted. Error payloads
remain useful for worker diagnostics, but they are not persisted as searchable
memories.

Error results keep `errorCode`, `message`, and `retryable` for backward
compatibility, and also include `errorDetails` for diagnostics. The detail
payload carries a stable failure category, normalized reason, exception type,
retryability, source, and task time-limit values when available.
Runtime diagnostics now keep the model-reported `latencySec` and may also
include worker-measured `queueWaitSec`, `storageReadSec`, `imageDecodeSec`,
`modelInferenceSec`, and `taskLatencySec`. Error results may include the same
runtime object when the worker recorded partial timings before the failure.

Current reference files:

- [apps/inference-server/src/contracts/vlm.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/contracts/vlm.py)
- [apps/inference-server/src/queue/tasks.py](/home/ghpark/projects/smart-glass-project/apps/inference-server/src/queue/tasks.py)
- [apps/api-server/src/api/schemas.py](/home/ghpark/projects/smart-glass-project/apps/api-server/src/api/schemas.py)
- [apps/api-server/src/database/memory_store.py](/home/ghpark/projects/smart-glass-project/apps/api-server/src/database/memory_store.py)

## Storage Notes

- Original images stay in object storage.
- Capture image object keys use the canonical `captures/{userId}/{yyyy}/{mm}/{dd}/{captureId}-{fileName}` shape.
- Explicit `imageKey` values are normalized and validated before worker dispatch or signed URL generation.
- Normalized memory documents are stored in PostgreSQL as JSONB.
- Search is currently based on recent-history retrieval plus keyword/location matching.
- A separate vector database is not part of the default architecture.
- Detailed key policy: [object-storage-keys.md](./object-storage-keys.md)

# API Spec

## Purpose

This document describes the current API contract between:

- `api-server`
- `inference-server`
- PostgreSQL-backed memory storage inside `api-server`

There is no separate search service in the default application flow anymore.

## Capture Flow

1. A client requests `POST /media/upload-authorizations` with `deviceId` and upload metadata.
2. `api-server` validates `deviceId`, resolves `userId`, and returns a direct-upload plan with a canonical `imageKey` plus a presigned PUT `uploadUrl`.
3. The client uploads the original image to object storage using the returned `uploadUrl`.
4. The client registers the capture with `POST /media/captures` using the same `deviceId`, `userId`, and `imageKey`.
5. `api-server` dispatches the inference worker.
6. `api-server` returns `202 Accepted` with the Celery `taskId`.
7. The client polls `GET /media/captures/tasks/{taskId}`.
8. When the worker result is ready, `api-server` reads the normalized VLM
   result from the result backend and stores the memory document in PostgreSQL.

When capture upload and inference are owned by another team, steps 1-4 can
happen outside `api-server`. In that integration mode, the external pipeline
posts the final successful VLM result to `POST /memories/inference-results`.

## Main Endpoints

### `POST /media/upload-authorizations`

Validates a registered `deviceId` and prepares the direct-upload object key and
presigned PUT URL that the client should use for object storage upload.

Relevant request fields:

- `deviceId`
- `captureId`
- `requestId`
- `memoryId`
- `taskType`
- `capturedAt`
- `fileName`
- `imageKey`
- `contentType`

Allowed response sections:

- `status`
- `deviceId`
- `userId`
- `upload`

Allowed response example:

```json
{
  "status": "allowed",
  "deviceId": "glass-001",
  "userId": "user-1",
  "upload": {
    "method": "direct",
    "captureId": "capture-001",
    "requestId": "req-001",
    "memoryId": "mem-001",
    "taskType": "metadata",
    "capturedAt": "2026-05-05T02:00:00Z",
    "uploadUrl": "https://storage.example.com/signed-put/captures/user-1/2026/05/05/capture-001-photo.png",
    "expiresAt": "2026-05-05T02:05:00Z",
    "expiresInSec": 300,
    "sourceImage": {
      "imageKey": "captures/user-1/2026/05/05/capture-001-photo.png",
      "imageUrl": null,
      "contentType": "image/png",
      "fileName": "photo.png"
    }
  }
}
```

Blocked response example:

```json
{
  "status": "blocked",
  "deviceId": "glass-999",
  "userId": null,
  "upload": null
}
```

### `POST /media/captures`

Registers a captured image, enqueues the inference worker, and returns
immediately with `202 Accepted`.

Relevant request fields:

- `captureId`
- `requestId`
- `memoryId`
- `userId`
- `deviceId`
- `taskType`
- `capturedAt`
- `fileName`
- `imageKey`
- `imageUrl`
- `contentType`
- `sourceImage`
- `generation`

Relevant response sections:

- `taskId`
- `capture`
- `worker`

Response example:

```json
{
  "status": "accepted",
  "service": "api-server",
  "taskId": "4f2a6c0d-8d7e-4b35-9f5b-8a1b4d1f2c30",
  "capture": {
    "status": "accepted",
    "service": "api-server",
    "captureId": "capture-001",
    "requestId": "req-001",
    "memoryId": "mem-001",
    "userId": "user-1",
    "taskType": "metadata",
    "capturedAt": "2026-04-30T09:00:00Z",
    "sourceImage": {
      "imageKey": "captures/user-1/2026/04/30/capture-001-photo.jpg",
      "imageUrl": null,
      "contentType": "image/jpeg",
      "fileName": "photo.jpg"
    },
    "inferenceRequest": {
      "requestId": "req-001",
      "taskType": "metadata",
      "memoryId": "mem-001",
      "userId": "user-1",
      "capturedAt": "2026-04-30T09:00:00Z",
      "sourceImage": {
        "imageKey": "captures/user-1/2026/04/30/capture-001-photo.jpg",
        "imageUrl": null,
        "contentType": "image/jpeg"
      }
    },
    "dispatch": {
      "transport": "celery-redis",
      "taskName": "process_vision_inference",
      "status": "prepared",
      "brokerUrl": null,
      "note": "Worker task payload is ready for queue dispatch."
    }
  },
  "worker": {
    "taskId": "4f2a6c0d-8d7e-4b35-9f5b-8a1b4d1f2c30",
    "status": "queued",
    "result": null,
    "error": null
  }
}
```

### `GET /media/captures/tasks/{taskId}`

Polls the inference task. While the worker is not finished, the endpoint returns
one of:

- `queued`
- `running`
- `retrying`

When the worker succeeds, the endpoint persists the worker result through the
same PostgreSQL memory store path used by `POST /memories/inference-results`.
The memory write is an upsert by `(user_id, memory_id)`, so repeated polling
after completion is safe.

Completed response sections:

- `taskId`
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

### `DELETE /memories/{memoryId}`

Deletes one captured memory for the authenticated user.

The caller must pass `userId` as a query parameter and authenticate as the same
user. The API first verifies that the memory belongs to the user, then deletes
the Object Storage image when an `imageKey` exists, and finally removes the
PostgreSQL memory document. If Object Storage deletion fails, the DB record is
kept so the client can retry.

Request:

```http
DELETE /memories/mem-earbuds-001?userId=user-1
Authorization: Bearer <access-token>
```

Response:

```json
{
  "status": "deleted",
  "memoryId": "mem-earbuds-001",
  "userId": "user-1",
  "imageKey": "captures/user-1/2026/04/30/cap-earbuds.jpg",
  "objectDeleted": true
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

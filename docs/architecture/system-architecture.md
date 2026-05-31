# System Architecture

This document describes the architecture that is currently represented in the
repository code. It is a system overview; endpoint-level details live in
[`api-spec.md`](./api-spec.md).

## Repository Layout

- `apps/api-server`: Python FastAPI application API. It owns auth, user/device
  registration, media upload authorization, capture registration, task polling,
  memory persistence, search, chat, media access URLs, and admin endpoints.
- `apps/inference-server`: Python FastAPI inference API plus Celery worker code.
  The worker reads captured images from Object Storage, runs the configured
  vision model path, and returns normalized VLM/caption results.
- `apps/smart-glass-client`: Expo/React Native client plus XIAO ESP32S3 Sense
  BLE camera firmware. The current capture screen uses a Web Bluetooth-style
  path to connect to the BLE camera, request capture, receive JPEG chunks,
  upload the image, register the capture, and poll task status.
- `apps/admin-web`: Vite/React admin console. It connects to the API for admin
  login, user/device management, capture upload, task polling, and query-log
  inspection.
- `packages/*`: Workspace packages for shared types, utilities, config, and UI
  kit placeholders.
- `infra/*`: Docker, Compose, Nginx, Kubernetes, and Terraform scaffolding.
- `scripts/*`: Local setup, test, and smoke-test helpers.
- `docs/*`: Architecture, setup, sprint, and convention documentation.

## Runtime Services

The local Compose topology in `infra/compose/docker-compose.local.yml` starts:

- `redis`: Celery broker and result backend.
- `postgres`: PostgreSQL database for API-owned durable stores.
- `inference-api`: HTTP inference service on port `8000`.
- `inference-worker`: Celery worker that executes `process_vision_inference`.
- `api-server`: application API on port `8002`.

The API server waits for Redis, PostgreSQL, and a healthy inference worker before
starting in the local compose file. Original images are stored outside the
database in S3-compatible Object Storage configured through `STORAGE_*`
environment variables.

## Primary Data Flow

1. The smart-glass client requests an upload plan from
   `POST /media/upload-authorizations`.
2. `api-server` validates the device/user boundary and returns a canonical
   `imageKey`, a presigned `PUT` URL, and capture metadata.
3. The client uploads the original image directly to Object Storage using the
   presigned URL.
4. The client registers the capture through `POST /media/captures`.
5. `api-server` submits a Celery task to Redis and returns a `taskId`.
6. `inference-worker` reads the image from Object Storage and runs the configured
   inference path.
7. The worker returns a normalized result with caption, detected objects, tags,
   position hints, provider metadata, and runtime metrics when available.
8. `api-server` polls the worker result, stores successful results in
   PostgreSQL-backed memory storage when enabled, and exposes task state through
   `GET /media/captures/tasks/{taskId}`.
9. The app and API clients read the saved memory through `GET /memories/recent`,
   `POST /search`, `POST /chat`, and media access URL endpoints.

## Application API

`apps/api-server/src/api/main.py` is the active application API entrypoint. Its
main endpoint groups are:

- Health: `GET /health/live`, `GET /health/ready`.
- Auth: signup, login, refresh, logout, Google OAuth start/callback/exchange,
  and admin auth user management.
- Users/devices: user creation, device registration, pairing, approval, revoke,
  rename, and admin device management.
- Capture/media: upload authorization, capture registration, task status,
  gallery, single media access URL, and batch media access URLs.
- Memory: external inference-result ingest, recent memories, search, and chat.

Search and chat currently run inside `api-server` over the memory store and
configured LLM/template provider. A separate vector database or standalone RAG
service is not part of the default runtime.

## Inference Layer

`apps/inference-server` has two runtime modes in local compose:

- `inference-api`: FastAPI service exposing health and model metadata.
- `inference-worker`: Celery worker consuming image-processing jobs from Redis.

The worker task in `apps/inference-server/src/queue/tasks.py`:

- reads the source image from Object Storage;
- decodes the image;
- chooses an execution path from environment/profile settings;
- supports local Qwen VLM metadata generation, Ollama VLM forwarding, and
  caption-model fallback paths;
- normalizes success/error responses through the VLM contract;
- records queue, storage, decode, inference, and task latency metrics when
  available;
- classifies retryable failures such as storage access and model runtime errors.

The default local compose settings select `qwen2.5-vl-7b` with `4bit`
quantization. Actual success depends on GPU, CUDA/PyTorch compatibility, model
cache, Object Storage credentials, and bucket permissions.

## Smart-Glass Client And Firmware

The client app uses `EXPO_PUBLIC_API_BASE_URL` and defaults to
`http://localhost:8002`.

Current app capture behavior:

- The Capture screen connects to a BLE device named `XIAO_BLE_CAM` through the
  browser/Web Bluetooth API exposed as `navigator.bluetooth`.
- It uses Nordic-UART-style service/characteristics defined in the firmware.
- Pressing the capture button writes command `1` to the RX characteristic.
- The firmware captures a JPEG and sends chunks over TX notifications.
- The app reconstructs the JPEG, uploads it through the media upload flow,
  registers the capture, and polls task status.
- The Capture screen also refreshes the displayed recent-memory list
  periodically. This refresh timer does not trigger new captures.

Current firmware behavior:

- RX command `1`: capture a JPEG frame and send it over BLE notifications.
- RX command `2`: enter deep sleep.
- The firmware does not currently run its own periodic capture timer.

## Admin Web

`apps/admin-web` is a Vite/React admin console. Its active entrypoint renders the
API-connected console in `src/app/App.jsx`.

Current implementation status:

- Admin login uses the bootstrap account configured through environment
  variables.
- User devices can be listed, approved, and revoked through admin API
  endpoints.
- The upload panel selects an active device, requests a device-oriented upload
  authorization, uploads directly to Object Storage, registers the capture, and
  polls task status.
- The production Compose stack serves the built SPA through Nginx and proxies
  `/api/*` to `api-server`.
- Browser direct upload still requires Object Storage CORS to allow the admin
  web origin, `PUT`, and `Content-Type`.

## Storage And Persistence

- Object Storage stores original captured images under canonical capture object
  keys generated by `api-server`.
- PostgreSQL stores API-owned user/device/auth data and normalized memory
  records.
- Redis carries Celery task dispatch and result state.
- Media access to stored images is exposed through short-lived signed URLs.

## Auth And Device Boundaries

The API server has real auth flows and demo-token support:

- JWT-style access/refresh token flows are implemented in the auth module.
- Google OAuth local setup is supported through dedicated auth endpoints.
- Demo bearer tokens can be enabled by `API_AUTH_ENABLE_DEMO_TOKENS`.
- Device registration and capture authorization enforce user/device boundaries.
- Capture image keys are normalized to stay under the requesting user's capture
  prefix.

## Local Development Notes

- Root script `npm run dev` delegates to `scripts/dev.sh`.
- API/inference local compose depends on `.env` Object Storage values.
- `INFERENCE_STORAGE_READINESS_MODE=config` checks configuration only; `deep`
  performs bucket-level access probing.
- `API_CAPTURE_ENABLE_MEMORY_STORE=1` enables memory persistence in local compose.
- Browser direct upload requires Object Storage CORS to allow the web/app origin,
  `PUT`, and `Content-Type`.

## Current Boundaries

- The default architecture does not include a separate vector database.
- The app has manual BLE capture request behavior; a five-minute periodic
  capture scheduler is not implemented in the current app or firmware.
- Hardware, BLE support, Object Storage credentials, bucket permissions, and
  model runtime compatibility can block a full end-to-end local demo even when
  the code paths are present.

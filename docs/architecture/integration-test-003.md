# 3rd Integration Test

## Purpose

The third integration test extends the second device-auth integration flow with
the newly merged auth and memory-chat work:

1. Device-based upload authorization and capture pipeline
2. Object Storage direct upload through presigned PUT URL
3. Celery dispatch and inference-worker VLM processing
4. PostgreSQL memory persistence
5. Metadata-derived `/search` and `/chat` validation
6. Google OAuth web login flow
7. Profile-based device registration/selection after login
8. Admin auth-user controls
9. Ollama Cloud answer generation for memory chat
10. Web session continuity for chat, history, and item-location views

## Execution Result

Executed on 2026-05-07 against the local Docker Compose stack.

Services:

- `compose-api-server-1`: ready
- `compose-inference-api-1`: healthy
- `compose-inference-worker-1`: healthy
- `compose-postgres-1`: healthy
- `compose-redis-1`: healthy

Test data:

- `userId`: `device-auth-smoke-user-20260507-003`
- `deviceId`: `device-auth-smoke-glass-20260507-003`
- image: `apps/inference-server/sample_data/KakaoTalk_20260406_114213285.png`
- image key:
  `captures/device-auth-smoke-user-20260507-003/2026/05/07/capture-d45f793e8667-KakaoTalk_20260406_114213285.png`
- Celery task id: `3c77e56e-d5c3-48a1-ae8e-156be6540993`
- memory id: `mem-589eef037022`

Confirmed flow:

```text
User creation
-> Device registration
-> deviceId-based upload authorization
-> Object Storage direct upload through presigned PUT
-> capture registration
-> Celery dispatch
-> inference-worker VLM inference
-> PostgreSQL memory persistence
-> /memories/recent metadata lookup
-> metadata-derived /search
-> /chat
```

Stored metadata excerpt:

- caption: `작업 중인 작업실 내부`
- scene summary: `작업 중인 작업실 내부`
- position hint: `테이블 위`
- detected objects:
  `모니터`, `램프`, `컵`, `전선`, `스케치북`, `펜`, `아이폰`, `전화기`, `전자기기`, `태블릿`
- selected metadata-derived query: `모니터`

Search/chat result:

- `/search` query `모니터`: `totalHits = 1`
- `/chat` query `모니터 어디 있어?`: `200 OK`
- cited memory: `mem-589eef037022`

Unregistered device block result:

- request `deviceId`: `unknown-device-20260507-003`
- response status: `403 Forbidden`
- response body:

```json
{
  "status": "blocked",
  "deviceId": "unknown-device-20260507-003",
  "userId": null,
  "upload": null
}
```

## Device Upload Flow

Use the local Docker Compose stack:

```bash
docker compose -f infra/compose/docker-compose.local.yml up -d --build
```

Run the smoke script from the repository root:

```bash
python scripts/run-device-auth-flow.py
```

The default test image is:

```text
apps/inference-server/sample_data/KakaoTalk_20260406_114213285.png
```

The script now verifies search with stored metadata instead of the image file
name. After the worker stores memory, it fetches `/memories/recent`, derives
query candidates from actual VLM fields, and accepts the first query that
returns the stored memory.

## Google OAuth And Web Flow

Required local settings:

```text
API_AUTH_GOOGLE_CALLBACK_URL=http://localhost:8002/auth/oauth/google/callback
API_AUTH_OAUTH_REDIRECT_ALLOWLIST=smart-glass-client://oauth,http://localhost:8081/,http://127.0.0.1:8081/
EXPO_PUBLIC_API_BASE_URL=http://localhost:8002
```

Readiness check:

```bash
python scripts/check-google-oauth-setup.py
```

Expected web flow:

```text
Login screen
-> Continue with Google
-> backend callback
-> OAuth handoff exchange
-> profile screen
-> device registration or existing device selection
-> chat main screen
```

Confirmed on 2026-05-07:

- `POST /auth/oauth/google/start`: `200 OK`
- `GET /auth/oauth/google/callback`: `302 Found`
- `POST /auth/oauth/google/exchange`: `200 OK`
- `POST /users/{userId}/devices`: `201 Created`
- `GET /users/{userId}/devices`: `200 OK`
- Expo web ran on `http://localhost:8081` with Node `v22.22.2`

During the 3rd integration run, the local stack also confirmed:

- `python scripts/check-google-oauth-setup.py`: ready
- `POST /auth/oauth/google/start`: `200 OK`
- Google authorization URL and state were generated successfully

## Admin Auth Controls

Backend unit coverage for the admin auth-user APIs is included in:

```bash
python -m unittest tests.test_auth_service tests.test_api_real_auth
```

Covered behavior:

- admin-only auth-user listing
- role/status update
- disabled-account refresh session revocation
- non-admin access rejection

## Ollama Memory Chat

Required local settings:

```text
API_LLM_PROVIDER=ollama
API_LLM_OLLAMA_BASE_URL=https://ollama.com/api
API_LLM_OLLAMA_API_KEY=...
API_LLM_OLLAMA_MODEL=gpt-oss:20b-cloud
API_LLM_OLLAMA_TIMEOUT_SEC=20
```

Confirmed on 2026-05-07:

- direct Ollama Cloud `/api/chat` call succeeded
- memory-hit answer generation returned `answer.mode == "ollama"`
- generated Korean answer cited the stored memory id used in the smoke context
- endpoint-level `/chat` verification with `API_LLM_PROVIDER=ollama` returned
  `answerMode = "ollama"` for memory `mem-589eef037022`

Note: the committed local `.env` value used during the Compose run had
`API_LLM_PROVIDER=template`, so the default Compose `/chat` response used
template mode. The Ollama endpoint path was verified by running api-server with
`API_LLM_PROVIDER=ollama` against the same Postgres memory store.

## Regression Commands

Backend:

```bash
python -m unittest tests.test_auth_service tests.test_api_real_auth
python -m unittest tests.test_search_service tests.test_api_real_auth
python -m unittest tests.test_search_ollama tests.test_google_oauth_service
```

Frontend:

```bash
npx tsc --noEmit -p apps/smart-glass-client/tsconfig.json
```

## Known Operational Notes

- In Docker Compose, `API_CAPTURE_DATABASE_URL` can use host `postgres`.
- For local uvicorn outside Compose, override the database URL to
  `127.0.0.1:5432`.
- `/health/ready` checks storage, DB, auth, user-device, and memory query
  dependencies; a single missing external dependency can make readiness fail
  even when liveness is healthy.
- Pydantic currently emits alias warnings for some request fields. The warnings
  do not block the tested flows, but should be cleaned up separately.

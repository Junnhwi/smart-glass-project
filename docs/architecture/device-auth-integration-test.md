# Device Auth Integration Test

## Purpose

This smoke flow validates the second integration-test path requested for
`api-server`:

1. Create or confirm a user
2. Register or confirm a smart-glass `deviceId`
3. Request `POST /media/upload-authorizations`
4. Upload the original image through the returned presigned PUT `uploadUrl`
5. Register `POST /media/captures`
6. Poll `GET /media/captures/tasks/{taskId}`
7. Verify the stored memory through `/search` and `/chat`

## Prerequisites

- local or shared `api-server` running and reachable
- object storage credentials configured in `.env`
- worker/storage pipeline available so the capture task can complete

Recommended local stack:

```bash
docker compose -f infra/compose/docker-compose.local.yml up -d --build
```

## Run

From the repository root:

```bash
python scripts/run-device-auth-flow.py
```

The default image is:

```text
apps/inference-server/sample_data/KakaoTalk_20260406_114213285.png
```

Optional custom image:

```bash
python scripts/run-device-auth-flow.py apps/inference-server/sample_data/wallet_54.jpg
```

Optional custom user/device/query:

```bash
python scripts/run-device-auth-flow.py \
  apps/inference-server/sample_data/key_1.jpg \
  --user-id device-auth-user-01 \
  --device-id glass-device-01 \
  --query key
```

When `--query` is omitted, the script does not infer the verification query
from the image file name. After memory persistence succeeds, it reads
`/memories/recent`, finds the stored memory, builds query candidates from the
actual VLM metadata (`detectedObjects`, `tags`, `positionHint`, `caption`,
`sceneSummary`), and uses the first query that returns the stored memory from
`/search`.

## Success Criteria

The script succeeds only when all of these pass:

- upload authorization returns `allowed`
- direct object-storage upload succeeds
- capture task reaches `completed`
- memory store status is `success`
- `/memories/recent` returns the stored memory metadata
- metadata-derived `/search` query returns the stored memory
- `/chat` returns a non-empty answer for the selected query

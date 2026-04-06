# Healthcheck Probes

`apps/inference-server` exposes two operational probe endpoints for `inference-api`, and the Celery worker uses an internal probe script.

- `GET /health/live`
  - Purpose: liveness probe
  - Meaning: the API process is up and able to respond
  - Use this when the platform supports a separate liveness probe

- `GET /health/ready`
  - Purpose: readiness probe
  - Meaning: the API process is up and key dependencies are ready
  - Current checks: Redis broker connectivity, S3-related required env vars, caption model config
  - Returns `503` when the service is not ready to accept traffic

## Docker Compose

Docker Compose supports a single container healthcheck, so `inference-api` uses the readiness endpoint and `inference-worker` uses a Celery ping-based script.

```yaml
inference-worker:
  healthcheck:
    test:
      [
        "CMD",
        "python",
        "/app/scripts/worker_healthcheck.py"
      ]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 30s

inference-api:
  healthcheck:
    test:
      [
        "CMD",
        "python",
        "/app/scripts/http_healthcheck.py",
        "http://127.0.0.1:8000/health/ready"
      ]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 20s
```

`worker_healthcheck.py` verifies:

- the Celery worker responds to `ping`
- Redis broker connectivity is available
- required S3 env vars are present
- configured model key / quantization / dtype are valid
- worker startup preload finished successfully and wrote a ready status file

## Worker Preload

`inference-worker` can preload the serving model during container startup.

- enabled with `INFERENCE_WORKER_PRELOAD_ON_STARTUP=1`
- preload status file path defaults to `/tmp/inference-worker-preload.json`
- when `INFERENCE_PRELOAD_FAIL_FAST=1`, preload failure stops worker startup
- preload target defaults to `VISION_CAPTION_MODEL` and can be overridden with `VISION_PRELOAD_MODEL`

This is a startup-time behavior, not an image build-time behavior. Docker image build only installs code and dependencies; the model is downloaded and loaded when the worker container actually starts.

## Deployment Example

When deploying to Kubernetes or another orchestrator that supports separate probes, wire them like this.

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 15
```

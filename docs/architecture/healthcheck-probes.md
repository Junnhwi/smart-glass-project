# Healthcheck Probes

`apps/inference-server` exposes two operational probe endpoints.

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

Docker Compose supports a single container healthcheck, so `inference-api` uses the readiness endpoint.

```yaml
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

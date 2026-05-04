# Observability

## Structured Logs

`apps/inference-server` writes JSON logs through
`apps/inference-server/src/core/logging.py`.

Common HTTP request logs include:

- `request_id`
- `method`
- `path`
- `status_code`
- `duration_ms`
- `client_ip`

Inference worker logs include:

- `task_name`
- `request_id`
- `image_key`
- `memory_id`
- `user_id`
- `model_key`
- `model_id`
- `model_mode`
- `quantization`
- `dtype_name`
- `settings_source`
- `soft_time_limit_sec`
- `hard_time_limit_sec`
- `fallback_model_key`
- `fallback_triggered`
- `latency_sec`
- `load_time_sec`
- `peak_memory_mb`

Retry and failure logs also include:

- `error_code`
- `retryable`
- `failure_category`
- `retry_count`
- `max_retries`
- `retry_delay_sec`

The log formatter uses an explicit allowlist. Do not add credentials, raw image
bytes, raw model prompts, signed access URLs, or token values to logger `extra`.

## Health Monitoring

Inference readiness surfaces local probe timing:

- `checks.<name>.durationMs`: duration for a single dependency check
- `summary.durationMs`: sum of measured check durations

Current inference readiness checks cover:

- API process health
- Redis broker connectivity
- storage configuration or deep storage access, depending on mode
- selected model configuration

Worker readiness covers:

- Celery worker ping or process fallback
- Redis broker connectivity
- storage readiness
- selected model configuration
- preload status

Timing fields are useful for spotting slow dependencies, but they are measured
inside the service process and are not a replacement for external request
latency monitoring.

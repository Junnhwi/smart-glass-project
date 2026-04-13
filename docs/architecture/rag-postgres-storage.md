# RAG Postgres Storage

This project now uses PostgreSQL for durable memory storage in `rag-service`.

## What is stored

- `memory_id`
- `user_id`
- `image_key` / `image_url`
- `captured_at`
- `caption`, `scene_summary`, `ocr_text`, `position_hint`
- `detected_objects`, `tags`
- `location`
- the normalized memory document as JSONB

## Local Docker workflow

No separate database installation is needed.

1. Copy the sample env file.
2. Run Docker Compose.

```powershell
Copy-Item .env.example .env
docker compose -f infra/compose/docker-compose.local.yml up --build
```

The compose file starts:

- `postgres`
- `redis`
- `inference-api`
- `inference-worker`
- `rag-service`

`rag-service` uses the PostgreSQL backend automatically in this compose setup.

## Running `rag-service` outside Docker

If you want to run the service directly on the host, keep the file backend or set your own PostgreSQL URL.

```powershell
$env:RAG_STORAGE_BACKEND="file"
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

For PostgreSQL mode you need:

- `psycopg[binary]`
- a running PostgreSQL server
- `RAG_STORAGE_BACKEND=postgres`
- `RAG_DATABASE_URL=postgresql://...`

## Notes

- The search pipeline still uses the current TF-IDF retriever.
- PostgreSQL is the persistence layer, so the existing RAG and LLM responses continue to work without code changes in the API layer.
- Vector search can be added later on top of the same stored memory records.

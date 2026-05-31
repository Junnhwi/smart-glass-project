# LLM-only memory prompt experiment

These scripts let you test the answer prompt without running the full capture,
VLM, API, and app flow.

## 1. Dump stored memory JSON from PostgreSQL

```powershell
python ai_test/llm/dump_memory_records.py --user-id USER_ID
```

By default this reads `API_CAPTURE_DATABASE_URL` from `.env`. If the local Docker
compose URL uses the service host `postgres`, the script rewrites it to
`localhost` so it can run from the host machine.

Output JSON files are written to:

```text
output/llm-memory-dump/
```

## 2. Run only the LLM prompt

```powershell
python ai_test/llm/run_memory_prompt.py "내 지갑 어디 있었어?"
```

To inspect the final messages without calling the model:

```powershell
python ai_test/llm/run_memory_prompt.py "내 지갑 어디 있었어?" --dry-run
```

`ai_test/llm/answer_prompt.txt` starts from the same answer prompt used by
`apps/api-server/src/modules/search/service.py` in the main `/chat` flow. Edit
that file when you want to test prompt-only changes.

Useful overrides:

```powershell
python ai_test/llm/run_memory_prompt.py "내 지갑 어디 있었어?" --model gpt-oss:20b-cloud --base-url https://ollama.com/api
python ai_test/llm/run_memory_prompt.py "내 지갑 어디 있었어?" --memory-dir output/llm-memory-dump --limit 10
```

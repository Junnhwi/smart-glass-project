# 설정 가이드 (Setup Guide)

## 로컬 개발 환경 (Local Development)

권장하는 로컬 작업 환경은 저장소 최상단(루트)에서 Docker Compose를 사용하는 것입니다.

```powershell
Copy-Item .env.example .env
docker compose -f infra/compose/docker-compose.local.yml up --build
```

기본 로컬 스택을 실행하면 다음 서비스들이 시작됩니다:

- `postgres`
- `redis`
- `inference-api`
- `inference-worker`
- `api-server`

## 서비스 역할 (Service Roles)

- api-server: 캡처 등록, PostgreSQL 메모리 영구 저장(Persistence), 검색 및 채팅 API

- inference-server: VLM 추론 API 및 Celery 워커(Worker)

- postgres: 정규화된 메타데이터를 보관하는 영구 메모리 저장소

- redis: 큐 브로커(Queue broker) 및 결과 백엔드(Result backend)

## 필수 환경 변수 (Required Environment Values)

스택을 실행하기 전에 .env 파일에 다음 항목들을 설정해야 합니다:

- `STORAGE_ACCESS_KEY_ID`
- `STORAGE_SECRET_ACCESS_KEY`
- `STORAGE_BUCKET_NAME`
- `STORAGE_REGION`
- `STORAGE_ENDPOINT_URL`
- `STORAGE_ADDRESSING_STYLE`

기본 오브젝트 스토리지 설정은 네이버 오브젝트 스토리지(Naver Object Storage)를 기준으로 합니다:

- `STORAGE_REGION=kr-standard`
- `STORAGE_ENDPOINT_URL=https://kr.object.ncloudstorage.com`
- `STORAGE_ADDRESSING_STYLE=path`

## 선택적 환경 변수 (Optional Environment Values)

- `API_CAPTURE_ENABLE_MEMORY_STORE`
- `API_CAPTURE_DATABASE_URL`
- `API_MEMORY_DEFAULT_TOP_K`
- `VISION_QWEN_FALLBACK_MODEL`
- `VISION_QWEN_ENABLE_OBJECT_REVIEW`

## WSL / DNS 관련 주의사항 (WSL / DNS Notes)

WSL 내부에서 kr.object.ncloudstorage.com에 대한 도메인 이름 확인(Name resolution)이 실패할 경우, Docker 컨테이너가 정상(Healthy) 상태여도 오브젝트 스토리지 접근 테스트 및 CLI 검사가 실패할 수 있습니다.

유용한 점검 명령어:

```bash
getent hosts kr.object.ncloudstorage.com
python -c "import socket; print(socket.getaddrinfo('kr.object.ncloudstorage.com', 443))"
cat /etc/resolv.conf
```

필요한 경우, 자동 생성되는 WSL DNS를 비활성화하고 /etc/resolv.conf 파일을 수동으로 작성하세요:

```ini
[network]
generateResolvConf = false
```

```bash
wsl --shutdown
sudo rm -f /etc/resolv.conf
printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" | sudo tee /etc/resolv.conf
```

## Postgres 볼륨 주의사항 (Postgres Volume Note)

만약 이전에 다른 Postgres 인증 정보로 구버전 로컬 스택을 실행한 적이 있다면, 업데이트된 compose 스택을 시작하기 전에 로컬의 postgres-data 볼륨을 다시 생성(초기화)해야 합니다.

## NCP 운영 환경 배포 (NCP Production Deployment)

운영(Production) compose 스택은 VLM 추론과 채팅 응답 모두에 Ollama Cloud를 사용합니다. 추론 워커(Inference worker)는 CPU 전용 Python 이미지에서 실행되므로 CUDA, NVIDIA 런타임 또는 GPU 서버가 필요하지 않습니다.

루트 .env 파일에 다음 값들을 설정하세요:

```env
API_LLM_OLLAMA_API_KEY=...
API_LLM_OLLAMA_BASE_URL=https://ollama.com/api
API_LLM_OLLAMA_MODEL=gpt-oss:20b-cloud
OLLAMA_VLM_MODEL=gemma3:12b
```

저장소 최상단(루트)에서 배포를 시작합니다:

```bash
docker compose -f infra/compose/docker-compose.prod.yml up --build -d
```

이 스택을 실행하면 다음 서비스들이 시작됩니다:

- `postgres`
- `redis`
- `inference-worker`
- `api-server`

백그라운드에서 오래 실행되는 서비스들이 켜지기 전에, 일회성 검사(One-shot checks)를 통해 오브젝트 스토리지 접근 및 Ollama Cloud API 키 설정이 올바른지 먼저 확인합니다. 공개(Public) API는 8002 포트로 열립니다.
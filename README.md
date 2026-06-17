# Smart Glass Project

시각 정보를 기억으로 저장하고 다시 검색할 수 있는 스마트 글래스 서비스 모노레포입니다.
BLE 카메라로 촬영한 이미지를 Object Storage에 업로드하고, VLM 추론 결과를 구조화해 저장한 뒤 앱에서 최근 기억, 검색, 채팅 형태로 조회하는 흐름을 구현했습니다.

## 핵심 요약

- 스마트 글래스 클라이언트, 백엔드 API, VLM 추론 워커, 관리자 웹을 한 저장소에서 관리합니다.
- 이미지 원본은 S3 호환 Object Storage에 저장하고, 사용자/기기/기억 메타데이터는 PostgreSQL에 저장합니다.
- Redis와 Celery로 이미지 추론 작업을 비동기 처리합니다.
- 검색과 채팅은 `api-server` 안에서 메모리 저장소와 LLM provider를 사용해 제공합니다.
- 로컬 개발은 Docker Compose 기준으로 실행할 수 있습니다.

## 주요 기능

| 영역 | 내용 |
| --- | --- |
| 스마트 글래스 앱 | Expo/React Native 앱, BLE 카메라 연결, JPEG 수신, 업로드, 작업 상태 조회 |
| 펌웨어 | Seeed Studio XIAO ESP32S3 Sense 기반 BLE 카메라 스케치 |
| API 서버 | 인증, 사용자/기기 관리, 업로드 승인, 캡처 등록, 메모리 저장, 검색, 채팅 |
| 추론 서버 | FastAPI inference API와 Celery worker, Qwen/Ollama 기반 VLM 추론 경로 |
| 관리자 웹 | 사용자 및 기기 관리, 캡처 업로드 테스트, 추론 작업 상태 확인 |
| 인프라 | Docker, Compose, Nginx, Kubernetes, Terraform 스캐폴딩 |

## 아키텍처

```text
Smart Glass Client / Admin Web
        |
        | upload authorization, capture registration, search/chat
        v
API Server (FastAPI)
        |
        | Celery task
        v
Redis  <---->  Inference Worker
        |              |
        |              | read image / run VLM
        v              v
PostgreSQL      Object Storage
```

기본 데이터 흐름은 다음과 같습니다.

1. 클라이언트가 API 서버에 업로드 권한을 요청합니다.
2. 클라이언트가 presigned URL로 이미지를 Object Storage에 직접 업로드합니다.
3. API 서버가 캡처를 등록하고 Celery 작업을 큐에 넣습니다.
4. 추론 워커가 이미지를 읽고 VLM 결과를 정규화합니다.
5. API 서버가 결과를 PostgreSQL에 memory record로 저장합니다.
6. 앱은 최근 기억, 검색, 채팅 API로 저장된 기억을 조회합니다.

## 기술 스택

| 구분 | 기술 |
| --- | --- |
| Client | Expo, React Native, React Navigation, TypeScript |
| Admin Web | React, Vite |
| API | Python, FastAPI, Uvicorn, Pydantic |
| Async Worker | Celery, Redis |
| Inference | Qwen VLM, Ollama Cloud 연동, Pillow/OpenCV 기반 이미지 처리 |
| Storage | PostgreSQL, S3 호환 Object Storage |
| Infra | Docker, Docker Compose, Nginx |

## 저장소 구조

```text
smart-glass-project/
|-- apps/
|   |-- api-server/          # FastAPI application API
|   |-- inference-server/    # VLM inference API and Celery worker
|   |-- admin-web/           # React admin console
|   `-- smart-glass-client/  # Expo app and ESP32S3 BLE camera firmware
|-- packages/                # shared package placeholders
|-- infra/                   # docker, compose, nginx, k8s, terraform
|-- scripts/                 # local helper scripts
`-- docs/                    # architecture and setup notes
```

## 빠른 시작

`.env.example`을 복사한 뒤 Object Storage와 인증 관련 값을 채웁니다.

```bash
cp .env.example .env
docker compose -f infra/compose/docker-compose.local.yml up --build
```

로컬 Compose 스택은 다음 서비스를 실행합니다.

- `api-server`: http://localhost:8002
- `inference-api`: http://localhost:8000
- `postgres`: localhost:5432
- `redis`: localhost:6379
- `inference-worker`: Celery worker

관리자 웹까지 포함한 운영형 compose는 다음 명령으로 실행합니다.

```bash
docker compose -f infra/compose/docker-compose.prod.yml up --build -d
```

## 주요 API

| 목적 | Endpoint |
| --- | --- |
| Health check | `GET /health/live`, `GET /health/ready` |
| 업로드 승인 | `POST /media/upload-authorizations` |
| 캡처 등록 | `POST /media/captures` |
| 작업 상태 조회 | `GET /media/captures/tasks/{taskId}` |
| 최근 기억 | `GET /memories/recent` |
| 기억 검색 | `POST /search` |
| 기억 기반 채팅 | `POST /chat` |
| 미디어 접근 URL | `POST /media/access-url`, `POST /media/access-urls` |

자세한 API 계약은 [`docs/architecture/api-spec.md`](docs/architecture/api-spec.md)를 참고합니다.

## 테스트와 검증

서비스별 테스트는 `apps/api-server/tests`와 `apps/inference-server/tests`에 있습니다.
현재 루트 `npm run test`는 자리만 잡혀 있으므로, 실제 검증은 각 Python 서비스 테스트와 Compose healthcheck를 중심으로 수행합니다.

```bash
python -m unittest discover apps/api-server/tests
python -m unittest discover apps/inference-server/tests
```

## 문서

- [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md): 전체 아키텍처와 현재 구현 범위
- [`docs/architecture/api-spec.md`](docs/architecture/api-spec.md): API 요청/응답 계약
- [`apps/smart-glass-client/README.md`](apps/smart-glass-client/README.md): BLE 카메라 펌웨어 계약
- [`docs/google-oauth-local-setup.md`](docs/google-oauth-local-setup.md): Google OAuth 로컬 설정
- [`docs/ollama-cloud-setup.md`](docs/ollama-cloud-setup.md): Ollama Cloud 설정

## 현재 구현 범위

- 기본 런타임은 별도 벡터 DB 없이 API 서버 내부 검색/채팅 흐름을 사용합니다.
- BLE 캡처는 사용자가 직접 촬영 명령을 보내는 방식입니다.
- 전체 end-to-end 데모는 BLE 지원 환경, Object Storage 권한, GPU 또는 Ollama Cloud 설정에 영향을 받습니다.

# smart-glass-project

스마트 글라스 프로젝트를 위한 모노레포입니다.

## Repository Layout

```text
smart-glass-project/
├─ apps/
│  ├─ api-server/
│  ├─ inference-server/
│  ├─ rag-service/
│  ├─ admin-web/
│  └─ smart-glass-client/
├─ packages/
│  ├─ shared-types/
│  ├─ shared-utils/
│  ├─ shared-config/
│  └─ ui-kit/
├─ infra/
│  ├─ docker/
│  ├─ compose/
│  ├─ nginx/
│  ├─ k8s/
│  └─ terraform/
├─ scripts/
├─ docs/
└─ .github/
```

## 3.27 note: Current Status

- 기존 `inference-server` 구현은 `apps/inference-server`로 이동했습니다.
- 로컬 Docker Compose 파일은 `infra/compose/docker-compose.local.yml`로 이동했습니다.
- 나머지 앱과 패키지는 확장을 위한 기본 골격을 먼저 구성했습니다.

## Quick Start

```bash
cp .env.example .env
docker compose -f infra/compose/docker-compose.local.yml up --build
```

## Notes

- Object Storage 및 기타 민감한 값은 `.env`에만 보관하세요.
- 추론 워커 테스트 스크립트는 `apps/inference-server/scripts/test_task.py`에 있습니다.
- 문서와 운영 스크립트는 각각 `docs/`, `scripts/` 아래로 정리했습니다.

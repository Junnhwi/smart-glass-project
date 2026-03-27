# System Architecture

- `apps/api-server`: 메인 API 서버
- `apps/inference-server`: 비전 추론 워커 및 관련 파이프라인
- `apps/rag-service`: 검색 및 RAG 서비스
- `apps/admin-web`: 관리자 웹
- `apps/smart-glass-client`: 스마트 글라스 클라이언트
- `packages/*`: 공통 타입, 유틸, 설정, UI 자산
- `infra/*`: Docker, Compose, Nginx, Kubernetes, Terraform 관리

# [공지] Smart Glass 프로젝트 통합 개발 가이드

프로젝트의 코드 안전성과 효율적인 관리를 위해 아래 **환경 세팅** 및 **'포크(Fork) & PR'** 방식을 준수해 주세요.

## 💻 Part 1. 로컬 개발 환경 세팅 (WSL2 & Docker)

우리 프로젝트는 모든 환경을 **Docker**로 통일합니다. 반드시 **WSL2 내부 경로(`~/`)**에서 작업해 주세요.

### 1단계: WSL2 및 Ubuntu 준비

1. 터미널(PowerShell)을 관리자 권한으로 실행 후 `wsl --install` 입력.
2. 설치 후 PC 재부팅, Microsoft Store에서 **Ubuntu** 설치 및 실행.

### 2단계: Docker Desktop 설정

1. **Settings > General**: `Use the WSL 2 based engine` 체크 확인.
2. **Settings > Resources > WSL Integration**: `Enable integration with my default WSL distro`와 설치한 **Ubuntu** 항목 활성화.

### 3단계: NVIDIA Container Toolkit (★AI/Inference 담당자 필수)

*프론트엔드/앱 서버 담당자는 건너뛰어도 무방합니다.*

Bash

```bash
# Ubuntu 터미널에서 실행
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
# ... (NVIDIA 리포지토리 등록 및 설치 진행)
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 4단계: WSL Git 초기 설정 (공통)

줄 바꿈 오류 방지를 위해 아래 설정을 반드시 실행해 주세요.

Bash
git config --global core.autocrlf input
```

## LLM / Chat

- Local chat responses now use an Ollama-backed OpenAI-compatible endpoint in the local compose stack.
- `docker compose -f infra/compose/docker-compose.local.yml up --build` starts Ollama, pulls `qwen2.5:3b`, and points `rag-service` at `http://ollama:11434/v1`.
- Team members do not need to install the model manually when they use the compose setup.

## Object Storage / DNS 점검

- inference-server는 AWS S3 전용이 아니라 S3 호환 Object Storage 설정을 사용합니다.
- 기본 환경변수는 `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY`, `STORAGE_BUCKET_NAME`, `STORAGE_REGION`, `STORAGE_ENDPOINT_URL`, `STORAGE_ADDRESSING_STYLE` 입니다.
- 네이버 Object Storage 기본값은 `STORAGE_REGION=kr-standard`, `STORAGE_ENDPOINT_URL=https://kr.object.ncloudstorage.com`, `STORAGE_ADDRESSING_STYLE=path` 입니다.

### WSL 호스트 DNS 이슈

- WSL에서 `kr.object.ncloudstorage.com` 해석이 실패하면, 컨테이너 밖 Python/CLI probe는 실패할 수 있습니다.
- 이번 저장소에서 재현된 증상은 아래와 같습니다.
  - `getent hosts kr.object.ncloudstorage.com` 실패
  - `socket.getaddrinfo('kr.object.ncloudstorage.com', 443)` 실패
  - `/etc/resolv.conf` 에 WSL 자동 생성 nameserver 하나만 설정됨

### 점검 명령

```bash
getent hosts kr.object.ncloudstorage.com
python -c "import socket; print(socket.getaddrinfo('kr.object.ncloudstorage.com', 443))"
cat /etc/resolv.conf
```

### 권장 조치

1. `/etc/wsl.conf`에 아래 설정을 추가해 WSL의 자동 DNS 생성을 끕니다.

```ini
[network]
generateResolvConf = false
```

2. WSL을 종료한 뒤 다시 시작합니다.

```bash
wsl --shutdown
```

3. Ubuntu 재진입 후 `/etc/resolv.conf`를 직접 작성합니다.

```bash
sudo rm -f /etc/resolv.conf
printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" | sudo tee /etc/resolv.conf
```

4. 다시 이름 해석을 확인합니다.

```bash
getent hosts kr.object.ncloudstorage.com
```

### 참고

- Docker 컨테이너 내부에서는 DNS가 정상일 수 있어, 호스트 probe만 실패하고 compose 기반 smoke test는 성공할 수 있습니다.
- 운영 검증은 가능하면 `scripts/smoke-inference-qwen.sh` 또는 `scripts/run-qwen-via-api.sh` 같은 compose 경로 기준으로 함께 확인하는 것을 권장합니다.

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
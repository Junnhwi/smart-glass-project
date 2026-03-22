# smart-glass-project

1단계: WSL2 및 Ubuntu 준비
Docker는 리눅스 기반이므로 Windows 안에 리눅스(WSL2)가 먼저 깔려 있어야 합니다.
1.	터미널(PowerShell 또는 CMD)을 관리자 권한으로 실행합니다.
2.	wsl --install 명령어를 입력합니다. (이미 설치되어 있다면 다음으로 넘어갑니다.)
3.	설치 후 PC를 재부팅하고, Microsoft Store에서 Ubuntu를 설치하여 실행합니다.
2단계: Docker Desktop 설정 확인
1.	Docker Desktop을 실행하고 **Settings (톱니바퀴 아이콘)**로 들어갑니다.
2.	General 탭에서 Use the WSL 2 based engine이 체크되어 있는지 확인합니다.
3.	Resources > WSL Integration에서 Enable integration with my default WSL distro와 방금 설치한 Ubuntu 항목을 활성화합니다.
3단계: WSL2 내부에서 Toolkit 설치
이제 Ubuntu 터미널을 열고 다음 명령어들을 복사해서 붙여넣으세요. NVIDIA의 공식 리포지토리를 등록하고 툴킷을 설치하는 과정입니다.
Bash
# 1. 저장소 설정
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. 패키지 목록 업데이트 및 설치
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Docker 서비스 재시작 (Ubuntu 터미널 내)
sudo systemctl restart docker
________________________________________
✅ 최종 확인: Docker에서 GPU가 돌아가는가?
설치가 끝났다면, Docker 컨테이너 내부에서도 아까 윈도우에서 봤던 nvidia-smi 화면이 뜨는지 확인해야 합니다. 터미널에 다음 명령어를 입력해 보세요.
Bash
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.0.1-base-ubuntu22.04 nvid


# wsl에서 github repository clone 하는 방법: SSH이용
# 1. ssh-keygen -t ed25519 -C "your_email@example.com"
# 2. cat ~/.ssh/id_ed25519.pub
# 3. github에 등록 Settings -> SSH and GPG keys -> New SSH key -> Key 붙여넣기 -> 저장
# 4. ssh로 클론 ex. git clone git@[IP_ADDRESS]:ghpark/smart-glass-project.git


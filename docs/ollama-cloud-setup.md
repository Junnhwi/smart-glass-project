# Ollama Cloud LLM Setup

## 목적

`api-server /chat` 응답을 template 답변 대신 Ollama Cloud LLM으로 생성하도록 설정한다.

현재 기본 구현은 다음과 같다.

- 검색: 기존 memory search 로직 유지
- 답변 생성: Ollama Cloud 우선
- 실패 시: 기존 template 답변으로 fallback

## 기본 권장값

지금 브랜치의 기본 권장 모델은 `gpt-oss:20b-cloud`다.

이유:

- Ollama 공식 cloud 모델 중 비교적 최신 `gpt-oss` 계열
- 무료 플랜에서도 접근 가능
- `120b`보다 데모/개발 환경에서 더 현실적인 속도와 사용성 기대

공식 참고:

- Cloud API: `https://docs.ollama.com/cloud`
- Authentication: `https://docs.ollama.com/api/authentication`
- Pricing: `https://ollama.com/cloud`
- Model library: `https://ollama.com/library/gpt-oss`

## 필요한 환경변수

루트 `.env`에 아래 값을 넣는다.

```env
API_LLM_PROVIDER=ollama
API_LLM_OLLAMA_BASE_URL=https://ollama.com/api
API_LLM_OLLAMA_API_KEY=...
API_LLM_OLLAMA_MODEL=gpt-oss:20b-cloud
API_LLM_OLLAMA_TIMEOUT_SEC=20
```

## 어떤 값을 직접 넣어야 하나?

### 1. 직접 꼭 넣어야 하는 값

- `API_LLM_PROVIDER`
  - `template`에서 `ollama`로 바꿔야 함
- `API_LLM_OLLAMA_API_KEY`
  - 직접 발급받아서 넣어야 함

### 2. 보통 그대로 써도 되는 값

- `API_LLM_OLLAMA_BASE_URL=https://ollama.com/api`
- `API_LLM_OLLAMA_MODEL=gpt-oss:20b-cloud`
- `API_LLM_OLLAMA_TIMEOUT_SEC=20`

## API Key 발급 방법

Ollama 공식 문서에 따르면 `https://ollama.com/api`를 직접 호출할 때는 API key 인증이 필요하다.

공식 참고:

- `https://docs.ollama.com/api/authentication`

절차:

1. `https://ollama.com` 에 로그인하거나 계정을 만든다.
2. 브라우저에서 API key 설정 페이지로 이동한다.
   - `https://ollama.com/settings/keys`
3. 새 API key를 생성한다.
4. 생성된 key를 복사해서 `.env`의 `API_LLM_OLLAMA_API_KEY`에 넣는다.

예:

```env
API_LLM_OLLAMA_API_KEY=ollama_xxxxxxxxxxxxxxxxx
```

주의:

- API key는 민감정보라서 git에 커밋하면 안 된다.
- 팀원마다 같은 key를 공유할 수도 있지만, 가능하면 개인별 또는 팀 공용 비밀 관리 방식으로 다루는 게 좋다.

## 로컬에서 적용하는 순서

1. 루트 `.env` 열기
2. 아래 값 추가 또는 수정

```env
API_LLM_PROVIDER=ollama
API_LLM_OLLAMA_BASE_URL=https://ollama.com/api
API_LLM_OLLAMA_API_KEY=발급받은_키
API_LLM_OLLAMA_MODEL=gpt-oss:20b-cloud
API_LLM_OLLAMA_TIMEOUT_SEC=20
```

3. `api-server` 재시작
4. `/chat` 요청 테스트

## 빠른 확인 포인트

정상이라면 `/chat` 응답에서:

- `answerMode`가 `ollama`
- `reason`에 Ollama 모델명이 포함

실패 후 fallback이면:

- `answerMode`가 `template`
- `reason`에 `Ollama fallback triggered`가 포함

## 대안

### 더 강한 모델을 쓰고 싶을 때

```env
API_LLM_OLLAMA_MODEL=gpt-oss:120b
```

또는 cloud 계열을 직접 시도할 수 있다.

다만 무료 플랜에서는 usage 한도와 응답 속도를 꼭 같이 봐야 한다.

### 로컬 Ollama를 쓰고 싶을 때

```env
API_LLM_PROVIDER=ollama
API_LLM_OLLAMA_BASE_URL=http://localhost:11434/api
API_LLM_OLLAMA_API_KEY=
API_LLM_OLLAMA_MODEL=gpt-oss
```

Ollama 공식 문서 기준으로 로컬 `http://localhost:11434`는 별도 인증이 필요 없다.

## 지금 구현 범위

현재 구현은:

- 검색된 memory hit를 1~2개 context로 묶어 LLM에 전달
- 한국어로 짧고 자연스럽게 답변 생성
- 근거가 없으면 지어내지 않도록 system prompt 제한
- 호출 실패 시 template 답변 fallback

아직 안 한 것:

- multi-turn conversation memory
- conversationId 기반 문맥 유지
- LLM answer quality 평가/비교 자동화
- prompt 버전 관리

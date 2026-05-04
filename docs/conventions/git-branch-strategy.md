# Git Branch Strategy

- `main`: 운영 기준 브랜치
- `develop`: 통합 개발 브랜치
- `feat/*`: 기능 개발
- `fix/*`: 버그 수정

## Working Branch Names

- 작업 브랜치는 백로그 카드 단위로 만든다.
- 하나의 작업 브랜치는 하나의 백로그 항목을 기준으로 한다.
- 새 작업은 `git switch -c feat/<english-slug>` 형식으로 시작한다.
- 브랜치 이름은 영어 소문자와 하이픈을 사용한다.
- 버그 수정 작업은 `fix/<english-slug>` 형식을 사용한다.

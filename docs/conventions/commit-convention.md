# Commit Convention

- `feat:` 기능 추가
- `fix:` 버그 수정
- `refactor:` 구조 개선
- `docs:` 문서 수정
- `chore:` 운영 및 설정 변경

## Work Handoff

- 작업은 반드시 백로그 카드 단위로 진행한다.
- Codex는 작업 시작 전에 영어 형식의 작업 브랜치를 만든다.
  - 예: `git switch -c feat/<english-slug>`
- 주어진 작업을 완료한 뒤 사용자가 직접 실행할 수 있도록 `add`, `commit`, `push`, `PR` 명령어를 순서대로 제시한다.
- PR 제목은 영어로 작성한다.
- PR 본문 메시지는 상세한 한국어로 작성한다.

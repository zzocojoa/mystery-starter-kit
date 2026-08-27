## 변경 목적

이 변경이 필요한 이유와 해결하려는 문제를 작성해 주세요.

## 주요 변경

- 변경 내용을 작성해 주세요.

## 검증

- [ ] `.venv/bin/python -m pytest`를 통과했습니다.
- [ ] `.venv/bin/mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests`를 통과했습니다.
- [ ] `.venv/bin/ruff check .`를 통과했습니다.
- [ ] `.venv/bin/python -m build`와 `.venv/bin/python -m pip_audit`를 통과했습니다.
- [ ] 관련 JSON 문서와 Schema의 호환성을 확인했습니다.

## 호환성 영향

- [ ] Production Standard와 Channel DNA의 버전 독립성을 유지합니다.
- [ ] Channel의 명시값을 Standard Default가 덮어쓰지 않습니다.
- [ ] 상위 Artifact 변경 시 하위 Artifact 무효화 범위를 확인했습니다.
- [ ] Reference 원문과 Example이 Production Agent Context에 포함되지 않습니다.
- [ ] Schema Major 변경 또는 Migration이 필요하면 아래에 기록했습니다.

## 추가 확인 사항

리뷰어가 특별히 확인해야 할 내용이 있으면 작성해 주세요.

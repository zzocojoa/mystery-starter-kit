# 기여 방법

## 작업 흐름

1. 최신 `main`에서 `feature/`, `fix/`, `docs/`, `chore/` 중 하나의 접두사로 브랜치를 만든다.
2. 변경 범위에 맞는 테스트를 추가하고 로컬 품질 검사를 실행한다.
3. Pull Request 템플릿의 검증 및 호환성 항목을 작성한다.
4. 필수 CI가 모두 통과한 후 Squash Merge한다.

## 로컬 검증

```bash
.venv/bin/python -m pip install 'pip>=26.2'
.venv/bin/pytest
.venv/bin/mypy VALIDATORS tests
.venv/bin/ruff check .
.venv/bin/python -m build
.venv/bin/python -m pip_audit
```

## 변경 원칙

- Required Capability는 반드시 필요한 최소 항목만 유지한다.
- 새 Channel 기능은 먼저 Optional Capability로 도입한다.
- `content_version` 변경을 호환성 실패 사유로 사용하지 않는다.
- Schema Major 변경은 Migration 또는 Adapter 설계와 함께 제안한다.
- 코드 주석은 한국어로 작성한다.

# 기여 방법

## 작업 흐름

1. 최신 `main`에서 `codex/` 접두사 브랜치를 만든다.
2. 변경 기능의 문서, Schema/Contract, Validator, Test를 함께 갱신한다.
3. 구현 매트릭스의 증거 파일을 확인한다.
4. 로컬 품질 검사 후 Pull Request 템플릿을 작성한다.
5. Python 3.11·3.14 CI가 모두 통과하면 Squash Merge한다.

## 로컬 검증

```bash
.venv/bin/python -m pip install 'pip>=26.2' 'setuptools>=83'
.venv/bin/python -m pip install '.[dev]'
.venv/bin/python -m pytest
.venv/bin/mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests
.venv/bin/ruff check .
.venv/bin/python -m build
.venv/bin/python -m pip_audit
```

## 변경 원칙

- Required Capability 이름은 Compatibility Contract에서만 관리한다.
- 새 Channel 기능은 먼저 Optional Capability로 도입한다.
- `content_version` 변경을 Compatibility 실패 사유로 사용하지 않는다.
- Schema Major 변경은 Migration 또는 Adapter 설계와 함께 제안한다.
- 상위 Artifact 변경 시 Dependency Graph의 하위 Artifact를 재검증한다.
- Production Agent Context에 Reference 원문과 `EXAMPLES/`를 넣지 않는다.
- Provider Adapter는 공통 Descriptor·Request·Response Schema와 Conformance Test를 제공한다.
- Runtime Task가 Agent Manifest 읽기·쓰기 권한을 확장하지 않게 한다.
- 코드 주석은 한국어로 작성한다.
- 관련 없는 변경을 되돌리지 않는다.

# Mystery Starter Kit v1.3

[![CI](https://github.com/zzocojoa/mystery-starter-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/zzocojoa/mystery-starter-kit/actions/workflows/ci.yml)

Channel의 정체성을 유지하면서 Story 구조와 인과를 반복하지 않도록 설계한 미스터리 제작 Starter Kit다. Compatibility Negotiation, Full Story DNA, 10개 Agent Contract, Artifact Dependency Invalidation, Continuity/Causal/Novelty/Reference/Channel QA, 14개 Production Gate를 실행 코드로 제공한다.

## 빠른 시작

```bash
python -m venv .venv
.venv/bin/python -m pip install 'pip>=26.2' 'setuptools>=83'
.venv/bin/python -m pip install '.[dev]'

# 아래 명령은 저장소 Root에서 실행한다.
.venv/bin/mystery-kit init PRJ-002
.venv/bin/mystery-kit compat PROJECTS/PRJ-002
.venv/bin/mystery-kit variations PROJECTS/PRJ-002 \
  --seed "공장 교대 중 사라진 작업자" \
  --count 5
.venv/bin/mystery-kit approve PROJECTS/PRJ-002 VAR-03
.venv/bin/mystery-kit precheck PROJECTS/PRJ-002
```

Reference 기반 Project는 후보 생성 전에 원문 JSON을 Project 밖에 보관하고 정제 Profile만 만든다.

```bash
.venv/bin/mystery-kit reference-profile PROJECTS/PRJ-002 /secure/reference-source.json
```

승인 후보를 바탕으로 `01_CASE`부터 `09_PRODUCTION`까지 Artifact를 작성한 뒤 전체 Gate를 실행한다.

```bash
.venv/bin/mystery-kit validate PROJECTS/PRJ-002
.venv/bin/mystery-kit register PROJECTS/PRJ-002
```

`validate`는 `08_QA`의 개별 보고서와 통합 보고서, `00_PROJECT/project_state.json`, Change Log를 갱신한다. `register`는 `PRODUCTION_READY` Project만 Story Library에 추가한다. 종료 코드는 `PASS=0`, Gate 실패 `=1`, 입력·구성 오류 `=2`다.

`compat`는 Project ID가 포함된 Compatibility Report를 만들고 `GATE-00`을 통과시킨다. Compatibility와 `GATE-00`이 모두 PASS가 아니면 `variations`는 실행되지 않는다.

## Compatibility 단독 진단

Project와 무관하게 Channel Contract만 진단할 때는 다음 명령을 사용한다. 이 출력은 Project Artifact가 아니므로 `PROJECTS/` 아래에 저장하지 않는다.

```bash
.venv/bin/mystery-compat \
  --contract STANDARD/compatibility_contract.json \
  --defaults STANDARD/standard_defaults.json \
  --channel CHANNELS/mystery_main/channel_dna.json \
  --contract-schema STANDARD/schemas/compatibility_contract.schema.json \
  --defaults-schema STANDARD/schemas/standard_defaults.schema.json \
  --channel-schema STANDARD/schemas/channel_dna.schema.json \
  --output compatibility_report.json
```

## 구조

- `STANDARD/`: v1.3 표준, Contract, Policy, Catalog, Dependency Graph, JSON Schema
- `CHANNELS/`: 독립 Version의 Channel DNA
- `AGENTS/`: 10개 Agent Prompt와 실행 Manifest
- `TEMPLATES/PROJECT/`: `00_PROJECT`~`09_PRODUCTION` Scaffold
- `VALIDATORS/`: CLI, 상태 머신, Pipeline과 QA Engine
- `STORY_LIBRARY/`: Production Ready Story/Causal Fingerprint History
- `tests/`: 정상·실패·경계·Disk E2E 자동 검증

상세 규칙은 [Production Standard](STANDARD/mystery_production_standard_v1.3.md), 구현 증거는 [v1.3 구현 매트릭스](docs/01-plan/v1.3-implementation-matrix.md)에서 확인할 수 있다.

## 로컬 품질 검사

```bash
.venv/bin/python -m pytest
.venv/bin/mypy VALIDATORS tests
.venv/bin/ruff check .
.venv/bin/python -m build
.venv/bin/python -m pip_audit
```

## GitHub 운영

모든 변경은 `main`에서 분기한 `codex/` 브랜치와 Pull Request를 통해 반영한다. CI의 Python 3.11·3.14 검증이 모두 통과해야 병합할 수 있으며 Squash Merge를 기본으로 사용한다. 자세한 절차는 [GitHub 운영 가이드](docs/04-deploy/github-operations.md)를 따른다.

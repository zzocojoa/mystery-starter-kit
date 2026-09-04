# Installed CLI Resource Hotfix 검증 기록

이 문서는 Hotfix 병합 전의 구현·로컬 검증 증거다. Exact-head CI 및 Human Merge는
PR에서 별도로 확인해야 하며, 이 문서 자체는 최종 main 완료 선언이 아니다.

## 1. PR #36 기준과 Hotfix 범위

- PR #36: `MERGED`, Squash Commit `0b4fbd5a2c9e10b99551b91a4981e0cb08e25f1f`.
- Squash Tree: `4dbc4881a9eb11c7b323be5025f477f66c7083be`, Corrected Stack Tree와 동일.
- Hotfix 시작 시 최신 `origin/main`은 위 Squash Commit과 동일하며 선조 관계 PASS.
- Branch: `codex/installed-cli-resource-resolution-fix`, Base: `main`.
- 목적: 설치형 `validate`·`audit`의 Repository Resource 해석만 수정한다.
- 기존 Caller의 명시적 Graph 전달 및 회귀 테스트 변경은 Human 승인 범위다.
- package version `1.6.1` 유지: 검사 시 Git tag와 GitHub Release가 없고,
  pip-audit도 이 패키지를 PyPI 미등록 로컬 패키지로 보고했다. 배포·등록은 하지 않는다.

## 2. 수정 전 재현

Linux Debian / Python 3.11.16에서 깨끗한 기준 checkout을 전체 검증했다.
Ruff PASS, strict mypy 154 files PASS, pytest **777 PASS**, build PASS,
pip-audit PASS, runtime doctor PASS.

기준 checkout에서 만든 non-editable wheel을 새 venv에 설치하고, `PYTHONPATH`를
제거한 실제 Console Script로 외부 PRJ-006 복사본을 검증했다.

```text
CWD: /work/main
Project: /work/baseline-projects/PRJ-006
Command: /work/baseline-installed/venv/bin/mystery-kit validate <Project>
Import: /work/baseline-installed/venv/lib/python3.11/site-packages/VALIDATORS/pipeline.py
Exit: 2
Missing: /work/baseline-installed/venv/lib/python3.11/site-packages/STANDARD/dependency_graph.json
```

원래 예외 연결도 직접 기록했다. CLI는 `InputFileNotFoundError`를 Exit 2로 처리하지만,
원인 Traceback은 `run_validate → audit_project → full_validation_report →
run_production_validation → required_channel_artifact_issues → load_json_object`의
module-relative `STANDARD` 읽기였다. `production_text_issues`에도 같은 결함이 있었다.

## 3. Resource Assumption Inventory

A = wheel 내부 Resource, B = Repository Contract, C = Project Runtime Data,
D = 테스트 전용 Resource. 설치 위치를 Repository로 간주하는 경로와 명시 Root를
전달받는 경로를 분리해 조사했다.

| 파일 / 함수 | 기존 Root 출처 | 분류 | 설치형 동작과 조치 |
|---|---|---|---|
| `VALIDATORS/pipeline.py` / `required_channel_artifact_issues` | `__file__.parents[1]` | B | 결함. Graph 인자로 교체, 내부 I/O 제거 |
| 동일 / `production_text_issues` | `__file__.parents[1]` | B | 같은 결함. 동일 Graph를 전달 |
| 동일 / Artifact loader 함수들 | Project Path + 전달된 Graph | C | Project 복사본을 읽음. 유지 |
| `VALIDATORS/production_cli.py` / `run_validate`, `run_audit` | import 시 CWD 전역값 | B/C | 호출 시 완전한 Root 하나를 명시적으로 선택 |
| 동일 / init, variation, task, editorial, finalize, register | CWD 또는 Project 경로 | B/C | 진단 경로 밖 제작·변경 명령. 재설계하지 않음 |
| `VALIDATORS/gate_transaction.py` / `audit_project` | Caller Root | B/C | Graph 한 번 로드·검증 후 모든 감사 계층에 전달 |
| 동일 / `full_validation_report` | Caller Root에서 Graph 재로드 | B/C | 재로드 제거, 전달된 동일 Graph 사용 |
| 동일 / `validate_gate_overlay` | Caller Graph | B/C | 기존 Graph를 Gate Validator에 전달 |
| 동일 / 미사용 `ROOT` | `__file__.parents[1]` | B | 미사용 전역 가정 제거 |
| `RUNTIME/gate_control.py` / `validate_gate`, `validation_report_through` | Graph 인자 없음 | B | 필수 명시 인자 추가 및 하위 호출 연결 |
| `RUNTIME/core_tasks.py` / `core_task_outputs` | 이미 로드한 Graph | B/C | 기존 인자 전달만 추가 |
| 동일 / `runtime_validation_inputs_for_project` | Caller Root / Version Pin | B | Root 하나의 Channel·Schema·Profile을 읽음. 유지 |
| `RUNTIME/engine.py` / `execute_existing_run` | Caller Root / 이미 로드한 Graph | B/C | 기존 Graph 인자 전달만 추가 |
| `RUNTIME/contracts.py`, `RUNTIME/planner.py` | 명시 Repository Root | B | 런타임 계약·계획 경로. 유지 |
| `RUNTIME/cli.py` / doctor 등 | `--repository-root`, 기본 CWD | B | 기존 명시 Root 지원. 설치형 doctor PASS |
| `RUNTIME/human_inputs.py`, `approvals.py`, `event_store.py` | module-local `schemas` | A | wheel에 선언된 내부 Schema. 정상이며 유지 |
| `VALIDATORS/config_admission.py` | 명시 Root 또는 Project 조상 | B/C | Admission 경로 유지. 감사 진입은 선택된 Root 사용 |
| `VALIDATORS/variation.py` / `verified_v2_runtime` | module-relative Root | B | 직접 생성 API, validate/audit 경로 아님. 승인 제외 |
| `VALIDATORS/version_immutability.py` | 명시 실행 CWD | B | 개발용 Git 검사. 유지 |
| `tests/**` Root 및 Fixture 참조 | 테스트 파일 위치 / 임시 Repository | D | Caller 인자와 설치 회귀 테스트만 변경 |

`STANDARD`, `CHANNELS`, `AGENTS`, `STORY_LIBRARY`를 wheel에 복사하지 않았다.
wheel ZIP과 Resource-open instrumentation이 이를 검증한다.

## 4. 선택한 계약과 변경 파일

`resolve_repository_resource_root(explicit_root, project_path, working_directory)`는
명시 Root → Project 조상 → CWD 조상 순으로 **완전한 Root 하나**만 반환한다.
명시 Root가 잘못되면 다른 Root로 대체하지 않는다.

필수 Sentinel: `pyproject.toml`, `STANDARD/dependency_graph.json`,
`CHANNELS/mystery_main/channel_manifest.json`, `RUNTIME/contracts/runtime_tasks.json`,
`AGENTS/manifest.json`, `STORY_LIBRARY/novelty_index.json`.

실패는 `ConfigurationError`에 JSON `code`, `message`, `context`를 담아 Exit 2로
종료한다. `REPOSITORY_RESOURCE_ROOT_NOT_FOUND`와 검사 Root·누락 Sentinel을 포함하며,
사용자에게 raw `FileNotFoundError` Traceback을 노출하지 않는다.

변경은 위 Runtime/Validator 6개 기존 파일, 새 `repository_resources.py`, 기존 호출부
테스트 5개, 새 설치 회귀 테스트, CI smoke 1개 Step, README CLI 안내, 이 보고서로 한정한다.
Dependency Graph·Channel·Profile·Schema·Fixture·제작 정책 내용은 변경하지 않는다.

## 5. 설치·Root 회귀 검증

`tests/test_installed_cli_resources.py`: **23 PASS**.
독립 명령 `python -m pytest -v tests/test_installed_cli_resources.py -k wheel`:
**11 PASS**, 12 deselected.

| 실행 문맥 | validate | audit |
|---|---|---|
| Source checkout, 외부 PRJ-006 복사본 | PASS | PASS |
| 독립 venv editable Console Script | PASS | PASS |
| 독립 venv non-editable wheel, Repository CWD | PASS | PASS |
| non-editable wheel, 외부 CWD + 명시 Root | PASS | PASS |
| Root 없음 + 외부 CWD + 독립 Project | 구조화 Exit 2 | 구조화 Exit 2 |
| 잘못된 명시 Root + 정상 Repository CWD | 구조화 Exit 2 | 구조화 Exit 2 |
| 다른 완전한 Project 조상·CWD + 명시 Root 충돌 | 명시 Root만 사용 | 명시 Root만 사용 |

추가 검증: 6개 Sentinel 각각의 누락, Project/CWD 조상 탐색, 상대 명시 Root,
순수 Validator의 I/O 금지·입력 불변성, 실제 설치 Import 경로, wheel-installed doctor.
충돌 Root subprocess의 Resource-open 기록은 선택 Root 바깥 계약 읽기가 없고,
Graph open이 정확히 한 번임을 확인한다.

Graph SHA-256: `2c4b7208a2b8e7c14e24b4dd58201bdc0eb60cdb387c7f11f0b7665d986424ce`.

## 6. 독립 설치형 PRJ-006 진단

테스트 Fixture 외에도 build 결과 wheel을 `/work/hotfix-wheel-standalone` 새 venv에
설치했다. Import는 이 venv의 `site-packages/VALIDATORS/pipeline.py`다.
`/work/hotfix-external/PRJ-006` 복사본에서 실제 Console 명령을 실행했다.

```text
validate (Repository CWD): PASS, Exit 0
audit (외부 CWD + --repository-root /work/main): PASS, Exit 0
GATE-00~13: 모두 PASS
project_state: EDITORIAL_REVIEW_REQUIRED
editorial_approved: false
production_ready: false
state_unchanged: true
snapshot_consistent: true
trace_count: 146
missing_gate_traces: []
process_issues: []
```

State, Trace, Canonical Artifact는 유지한다. 허용된 진단 출력은 복사본의
`08_QA/audit_report.json`뿐이며 원본 PRJ-006은 수정하지 않는다.

## 7. 기존 회귀·보호 Byte

별도 표적 회귀 **80 PASS**: prelanding compatibility 18개, Source Fixture 57개,
실제 GATE-07 Fact/Clue 거부 2개, R1/R2 Gate Transaction 2개,
GATE-00~13 Runtime 1개.

Channel 1.1/2.0/2.1, Readable Report 1.0/2.0/2.1 OWNER_BOUND_1,
Novelty Precheck 1.1/1.2를 유지한다. R1은 `VICTIM / WORKPLACE / WORKPLACE`이며
MUT-01~05 검증을 유지한다. MUT-04는 비선택 후보 격리이므로 정상 수용이 기대값이다.

보호 경로 `PROJECTS`, `STORY_LIBRARY`, `CHANNELS`, `STANDARD`, `tests/fixtures`의
추적 파일 SHA-256 목록이 수정 전후 동일하다. 목록 자체 SHA-256:
`6d80d2a16e9b25d11c6e83d84c6816e29f1b05b83e1c1cf41c75535326fd2d97`.

- PRJ-006 Tree: `f8021e4164ff83dfa8cd665ee557a43c67b1f5c6`.
- Story Library Tree: `e6330aa1f967e4db0ab06ce1e15525292420a478`.
- `PROJECTS/PRJ-005`: 없음.
- Machine/Readable/Reenactment Script, 등록 Version 및 R1/R2 데이터: 변경 0.

## 8. 전체 로컬 검증과 제출 경계

실행 환경: Linux Debian / Python 3.11.16 / aarch64. Docker image digest:
`python@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534`.

| 검사 | 결과 |
|---|---|
| Ruff | PASS |
| strict mypy | PASS, 156 files |
| 전체 pytest | **800 PASS**, 349초, errors/failures/skipped 모두 0 |
| package build | wheel + sdist PASS |
| pip-audit | 알려진 의존성 취약점 없음. 로컬 패키지 자체는 PyPI 미등록으로 audit 제외 |
| runtime doctor | PASS |
| Version Immutability, base `0b4fbd5...` | PASS |
| 독립 wheel smoke | 11 PASS |
| 보호 Byte 비교 / diff whitespace | PASS |

원본 로그·종료 코드·시간·JUnit·수정 전 Traceback은 별도 Evidence Bundle에 보존한다.
PR에는 정확한 Hotfix Head와 Python 3.11·3.14 CI 및 각 wheel smoke 결과를 연결한다.

## 9. Human Merge 및 최종 main

Hotfix PR을 자동 Merge하지 않는다. Human이 GitHub UI에서 Squash Merge한 뒤,
새 main checkout과 새 wheel/venv에서 중단된 Post-merge PHASE 7~10을 재실행해야 한다.
현재 Hotfix 로컬 PASS는 병합 후 최신 main PASS를 대신하지 않는다.

```text
HOTFIX_EXACT_HEAD_CI = NOT_YET_SUBMITTED
HOTFIX_HUMAN_MERGE = NOT_PERFORMED
POST_HOTFIX_MAIN_CI = NOT_RUN
WORKFLOW_LANDING_COMPLETE = NO
NEW_SCRIPT_GENERATION_READY = NO
SUPPORTED_ENVIRONMENT = Linux/WSL
NATIVE_WINDOWS_STATUS = HOLD
```

Human Editorial Approval, production-finalize, register, 신규 Project 생성,
PRJ-005 작업, 장르 로직 변경, rebase, force push, 타 PR 병합은 수행하지 않았다.

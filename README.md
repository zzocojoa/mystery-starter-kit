# Mystery Starter Kit

- Package: `1.5.0`
- Production Standard: `1.3.3`
- Active Channel Content: `2.0.0`

[![CI](https://github.com/zzocojoa/mystery-starter-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/zzocojoa/mystery-starter-kit/actions/workflows/ci.yml)

Channel의 정체성을 유지하면서 Story 구조와 인과를 반복하지 않도록 설계한 미스터리 제작 Starter Kit다. Project별 Channel Content Version Pinning, Compatibility Negotiation, Full Story DNA, Presentation Contract v2.1, 10개 Agent Contract, Provider 독립 LLM Agent Runtime v1.0, Artifact Dependency Invalidation, Continuity/Causal/Novelty/Reference/Channel QA, 14개 Production Gate를 실행 코드로 제공한다.

## Codex App 운영 모드

실제 작품 제작의 기본 실행자는 저장소 내부 Provider가 아니라 Codex App이다. [공식 데스크톱 앱 안내](https://learn.chatgpt.com/docs/app)에 따라 ChatGPT 계정으로 로그인하고 이 저장소 폴더를 연다. Codex는 [공식 AGENTS.md 동작](https://learn.chatgpt.com/docs/agent-configuration/agents-md)에 따라 루트 `AGENTS.md`를 Project Context로 읽고, `AGENTS/manifest.json`의 역할·권한과 Artifact Schema에 맞춰 Project 파일을 작성한다.

저장소에는 API Key나 외부 LLM Provider 설정이 필요하지 않다. App의 계정 인증과 저장소의 Runtime Provider는 별도 경계다.

### 1. 저장소 준비

```bash
python -m venv .venv
.venv/bin/python -m pip install 'pip>=26.2' 'setuptools>=83'
.venv/bin/python -m pip install '.[dev]'

# 아래 명령은 저장소 Root에서 실행한다.
.venv/bin/mystery-kit init PRJ-002
.venv/bin/mystery-runtime doctor
```

### 2. Codex에 제작 요청

Codex App에서 다음 범위가 명확한 요청으로 시작한다.

```text
루트 AGENTS.md와 저장소 Contract, Schema를 먼저 읽어라.
PROJECTS/PRJ-002의 현재 Gate Task를 열어 격리 Workspace에서만 작업하라.
Task Record의 reads와 writes를 확장하지 말고 Canonical Project와 State를 직접 수정하지 마라.
현재 Gate Validator를 통과한 뒤 Task를 제출하고 Process Trace를 확인하라.
```

각 Gate는 하나의 Transaction으로 실행한다. `task-open`은 의존 순서의 CORE Task를 먼저 실행하고, 처음 만나는 LLM Task 하나의 `allowed_reads`와 `allowed_writes`만 연다. 출력된 `workspace`에서 현재 허용 파일만 수정한 뒤 같은 Gate로 제출한다.

```bash
.venv/bin/mystery-kit task-open PROJECTS/PRJ-002 GATE-05
.venv/bin/mystery-kit task-status PROJECTS/PRJ-002
# 출력된 Staging Workspace의 현재 allowed_writes만 Codex가 편집한다.
.venv/bin/mystery-kit task-submit PROJECTS/PRJ-002 GATE-05
# 응답이 AWAITING_LLM이면 새 current_task_id의 allowed_writes만 작성하고 다시 제출한다.
.venv/bin/mystery-kit task-status PROJECTS/PRJ-002
.venv/bin/mystery-kit task-submit PROJECTS/PRJ-002 GATE-05
.venv/bin/mystery-kit task-return PROJECTS/PRJ-002 script_writer --actor critic --reason "대본 수정 필요"
```

각 제출은 현재 Task의 writes Allowlist, Artifact Owner, Future Gate 수정, 입력 Hash Drift와 Schema를 검사한다. 통과하면 같은 Workspace에서 후속 CORE를 실행하고, 다음 LLM Task가 있으면 Canonical 중간 Commit 없이 새 `current_task_id`와 최소 권한을 반환한다. Gate의 모든 Task와 Gate Validator가 PASS한 경우에만 Artifact·Project State·`00_PROJECT/process_trace.jsonl`을 기존 Write-ahead Transaction으로 함께 Commit한다. 다음 Gate를 열기 전에는 이미 통과한 Canonical Artifact를 Project State Hash와 대조한다. 작업을 폐기하려면 `task-abort`를 사용한다. Critic Issue는 `task-return`으로 Owner Agent Gate에 반환하며, 새 `process_revision`의 Trace만 재작업 적합성에 사용한다. `AUTO_CONTINUE`는 정상 Task 통과 뒤 의존 가능한 CORE 또는 다음 LLM Task로 진행할 수 있다는 뜻이며 여러 Gate를 한꺼번에 작성한다는 뜻이 아니다.

새 Scaffold는 `script_source_mode: SCREENPLAY_UNITS`와 `REENACTMENT_CHARACTER_SCRIPT 1.0.0` Output Profile을 고정한다. GATE-08에서 Codex가 작성하는 유일한 새 창작 출력은 `screenplay_units.json`이다. 제출 뒤 CORE가 Layer Script, Broadcast Master와 `reenactment_character_script.md`를 만들고, GATE-09가 현재 입력 Hash에 결속된 `reenactment_export_report.json`을 계산한다. GATE-13은 이 Report가 오류 없는 `NEEDS_REVIEW`일 때만 동일 bytes를 Production 경로로 전달한다. `script_source_mode` 필드가 없는 기존 Project는 `LEGACY_MARKDOWN` Task 순서와 Artifact를 그대로 사용한다.

재연극 목표시간이 필요하면 `target_reenactment_minutes`와 `reenactment_runtime_tolerance_ratio`를 함께 설정한다. 이 값은 방송 전체의 `target_runtime_minutes`와 별도이며 방송 목표를 넘을 수 없다. CORE는 Output Profile이 포함한 Unit이 결속된 Drama·Narration Segment만 합산하고 Panel 등 제외 Segment를 Report에 따로 기록한다. Editorial evidence는 `WORD_COUNT_ESTIMATE`, `TABLE_READ`, `RECORDED_AUDIO`를 구분하며, Unit·Profile·Presentation 입력이 바뀌면 기존 측정 Hash를 거부한다.

### 3. 감사, Editorial 승인과 등록

```bash
.venv/bin/mystery-kit validate PROJECTS/PRJ-002
.venv/bin/mystery-kit audit PROJECTS/PRJ-002
.venv/bin/mystery-kit editorial-approve PROJECTS/PRJ-002 \
  --actor reviewer@example.com \
  --reason "최종 방송 적합성 검토 완료"
.venv/bin/mystery-kit production-finalize PROJECTS/PRJ-002
.venv/bin/mystery-kit register PROJECTS/PRJ-002
```

`validate`는 현재 파일 집합의 14개 Gate 정합성을 진단하고 `validation_report.json`과 파생 QA Report를 기록한다. `audit`는 같은 Artifact 검증에 Gate별 Process Trace 완전성을 더해 `audit_report.json`에 기록한다. 둘 다 `current_gate`, Project Status, Artifact `CLEAN` 상태나 기존 실행 이력을 바꾸지 않는다. 손상된 State를 Artifact에서 명시적으로 복구할 때만 `rebuild-state PROJECT --force`를 사용하며, 이 명령도 Process Trace나 Human Editorial 승인을 만들어 내지 않는다.

GATE-13 PASS의 도착 상태는 `EDITORIAL_REVIEW_REQUIRED`다. Editorial Review v1.2는 검토자·검토 시각·Artifact Hash와 `artifact + selector_type + selector_id + excerpt_hash`를 보존한다. Validator는 Selector를 현재 Artifact에서 다시 해석해 근거 위조와 유효하지 않은 ID를 차단한다. `WORD_COUNT_ESTIMATE`는 Editorial PASS 증거로는 사용할 수 있지만 Production Finalize를 허용하지 않는다. Finalize에는 방송 Panel과 설정된 재연극 Runtime 모두 `TABLE_READ` 또는 `RECORDED_AUDIO` 실측이 필요하다.

Continuity Critic의 `editorial_review.json`이 PASS여도 이는 기술적 Editorial 검토 결과일 뿐 Human Approval이 아니다. Human Actor와 Reason을 기록한 `editorial-approve` 전에는 승인되지 않는다. `production-finalize`는 `ARTIFACT_COMPLETE + CONTRACT_VALIDATED + PROCESS_CONFORMANT + EDITORIAL_APPROVED`를 모두 요구한다. `register`는 이 조건으로 확정된 `PRODUCTION_READY` Project만 Story Library에 추가한다. 종료 코드는 성공 `0`, 검증 실패 `1`, 입력·구성·Transaction 오류 `2`다.

Presentation Contract v2.1은 `panel_cast.json`, `reaction_segments.json`, Drama/Narration/Panel Reaction Layer Script를 별도 Artifact로 유지한다. Reaction Segment의 `turns[]`는 각 패널 발화별 화자·기능·Clue·Fact·Tone을 보존하며 Validator는 모든 Turn을 대본 순서와 대조한다. `draft_v01.md`와 `final_script.md`는 모든 Segment를 방송 순서대로 한 번씩 포함하고, Edit Script는 계획된 절대 Timecode를 보존한다. Panel Reaction 비율은 Segment `duration_sec` 합으로 계산한다.

`project_constraints.production_limits.enforce_final_footprint`가 켜진 Project에서는 Scene Card가 장소·배우·아역·차량·특수효과·폭력·제작 복잡도를 선언한다. `scene.compute_production_footprint` CORE Task가 GATE-07에서 Character와 Actual Timeline을 대조해 합계를 계산하며, GATE-13은 CORE Production Manifest와 Shooting Script의 정규 Scene Marker를 대조한다. 기존 v1.1 Project의 기본값은 `false`다.

## Runtime Core Flow

Built-in `fake` Adapter는 외부 서비스를 호출하지 않는 결정론적 Test Double이다. `mystery-runtime`의 14개 Gate, Staging, Schema 검증, 원자 Commit, Provenance를 로컬과 CI에서 재현하지만 실제 Story·Character·Script를 제작하는 용도가 아니다.

격리된 Test Project에서만 다음 Golden Path를 사용한다.

```bash
.venv/bin/mystery-runtime plan PROJECTS/PRJ-RUNTIME-TEST
.venv/bin/mystery-runtime run PROJECTS/PRJ-RUNTIME-TEST --to GATE-13
```

중단된 Run은 Run ID로 조회·승인·재개하거나 취소할 수 있다.

```bash
.venv/bin/mystery-runtime status PROJECTS/PRJ-RUNTIME-TEST
.venv/bin/mystery-runtime approve RUN-... variation.approve \
  --actor reviewer@example.com \
  --reason "후보 구조와 신규성을 검토함"
.venv/bin/mystery-runtime resume RUN-...
.venv/bin/mystery-runtime cancel RUN-...
.venv/bin/mystery-runtime providers
```

사실 기반 Project가 `GATE-01`의 `reference.intake_evidence`에서 `WAITING_HUMAN`으로 대기하면 Human은 원문 전문이 아닌 출처 Metadata, Claim 분류와 공개·임상 Label만 제출한다. 검증된 `FACT`만 Source Case Brief와 Verified Fact Ledger로 투영된 뒤 Variation과 Story Task가 시작된다. 두 보조 명령은 같은 Runtime 입력 경로를 사용한다.

```bash
.venv/bin/mystery-kit evidence-submit PROJECTS/PRJ-RUNTIME-TEST RUN-... evidence-input.json
# 또는
.venv/bin/mystery-runtime submit-input RUN-... reference.intake_evidence evidence-input.json
.venv/bin/mystery-runtime resume RUN-...
```

제출 시 Evidence 문서의 `bound_input_hashes`를 대기 중 Task의 현재 입력 Hash와 대조한다. 일치한 입력만 같은 Run에서 재개되며, 입력 Artifact가 바뀌면 기존 Human Input은 무효다. GATE-01의 Evidence Artifact 묶음과 Source Truth Contract는 하나의 Write-ahead Transaction으로 Commit한다. Contract는 Sources, Claim Evidence, Verified Fact Ledger, Source Subjects, Verified Event Ledger의 Canonical SHA-256과 전체 Bundle Hash를 보존하며 GATE-01·03·04·05, Audit, 모든 LLM Context 구성 직전에 다시 검증된다.

Runtime 종료 코드는 성공 `0`, Runtime·입력·구성 오류 `2`다. Gate 또는 Provider 실패는 구조화 오류로 `run.json`과 `events.jsonl`에 남고 Canonical Artifact는 마지막 통과 Gate 상태를 유지한다.

## Codex App 보조 CLI Flow

Codex App이 필요에 따라 호출할 수 있는 결정론적 제작 보조 명령도 유지한다. 이 흐름은 위 Runtime Core의 Run 승인·Human Input 명령과 별개다.

```bash
.venv/bin/mystery-kit compat PROJECTS/PRJ-002
.venv/bin/mystery-kit variations PROJECTS/PRJ-002 \
  --seed "공장 교대 중 사라진 작업자" \
  --count 5
# EXPLICIT_CRIME_EVENT_POLICY가 활성화되면 Codex가 후보별
# 00_PROJECT/candidate_event_briefs.json을 먼저 작성한다.
.venv/bin/mystery-kit precheck PROJECTS/PRJ-002
.venv/bin/mystery-kit candidate-eligibility PROJECTS/PRJ-002
# Codex가 00_PROJECT/candidate_evaluation.json의 Soft 평가 근거를 작성한다.
.venv/bin/mystery-kit approve PROJECTS/PRJ-002 VAR-03
```

후보 생성과 Soft 점수·근거는 Variation Designer/Codex의 후보 데이터다. Explicit Crime 경로의 Candidate Event Brief는 Novelty, 적격성, 평가와 승인 Hash에 결속되므로 Brief 변경 뒤에는 해당 단계를 다시 실행해야 한다. `candidate_eligibility.json`의 Hard Filter·Novelty 적격성 및 `candidate_approval.json`의 최종 승인 권한은 Runtime Core가 소유한다. 추천 후보가 아닌 적격 후보를 승인할 때만 `approve ... --override --actor ... --reason ...`을 명시한다.

Reference 기반 Project는 후보 생성 전에 원문 JSON을 Project 밖에 보관하고 정제 Profile만 만든다.

```bash
.venv/bin/mystery-kit reference-profile PROJECTS/PRJ-002 /secure/reference-source.json
```

`compat`는 `production_config.channel_content_version`을 `channel_manifest.json`에서 해석하고 Channel ID, Schema/Content Version, DNA SHA-256이 포함된 Compatibility Report를 만든 뒤 `GATE-00`을 통과시킨다. 활성 Channel이 바뀌어도 기존 Project는 생성 당시 버전을 유지한다. Variation Runtime은 Project가 Pin한 Engine·Catalog를 SemVer 호환 범위와 Capability로 해석한 뒤 Versioned Catalog Snapshot과 실제 Python 구현 Aggregate Hash를 검증하고 Entrypoint를 로드한다. 루트 Catalog는 Authoring Source일 뿐 Runtime 대상이 아니다. Compatibility와 `GATE-00`이 모두 PASS가 아니면 `variations`는 실행되지 않는다.

사용자가 주인공·사건 같은 일부 설정을 제공하는 경우 `production_config.json`의 `story_source_mode`를 `USER_CASE`로 설정하고 각 `user_case_constraints`를 `LOCKED`, `FLEXIBLE`, `UNKNOWN`으로 선언한다. `LOCKED` 값은 Variation과 Story DNA에서 변경할 수 없다.

`AGENTS/`는 10개 Agent의 최대 입출력·선행 단계·Gate 계약을 제공한다. `RUNTIME/contracts/runtime_tasks.json`은 이를 확장할 수 없는 실제 호출 단위로 좁히며, Runtime은 LLM 응답을 Canonical 파일에 직접 쓰지 않고 Schema 검증된 Staging Overlay만 Gate 단위로 Commit한다.

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

- `STANDARD/`: v1.3.3 표준, Contract, Policy, Catalog, Dependency Graph, JSON Schema
- `CHANNELS/`: 활성/사용 가능 Content Version Registry와 독립 Version Channel DNA
- `AGENTS/`: 10개 Agent Prompt와 계약 Manifest
- `TEMPLATES/PROJECT/`: 신규 Project용 Channel 2.0, Variation Engine/Catalog 2.0 `00_PROJECT`~`09_PRODUCTION` Scaffold. 최종 Production Footprint 검증을 기본 활성화한다.
- `VALIDATORS/`: CLI, 상태 머신, Pipeline과 QA Engine
- `RUNTIME/`: Provider 독립 실행 엔진, 계약, Schema, Adapter, 보안 경계
- `RUNTIME_ADAPTERS/`: [선택적 In-process·Sidecar Provider 확장 Interface 가이드](RUNTIME_ADAPTERS/README.md)
- `STORY_LIBRARY/`: Draft부터 추적하는 Novelty Index, Published Fingerprints, Append-only History
- `tests/`: 정상·실패·경계·Disk E2E 자동 검증

상세 규칙은 [Production Standard](STANDARD/mystery_production_standard_v1.3.md), [데이터 흐름](docs/01-plan/erd.md), [용어 정의](docs/01-plan/glossary.md), [Schema 계약](docs/01-plan/schema.md), [Runtime v1.0 설계](docs/02-design/llm-agent-runtime-v1.md), 구현 증거는 [v1.3 구현 매트릭스](docs/01-plan/v1.3-implementation-matrix.md)에서 확인할 수 있다. 기여와 보안 절차는 [CONTRIBUTING.md](CONTRIBUTING.md)와 [SECURITY.md](SECURITY.md)를 따른다.

## 로컬 품질 검사

```bash
.venv/bin/python -m pytest
.venv/bin/mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests
.venv/bin/ruff check .
.venv/bin/python -m build
.venv/bin/python -m pip_audit
```

## GitHub 운영

모든 변경은 `main`에서 분기한 `codex/` 브랜치와 Pull Request를 통해 반영한다. CI의 Python 3.11·3.14 검증이 모두 통과해야 병합할 수 있으며 Squash Merge를 기본으로 사용한다. 자세한 절차는 [GitHub 운영 가이드](docs/04-deploy/github-operations.md)를 따른다.

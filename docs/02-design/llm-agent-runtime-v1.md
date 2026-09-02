# LLM Agent Runtime v1.0

## 책임 경계

Runtime은 Agent 계약을 실제 호출 가능한 Task로 좁히고, Provider 생성 결과를 14개 Gate와 Canonical Artifact 체계에 안전하게 연결한다. Story 품질 규칙은 기존 Validator가 소유하며 Runtime은 해당 규칙을 우회하거나 복제하지 않는다.

```text
Agent Manifest ── 최대 권한
      ↓ 부분집합 검증
Runtime Task Catalog ── 최소 Context·Model Profile·Retry·writes
      ↓
Prompt Compiler → Router → Provider Adapter
      ↓
Output Gateway → Staging Overlay → Gate Validator
      ↓ PASS
Write-ahead Transaction → Canonical Artifacts + Project State
```

## Codex App 운영 경계

실제 작품 제작에서는 Codex App이 저장소를 여는 상위 제작 Agent다. Codex는 루트 `AGENTS.md`, Agent Manifest, Task Contract, Artifact Schema를 읽고 권한 범위 안의 Project Artifact 후보를 작성한다. Codex App은 `LLMProvider` 구현이나 Runtime의 HTTP Backend가 아니며, App의 계정 인증을 Provider Credential로 전달하지 않는다.

```text
Codex App
    ↓ task-open / 선행 CORE / 현재 Task reads
AGENTS.md + Agent Manifest + Contract + Schema
    ↓ 현재 Task의 allowed_writes만 작성
Gate Staging Workspace → task-submit → 후속 CORE → 다음 LLM Task
    ↓ Gate 전체 PASS
Atomic Canonical Commit + Project State + Process Trace
    ↓ GATE-13 / Human Editorial Approval
Production Ready → Story Library
```

Codex App은 Canonical Project를 직접 편집하지 않는다. `task-open`은 현재 Gate의 의존 가능한 CORE를 실행한 뒤 첫 LLM Task의 Agent, reads, writes, 입력 Hash, 금지 경로와 Staging Workspace를 고정한다. `task-submit`은 현재 Task의 Future Artifact, 권한, Drift와 Schema를 검사하고 후속 CORE를 실행한다. 다음 LLM Task가 있으면 같은 Transaction에서 최소 권한을 다시 열며, Gate 전체 Validator가 통과할 때만 Commit한다. 이 운영 모드에는 외부 LLM Provider가 필요하지 않다. Built-in FakeProvider는 Provider-independent Runtime의 Staging, Transaction, Hash Drift, Retry, Provenance를 재현하는 CI·E2E Test Double로만 사용한다. 따라서 `mystery-runtime run`의 Fake 출력은 실제 작품 결과로 취급하지 않는다.

통과한 Canonical Artifact는 다음 Task를 열기 전 Project State Hash와 다시 대조한다. Critic Issue는 `task-return`으로 Artifact Owner의 LLM Gate에 반환하며, 목표 Gate 이후 상태를 `DIRTY`로 바꾸고 `process_revision`을 증가시킨다. 과거 Trace는 감사 이력으로 남지만 현재 Revision의 Process Conformance에는 포함하지 않는다.

## 계약

- `runtime_tasks.json`: Task ID, Agent, Executor, Gate, reads, writes, 의존성, Model·Retry·Budget Profile
- `artifact_contracts.json`: Artifact별 Media Type, JSON Schema, 최대 Byte, Commit 정책
- `model_routes.json`: 논리 Model Profile, Capability, Route 순서, Token·시도 Budget
- `provider_registry.json`: Adapter 유형, 환경 변수 Credential 참조, Endpoint, 허용 Data Class
- `runtime_config.json`: 활성 Route Profile과 Runtime 계약 파일 경로
- `runtime_contract.json`: 소비 가능한 Agent Manifest·Dependency Graph Version 범위와 금지 권한

Runtime 시작 시 JSON Schema뿐 아니라 Task가 Agent Manifest 권한을 넓히지 않는지, Task Writer가 Dependency Graph Owner인지, Resource가 Repository 내부이며 `EXAMPLES/`가 아닌지 교차 검증한다.

### Screenplay Unit 실행 경로

새 Scaffold는 `SCREENPLAY_UNITS` mode와 고정 Reenactment Output Profile을 사용한다. GATE-06의 LLM은 Character State Transition만, GATE-08의 LLM은 Canonical Screenplay Unit만 작성한다. 이후 `script.render_screenplay_layers → script.render_broadcast_master → script.render_reenactment_export`와 `script.render_broadcast_readable`은 CORE이며, Trace Marker와 파생 Markdown을 LLM 권한 밖에서 생성한다. GATE-09의 `continuity.validate_reenactment`는 Unit·Cast·Relationship·Event/Harm·Clue/Reveal·Profile·Broadcast Hash로 Report를 재구성하고, GATE-13의 `production.package_reenactment`는 검증된 원문을 byte-identical 사본으로만 전달한다.

`broadcast_readable_script.md`는 같은 Canonical Screenplay Unit, Character, Panel, Reaction, Presentation JSON에서 Source-style 장면 Context, 실제 인물 이름과 Canonical Panel 발화를 결정론적으로 표시하는 정식 GATE-08 Artifact다. GATE-09의 `continuity.validate_broadcast_readable`은 다섯 입력 Hash, 출력 Hash와 Coverage를 `broadcast_readable_report.json`에 기록하고 현재 입력에서 Report를 다시 만들어 stale 결과를 거부한다. GATE-12 Validation은 이 QA Report에 의존하고, GATE-13의 `production.package_broadcast_readable`은 검증된 bytes만 Production 경로로 복사한다. Source·Report·Production Copy는 Dependency Invalidation과 Project State Hash, Process Trace, Editorial Review Hash에 모두 연결된다. Gate 밖의 직접 쓰기 명령은 제공하지 않으며 기존 Broadcast Master의 Marker 문법과 bytes는 바꾸지 않는다.

선택적인 재연극 Runtime target/tolerance는 방송 전체 Runtime과 독립적으로 검증한다. GATE-09 Report는 Output Profile에 포함된 Unit이 결속된 Segment와 제외 Segment, 계획시간을 기록하고, GATE-13 Editorial evidence는 Report 입력 Hash와 측정 방법에 결속된다. 추정은 `WORD_COUNT_ESTIMATE`, 실측은 `TABLE_READ` 또는 `RECORDED_AUDIO`로 구분하며 Unit 변경 뒤 기존 측정을 사용할 수 없다.

기존 Production Config에 `script_source_mode`가 없으면 `LEGACY_MARKDOWN`으로 평가해 `script.write_layers → script.integrate`를 유지한다. 두 경로는 Task Condition으로 상호 배타적이며 같은 Gate 안의 LLM→CORE 전환도 하나의 Staging Overlay에 남아 Gate PASS 전에는 Canonical 중간 Artifact를 Commit하지 않는다.

```text
GATE-06  LLM  character_state_transitions
   ↓
GATE-07  LLM/CORE  scene_cards → production_footprint
   ↓
GATE-08  LLM  screenplay_units
                ↓ CORE
          drama / narration / broadcast master / reenactment script
          broadcast readable script
   ↓
GATE-09  CORE  reenactment_export_report (NEEDS_REVIEW)
               broadcast_readable_report (PASS)
   ↓
GATE-12  CORE  full validation
   ↓
GATE-13  LLM production package → CORE manifest/reenactment/readable copies
               → LLM editorial review
                → CORE gate-final validation
   ↓
EDITORIAL_REVIEW_REQUIRED
   └─ Human only: editorial-approve → production-finalize CLI → register
```

`GATE-13` Task Catalog의 `production.finalize`는 Validation Report와 도착 상태를 확정하는 CORE Gate Task다. Human 승인 뒤 `PRODUCTION_READY`로 전이하는 `mystery-kit production-finalize` CLI와 이름이 비슷하지만 권한과 상태 전이가 다르다.

| Artifact | 소유자 | 생성 시점 |
|---|---|---|
| `character_state_transitions` | Story Architect LLM | GATE-06 |
| `screenplay_units` | Script Writer LLM | GATE-08 |
| Layer Script, Broadcast Master, 재연 Script, Readable Script | CORE Renderer | GATE-08 |
| `reenactment_export_report`, `broadcast_readable_report` | CORE Validator | GATE-09 |
| Production 문서 | Orchestrator LLM | GATE-13 |
| Production Manifest, 재연·Readable Production copy | CORE | GATE-13 |
| `editorial_review` | Continuity Critic LLM | GATE-13 |
| Editorial Approval | Human Actor | GATE-13 이후 |

Runtime은 ASR이나 음성 전사를 제공하지 않는다. `WORD_COUNT_ESTIMATE`는 계획 검토에만 쓰며, 실제 Production Finalize에는 별도 Table Read 또는 Recorded Audio 측정이 필요하다. 결정론적 Renderer와 Validator가 무결성을 증명해도 대사 자연스러움, 인물 목소리, 반전 설득력과 피해자 존엄성은 Editorial 및 Human 검토 대상이다.

## 실행과 원자성

한 Gate의 Task 출력은 메모리에서 결합한 뒤 Canonical Project를 복제한 Staging Overlay에 기록한다. 기존 Gate Validator가 Overlay 전체를 통과시킨 경우에만 Transaction Record를 `PREPARED`로 남기고 Artifact와 Project State를 교체한다. 중간 교체가 실패하면 모든 백업을 복구해 `ROLLED_BACK`으로 기록한다. Process가 Commit 도중 종료돼 `PREPARED`가 남으면 다음 Run 시작 시 먼저 복구한다. 복구 경로는 Canonical Project와 해당 Transaction의 백업 디렉터리 내부로 제한한다.

Codex Gate Transaction도 이 Overlay와 Write-ahead Commit을 재사용한다. 차이는 Provider 응답 대신 Codex가 현재 LLM Task의 허용 출력만 Workspace에 작성한다는 점이다. 같은 Gate의 CORE와 LLM 의존 순서는 Workspace 안에서 진행되며 중간 Canonical Commit은 없다. Commit 대상에는 Gate 출력과 Project State뿐 아니라 Task별 입력 Hash·변경 경로를 담은 누적 `process_trace.jsonl`도 포함되므로 세 결과는 함께 반영되거나 함께 복구된다.

Project별 Exclusive Lock은 동시에 하나의 Writer만 허용하며, 종료된 Process의 PID가 남긴 Lock만 Inode 재확인 후 회수한다. Provider 호출 전에 캡처한 Canonical 입력 Hash를 Commit 직전에 다시 계산하므로 실행 중 사용자나 다른 Process가 입력을 바꾸면 Commit하지 않는다.

## 상태와 Retry

Run은 `CREATED → PLANNED → RUNNING`에서 시작해 `VALIDATING`, `REVISING`, `WAITING_HUMAN`을 거쳐 `COMPLETED`, `FAILED`, `CANCELLED` 중 하나에 도달한다. 각 Task는 시도 횟수, Provider, 실제 Model, 입력 Hash, Prompt Hash, 오류를 보존한다.

- Transport Timeout·Rate Limit·Unavailable: 같은 Route 제한 재시도 후 다음 구성 Route 허용
- JSON Parse·Schema 오류: 같은 Task의 Format Repair 제한 재시도
- Gate 의미 오류: 검증 Issue와 허용 writes만 포함한 Semantic Revision 제한 재시도
- Refusal·Data Policy·권한 위반: 재시도나 Fallback 없이 즉시 실패
- 최대 시도 초과: Canonical Artifact를 유지하고 Project를 `BLOCKED` 처리한 뒤 실패 기록

`resume`은 마지막 Canonical Gate 다음 단계부터 동일 Run을 재개한다. Human Approval은 Task의 현재 입력 Hash와 결합되며 입력 변경 시 사용할 수 없다. `cancel`은 Durable 요청을 남기고 다음 안전 경계에서 Run을 중단한다.

## 보안과 감사

Prompt 우선순위는 Runtime System Rule, Agent Contract, Task Contract, 비명령성 Context 순이다. Task reads와 명시 Resource만 전달하며 Raw Reference, `EXAMPLES/`, Provider Data Policy 밖의 Class는 Router 이전 또는 Router에서 거부한다. v1.0 LLM Task에는 임의 Shell·파일 쓰기·무제한 HTTP·Credential 읽기 Tool을 제공하지 않는다.

`.runtime/`에는 다음 운영 증거가 저장된다.

- `runs/<run-id>/run.json`: Run과 Task Durable 상태
- `runs/<run-id>/events.jsonl`: Schema 검증된 Append-only Event
- `runs/<run-id>/tasks/...`: Provider Request·Response Attempt
- `runs/<run-id>/gates/...`: Gate별 Staging Overlay
- `transactions/<transaction-id>/`: Write-ahead Record와 Canonical 백업
- `provenance/<artifact>.json`: Content·Input·Prompt·Schema Hash, Provider·Model, Attempt, Transaction

Canonical `00_PROJECT/process_trace.jsonl`은 Runtime과 Codex 양쪽의 Gate별 PASS 및 Process Revision 증거다. `.runtime/codex_tasks/<transaction-id>/task.json`은 Open/Committed/Aborted 권한 Snapshot을 보존한다. `validate`와 `audit`는 이 이력을 재구성하지 않는다.

운영 파일은 Project 결과물이 아니므로 Git에서 제외한다.

## 검증 범위

`tests/runtime/`은 Fake Provider 전체 Gate E2E, 정제 Reference만 Provider로 전달되는 E2E, 권한 밖 출력 시 Canonical 불변성, Retry 소진 시 `BLOCKED`, Format Retry, Human 승인·재개, Active·Stale Lock, Input Drift, Transaction Rollback·Crash Recovery·경로 격리, EXAMPLES·Raw Reference·Tool 차단, In-process와 Sidecar Conformance를 검증한다. `tests/test_gate_transaction.py`는 Codex Workspace의 정상 Commit, Future/권한/사전 Drift 차단, Trace Revision, Owner 반환, 상태 비변경 Audit과 Editorial 분리를 검증한다. CI는 Python 3.11과 3.14에서 기존 Validator 회귀 테스트와 함께 실행한다.

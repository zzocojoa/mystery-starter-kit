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

## 계약

- `runtime_tasks.json`: Task ID, Agent, Executor, Gate, reads, writes, 의존성, Model·Retry·Budget Profile
- `artifact_contracts.json`: Artifact별 Media Type, JSON Schema, 최대 Byte, Commit 정책
- `model_routes.json`: 논리 Model Profile, Capability, Route 순서, Token·시도 Budget
- `provider_registry.json`: Adapter 유형, 환경 변수 Credential 참조, Endpoint, 허용 Data Class
- `runtime_config.json`: 활성 Route Profile과 Runtime 계약 파일 경로
- `runtime_contract.json`: 소비 가능한 Agent Manifest·Dependency Graph Version 범위와 금지 권한

Runtime 시작 시 JSON Schema뿐 아니라 Task가 Agent Manifest 권한을 넓히지 않는지, Task Writer가 Dependency Graph Owner인지, Resource가 Repository 내부이며 `EXAMPLES/`가 아닌지 교차 검증한다.

## 실행과 원자성

한 Gate의 Task 출력은 메모리에서 결합한 뒤 Canonical Project를 복제한 Staging Overlay에 기록한다. 기존 Gate Validator가 Overlay 전체를 통과시킨 경우에만 Transaction Record를 `PREPARED`로 남기고 Artifact와 Project State를 교체한다. 중간 교체가 실패하면 모든 백업을 복구해 `ROLLED_BACK`으로 기록한다. Process가 Commit 도중 종료돼 `PREPARED`가 남으면 다음 Run 시작 시 먼저 복구한다. 복구 경로는 Canonical Project와 해당 Transaction의 백업 디렉터리 내부로 제한한다.

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

운영 파일은 Project 결과물이 아니므로 Git에서 제외한다.

## 검증 범위

`tests/runtime/`은 Fake Provider 전체 Gate E2E, 정제 Reference만 Provider로 전달되는 E2E, 권한 밖 출력 시 Canonical 불변성, Retry 소진 시 `BLOCKED`, Format Retry, Human 승인·재개, Active·Stale Lock, Input Drift, Transaction Rollback·Crash Recovery·경로 격리, EXAMPLES·Raw Reference·Tool 차단, In-process와 Sidecar Conformance를 검증한다. CI는 Python 3.11과 3.14에서 기존 Validator 회귀 테스트와 함께 실행한다.

# v1.3.2 스키마와 Artifact 계약

## 독립 Version 경계

| 계층 | 식별자 | 구조 Version | 책임 |
|---|---|---|---|
| Compatibility Contract | `contract_family` | `contract_version` | Required/Optional Capability 이름과 호환 범위 |
| Channel DNA | `channel_id` | `schema_version` | Capability별 정책 값과 내부 구조 |
| Story DNA | `project_id` | `schema_version` | Episode 구조와 Source Mode |
| Agent Manifest | Agent 이름 | `schema_version` | 읽기·쓰기·선행 Agent·Gate |
| Dependency Graph | Artifact 이름 | `schema_version` | 경로·의존성·Owner |
| Project State | `project_id` | `schema_version` | Gate와 Artifact Hash/상태 |
| Story Library | `project_id` | `schema_version` | Production Ready Fingerprint History |
| Runtime Task Catalog | Task ID | `schema_version` | 실제 호출의 최소 읽기·쓰기·Gate·Retry 권한 |
| Provider Interface | `provider_id` | `interface_version` | SDK 비종속 Capability와 Request/Response Wire 경계 |
| Runtime Run/Event | `run_id` | `schema_version` | 재개 가능한 상태와 Append-only 감사 기록 |
| Gate Transaction | `transaction_id` | `schema_version` | Codex Task의 Gate·권한·Workspace·Hash Snapshot |
| Process Trace | `trace_id` | `schema_version` | Gate별 Task·Agent·변경·검증·Commit 증거 |

Required Capability 이름은 Contract만 소유한다. `channel_dna.schema.json`은 `capabilities` 객체에 Required 목록을 중복하지 않고 개별 Capability 형상만 검증한다.

## 주요 Schema

| 파일 | 검증 대상 |
|---|---|
| `compatibility_contract.schema.json` | Channel 요구 Interface |
| `project_manifest.schema.json` | Project 식별, Standard, Channel, Source Mode |
| `production_config.schema.json` | 승인 정책, Genre/Tone, Runtime, USER_CASE 입력 상태 |
| `channel_dna.schema.json` | Channel Identity와 Capability 구조 |
| `story_dna.schema.json` | Source Mode와 Full Story DNA v1.3 |
| `panel_cast.schema.json` | 외부 Panelist Persona, 허용 기능과 공개 정보 경계 |
| `reaction_segments.schema.json` | Panel 화자, 추리 기능, 근거, 가설 변화와 시간 |
| `presentation_plan.schema.json` | Presentation Contract v2 Segment Timeline |
| `reference_policy.schema.json` | 허용 Style과 금지 Story Content |
| `reference_profile.schema.json` | Project별 정제 Reference Profile |
| `fact_evidence.schema.json` | Fact/Inference/Dramatization과 Source/Claim 계약 |
| `variation_catalog.schema.json` | 다축 후보 선택 Catalog |
| `variation_candidates.schema.json` | 생성·승인 후보 출력 |
| `story_fingerprint.schema.json` | Story/Beat/Causal Fingerprint |
| `causal_graph.schema.json` | Mystery 인과 Node/Edge와 Causal Fingerprint |
| `novelty_thresholds.schema.json` | 최근/전체 유사도와 Weight |
| `novelty_precheck.schema.json` | 승인 Variation의 사전 History 비교 |
| `agent_manifest.schema.json` | 10개 Agent 실행 계약 |
| `dependency_graph.schema.json` | Artifact DAG |
| `project_state.schema.json` | 상태와 Hash 기반 무효화 |
| `gate_transaction.schema.json` | Codex Gate Task 권한과 실행 상태 |
| `process_trace.schema.json` | Gate별 Process Conformance 증거 |
| `editorial_review.schema.json` | 최종 방송·서사·제작 적합성 Critic 판정 |
| `validation_report.schema.json` | 14 Gate 통합 결과 |
| `story_library.schema.json` | 등록된 Fingerprint 집합 |
| `runtime_task_catalog.schema.json` | Agent 권한의 부분집합인 실행 Task Catalog |
| `runtime_config.schema.json` | 활성 Route Profile과 계약 파일 경로 |
| `artifact_contracts.schema.json` | 출력별 Media Type, Schema, 크기, Commit 정책 |
| `provider_registry.schema.json` | Adapter, Credential 환경 참조, Data Egress 정책 |
| `provider_descriptor.schema.json` | Provider Capability와 Token Limit |
| `llm_request.schema.json` | Provider 독립 Prompt·출력·도구·감사 요청 |
| `llm_response.schema.json` | Provider 독립 상태·출력·사용량 응답 |
| `agent_result.schema.json` | Task Identity와 Artifact 후보 Envelope |
| `runtime_run.schema.json` | Run·Task 상태, 시도, 입력·Prompt Hash |
| `runtime_event.schema.json` | Append-only 운영 Event |
| `approval.schema.json` | Actor·Reason·입력 Hash 결합 승인 |

## 의미 규칙

JSON Schema가 구조를 검증하고 Validator가 다음 교차 규칙을 검증한다.

- Reaction Ratio `min <= max`와 실제 Segment Duration 기반 비율
- Panel Cast/Reaction의 화자·기능·근거·공개 정보·가설 변화 정합성
- Drama/Narration/Panel Layer와 Final Broadcast Master Marker 일치
- Viewer Fact 공개, Audience Belief, 절대시간과 Actual Timeline 정합성
- Culprit Structure별 `causal_truth` 또는 `motive_class`
- Source Mode와 Reference Profile 일치
- USER_CASE의 LOCKED/FLEXIBLE/UNKNOWN 상태와 Story DNA 일치
- 승인 Variation과 Story DNA Override 일치
- Story Fingerprint의 현재성
- Causal Graph DAG와 Root-to-Resolution 경로
- Timeline, Knowledge, Clue, Runtime, ID 참조
- Reference Lexical/14개 Story Element Category Collision
- Channel Genre/Tone/Presentation/Reaction 일치
- Artifact, Contract, Process, Editorial 조건을 모두 충족한 Production Ready에서만 Story Library 등록
- Runtime Task 권한은 Agent Manifest보다 넓을 수 없음
- Provider 출력 Identity와 Task writes가 정확히 일치해야 함
- Raw Reference, EXAMPLES, 비허용 Data Class의 Provider Egress 금지
- Gate Commit 직전 Canonical Input Hash 불변성과 단일 Writer Lock
- Current Gate보다 뒤의 Artifact 수정과 Task writes 밖 변경 차단
- Gate별 PASS Process Trace 완전성과 Human Editorial 승인 분리

## Artifact 유효성

각 Artifact는 `MISSING`, `DIRTY`, `INVALID`, `CLEAN` 중 하나다. 파일이 존재한다는 사실만으로 `CLEAN`이 되지 않는다. 검증된 현재 Hash와 일치해야 하며 상위 Artifact가 바뀌면 Dependency Graph를 따라 하위 Artifact가 `DIRTY`가 된다.

Project State 1.2.0은 Artifact 상태와 별도로 `artifact_status`, `contract_status`, `process_status`, `editorial_status`, `process_start_gate`, `process_revision`을 유지한다. `validate`와 `audit`는 이 값을 바꾸지 않으며 `rebuild-state --force`도 존재하지 않는 Trace나 Human Approval을 합성하지 않는다.

Presentation Schema 1.x는 2.0.0과 호환되지 않는다. 기존 Project는 `PRESENTATION_MIGRATION_REQUIRED`로 전환하며 GATE-05 이후 Artifact를 재생성하기 전에는 Production Ready로 복귀할 수 없다.

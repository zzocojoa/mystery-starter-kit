# v1.3 스키마와 Artifact 계약

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

Required Capability 이름은 Contract만 소유한다. `channel_dna.schema.json`은 `capabilities` 객체에 Required 목록을 중복하지 않고 개별 Capability 형상만 검증한다.

## 주요 Schema

| 파일 | 검증 대상 |
|---|---|
| `compatibility_contract.schema.json` | Channel 요구 Interface |
| `project_manifest.schema.json` | Project 식별, Standard, Channel, Source Mode |
| `production_config.schema.json` | 승인 정책, Genre/Tone, Runtime, USER_CASE 입력 상태 |
| `channel_dna.schema.json` | Channel Identity와 Capability 구조 |
| `story_dna.schema.json` | Source Mode와 Full Story DNA v1.3 |
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
| `validation_report.schema.json` | 14 Gate 통합 결과 |
| `story_library.schema.json` | 등록된 Fingerprint 집합 |

## 의미 규칙

JSON Schema가 구조를 검증하고 Validator가 다음 교차 규칙을 검증한다.

- Reaction Ratio `min <= max`
- Culprit Structure별 `causal_truth` 또는 `motive_class`
- Source Mode와 Reference Profile 일치
- USER_CASE의 LOCKED/FLEXIBLE/UNKNOWN 상태와 Story DNA 일치
- 승인 Variation과 Story DNA Override 일치
- Story Fingerprint의 현재성
- Causal Graph DAG와 Root-to-Resolution 경로
- Timeline, Knowledge, Clue, Runtime, ID 참조
- Reference Lexical/14개 Story Element Category Collision
- Channel Genre/Tone/Presentation/Reaction 일치
- Production Ready에서만 Story Library 등록

## Artifact 유효성

각 Artifact는 `MISSING`, `DIRTY`, `INVALID`, `CLEAN` 중 하나다. 파일이 존재한다는 사실만으로 `CLEAN`이 되지 않는다. 검증된 현재 Hash와 일치해야 하며 상위 Artifact가 바뀌면 Dependency Graph를 따라 하위 Artifact가 `DIRTY`가 된다.

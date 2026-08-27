# 단편 미스터리 반복 제작 표준 제작체계 v1.3

## 1. 목적과 완료 정의

이 표준은 같은 채널의 정체성을 유지하면서 사건·인물·인과·반전의 복제를 막는 반복 제작 체계다. 결과물은 아이디어 문서가 아니라 `00_PROJECT`부터 `09_PRODUCTION`까지 추적 가능한 Artifact, 자동 검증 보고서, Production Ready 상태를 갖는 실행 단위다.

기능은 다음 다섯 증거가 모두 있을 때만 구현 완료로 본다.

1. 책임과 실패 조건을 설명하는 문서
2. 구조를 고정하는 JSON Schema 또는 명시적 Artifact Contract
3. 오류 Code와 Context를 반환하는 Validator
4. 정상·실패·경계 조건을 검증하는 Test
5. Pull Request에서 Test·Type·Lint·Build·Dependency Audit을 수행하는 CI Gate

## 2. 계층과 소유권

```text
Production Standard
        ↓ Compatibility Contract
Channel DNA
        ↓ Constraint
Story DNA
        ↓ Artifact Dependency Graph
Project / Script / Production Package
```

- Production Standard, Compatibility Contract, Channel DNA, Story DNA는 독립 Version 수명주기를 가진다.
- Standard와 Channel은 `compatibility_contract.json`을 통해서만 결합한다.
- Required Capability의 이름 소유권은 Contract에만 있다. Channel Schema는 Capability 내부 구조만 소유한다.
- Channel의 명시값은 동일 이름의 Optional Standard Default보다 우선한다.
- Story와 Project는 Standard 또는 Channel 원본을 수정하지 않는다.
- `schema_version`은 Interface 호환성, `content_version`은 정책 내용 변경을 뜻한다.

## 3. Story Source Mode와 Reference Firewall

모든 Story는 다음 Source Mode 중 하나를 선언한다.

| Mode | 의미 | 추가 조건 |
|---|---|---|
| `ORIGINAL` | 독립 창작 | Reference Profile과 원문을 사용하지 않음 |
| `USER_CASE` | 사용자가 일부 설정을 제공 | 각 입력을 `LOCKED`, `FLEXIBLE`, `UNKNOWN`으로 선언 |
| `REFERENCE_INSPIRED` | 표현 방식만 참고 | 정제된 Reference Profile과 Collision QA 필수 |
| `TRUE_STORY` | 검증 가능한 실제 사건 | Sources와 Claim-Evidence 필수 |
| `INSPIRED_BY_TRUE_EVENTS` | 사실에서 출발한 각색 | Sources와 Claim-Evidence, Fact/Inference/Dramatization 분리 필수 |

Reference 입력은 Production Agent Context에 직접 들어가지 않는다. Reference Auditor가 정책상 허용된 `PRESENTATION_MODE`, `PACING`, `TONE`, `SUSPENSE_HANDLING` 같은 Style Feature 이름만 남기고 다음 Story Content를 차단한다.

`USER_CASE`의 Constraint는 Production Config가 단일 원천이다. `LOCKED` 값은 모든 Variation과 Story DNA에서 유지하고, `FLEXIBLE` 값은 변경할 수 있으며, `UNKNOWN` 값은 Variation 단계에서 새로 제안한다.

- Characters와 Character Relationships
- Locations와 Incidents
- Culprit, Victim, Motive, Method
- Clues, Twists, Beat Sequence
- 고유 Dialogue, Number, Object

최종 Script는 6단어 이상 동일 문구와 2개 이상 금지 Story Element Category 충돌을 검사한다. Project Artifact에서 정책의 14개 금지 Category를 모두 추출하며 빈 Category도 명시적으로 유지한다. Collision Report에는 원문 대신 비가역 Phrase Hash만 기록한다. 모든 Production Agent의 `may_read_examples`는 `false`이며 Context Builder는 `EXAMPLES/` 경로를 거부한다.

## 4. Story DNA v1.3

Story DNA는 다음 축을 반드시 정의한다.

- Mystery Type: `WHO`, `WHOSE`, `WHY`, `HOW`, `WHEN`, `WHERE`, `WHETHER`, `WHAT`
- Architecture와 Protagonist Role
- Perspective, Narrator Reliability, Timeline Style
- Incident, Setting, Setting Logic
- Culprit Structure, Primary/Secondary Twist
- Information Mechanism, Clue Mechanism
- Emotional, Relationship, Pressure, Dramatic Engine
- Thematic Question과 Audience Experience
- Reveal Mode와 Ending Type

확장 Protagonist Role에는 `SURVIVOR`, `VICTIM_FAMILY`, `CULPRIT_FAMILY`, `REPORTER`, `EMPLOYEE`, `MANAGER`, `NEIGHBOR`, `FRIEND`, `PARTNER`, `EX_PARTNER`, `AUTHORITY`, `CULPRIT`, `UNWITTING_PARTICIPANT`가 포함된다. Perspective는 `FOUND_FOOTAGE`, `DOCUMENTARY`, `INTERVIEW_BASED`, `SCREENLIFE`, Timeline은 `PARALLEL`, `REAL_TIME`, `LOOP`, Culprit Structure는 `DUAL`, `VICTIM_SELF_ENGINEERED`, `SYSTEMIC_CAUSE`, `ACCIDENTAL`을 포함한다.

`NO_CULPRIT`, `SYSTEMIC_CAUSE`, `ACCIDENTAL`은 Motive 대신 `causal_truth`가 필수다. 그 밖의 Culprit Structure는 `motive_class`가 필수다.

## 5. Variation Engine과 승인

Variation Designer는 Story 문장을 쓰기 전에 최소 5개 구조 후보를 생성한다. 후보는 Mystery, Architecture, Protagonist, Perspective, Timeline, Culprit, Twist, Relationship, Pressure, Dramatic Dimension을 함께 바꾼다. 같은 Seed와 Catalog는 같은 후보를 생성하며 후보 Signature는 서로 달라야 한다.

승인 후보는 정확히 하나다. Story DNA가 승인 후보와 다른 Dimension을 사용하려면 `variation_overrides`에 해당 Dimension을 명시하고 `override_reason`을 기록해야 한다. 선언되지 않은 변경은 `UNDECLARED_VARIATION_OVERRIDE`로 차단한다.

승인 직후 Novelty Precheck가 Story History의 최근 5개·10개·전체 구조와 비교한다. Precheck Report는 후보 Selection과 승인 ID의 Hash를 보존하며 후보가 바뀌면 오래된 Report로 차단된다.

## 6. Agent Contract Pipeline

| Agent | 핵심 책임 | 주요 출력 |
|---|---|---|
| `orchestrator` | Gate 순서와 상태 전이, 최종 인계 | Production Config, Validation, Production Package |
| `variation_designer` | 다축 후보 생성 | Variation Candidates |
| `story_architect` | Story DNA, Case, Beat, Retention | Story/Case/Story Structure Artifact |
| `character_designer` | 인물·관계·지식 경계 | Characters, Relationships, Knowledge Matrix |
| `mystery_designer` | 실제/시청 Timeline과 추리 구조 | Timelines, Clues, Hypotheses, Causal Graph |
| `scene_designer` | Beat를 촬영 가능한 Scene으로 변환 | Scene Cards, Presentation Plan |
| `script_writer` | Scene과 지식 경계를 지키는 대본 | Draft, Final Script |
| `continuity_critic` | 시간·공간·지식·단서·채널 검사 | Continuity, Channel Report |
| `novelty_auditor` | 구조/Beat/Causal 중복 검사 | Story Fingerprint, Novelty Report |
| `reference_auditor` | Reference 정제와 사실/충돌 검사 | Reference, Evidence, Collision Report |

`AGENTS/manifest.json`이 Agent별 최대 읽기·쓰기 Artifact, 선행 Agent, Gate, Prompt를 소유한다. `RUNTIME/contracts/runtime_tasks.json`의 실제 Task 권한은 이 최대 권한의 부분집합이어야 하며 Dependency Graph의 Artifact Owner를 바꿀 수 없다. Agent는 선언되지 않은 Project Artifact와 `EXAMPLES/`를 읽을 수 없다.

LLM Agent Runtime v1.0은 Provider SDK에 종속되지 않는 Request/Response Interface를 사용한다. Model Profile은 필요한 Capability와 Route 순서만 정의하고 Provider 이름·Credential 환경 변수 참조·Data Egress 정책은 별도 Registry가 소유한다. In-process Plugin과 HTTP Sidecar가 같은 Descriptor·Request·Response Schema를 구현하므로 Provider 교체는 Runtime Core 변경 없이 구성으로 수행한다.

LLM은 Canonical Project 파일, Project State, Gate 상태를 직접 변경할 수 없다. 응답은 Agent Result Envelope, Run·Task·Agent·Attempt Identity, Task writes 소유권, Artifact별 JSON Schema·Media Type·크기 제한을 통과해야 한다. Gate의 여러 Artifact는 격리된 Staging Overlay에서 함께 검증한 후 Write-ahead Transaction으로 전부 Commit하거나 전부 복구한다.

Run과 Task 상태, 입력·Prompt·Schema Hash, Provider·Model·Token 사용량, Event, Attempt Request/Response, Artifact Provenance를 `.runtime/`에 기록한다. 재개 시 Canonical Project의 다음 Gate부터 실행하며, Commit 직전 입력 Hash가 바뀌면 `INPUT_HASH_CHANGED`로 거부한다. Transport 오류만 제한적으로 Route 전환할 수 있고 Provider Refusal, Data Policy, 권한, Schema 오류에는 임의 Fallback을 사용하지 않는다.

## 7. Project Scaffold와 Artifact Chain

```text
00_PROJECT   설정, 호환성, 후보, Story DNA, Fingerprint, State, Change Log
01_CASE      Case Input, Facts, Sources, Claim-Evidence
02_CHARACTER Characters, Relationships, Knowledge Matrix
03_TIMELINE  Actual, Viewer, Audience Belief Timeline
04_MYSTERY   Clue Matrix, Hypothesis Ledger, Causal Graph
05_STORY     Beat Sheet, Retention Plan
06_SCENE     Scene Cards, Presentation Plan
07_SCRIPT    Draft, Final Script
08_QA        Continuity, Novelty, Reference, Channel, 통합 Validation
09_PRODUCTION Shooting, Narration, Subtitle, Edit Script
```

핵심 흐름은 다음과 같다.

```text
Compatibility → Variations/Approval → Story DNA/Fingerprint
→ Case/Facts → Characters/Relationships/Knowledge
→ Actual/Viewer/Audience Timeline → Clues/Hypotheses/Causal Graph
→ Beats/Retention → Scenes/Presentation → Draft/Final Script
→ Continuity/Causal/Novelty/Reference/Channel QA
→ Shooting/Narration/Subtitle/Edit Package → Story Library
```

## 8. GATE-00부터 GATE-13

| Gate | 통과 조건 | 도착 상태 |
|---|---|---|
| `GATE-00` | Compatibility PASS, Production Config | `COMPATIBILITY_VALIDATED` |
| `GATE-01` | 최소 후보 수, 단일 승인, 최신 Novelty Precheck | `VARIATION_APPROVED` |
| `GATE-02` | Story DNA와 승인 Variation/Override 정합성 | `STORY_DESIGNED` |
| `GATE-03` | Case, Facts, Source Mode별 Evidence | `CASE_DEFINED` |
| `GATE-04` | Character, Relationship, Knowledge | `CHARACTERS_DESIGNED` |
| `GATE-05` | 3개 Timeline, Clue, Hypothesis, Causal DAG | `MYSTERY_DESIGNED` |
| `GATE-06` | Beat와 Retention | `STORY_STRUCTURED` |
| `GATE-07` | Scene과 Presentation | `SCENES_DESIGNED` |
| `GATE-08` | Draft와 Final Script | `SCRIPT_WRITTEN` |
| `GATE-09` | Continuity QA | `SCRIPT_WRITTEN` |
| `GATE-10` | 최종 Fingerprint 현재성과 Novelty QA | `SCRIPT_WRITTEN` |
| `GATE-11` | Reference QA | `SCRIPT_WRITTEN` |
| `GATE-12` | Channel QA와 통합 Validation | `QA_PASSED` |
| `GATE-13` | 네 가지 Production Artifact | `PRODUCTION_READY` |

Gate는 순서를 건너뛸 수 없다. 필수 Artifact는 모두 `CLEAN`이어야 하며 실패하면 마지막 통과 Gate를 유지한 채 `BLOCKED`가 된다.

## 9. QA 규칙

### Continuity와 Causal

- 같은 Character가 겹치는 시간에 다른 Location에 있을 수 없다.
- Character는 Knowledge Matrix의 학습 Scene 이전에 Fact를 사용할 수 없다.
- Core Clue와 Red Herring은 도입 후 회수되어야 한다.
- Character, Fact, Clue, Beat, Scene 참조 ID는 실제로 존재해야 한다.
- Scene 예상 시간 합은 Target Runtime 허용 범위 안이어야 한다.
- Causal Graph는 존재하는 Node만 참조하는 DAG여야 한다.
- `ROOT_CAUSE`에서 `RESOLUTION`까지 도달 가능한 경로가 있어야 한다.

### Novelty

Story Fingerprint는 Story Dimension, Beat Signature, 다섯 Causal Dimension으로 구성한다.

1. Root Cause
2. Mechanism
3. Concealment
4. Discovery Path
5. Resolution

Category는 Exact Match, 배열은 Jaccard, Beat는 Sequence Similarity, Causal은 다섯 Dimension의 부분 구조 일치율로 계산한다. 이 Component를 가중 합산하며 최근 5개는 60%, 최근 10개는 65%, 전체는 70%를 초과할 수 없다. 다섯 Causal Dimension이 모두 같으면 가중 유사도와 무관하게 `CAUSAL_HARD_COLLISION`이다. 저장 Fingerprint가 현재 Story/Beat/Causal Artifact에서 재생성되지 않으면 오래된 것으로 차단한다.

### Channel Consistency

Genre, 금지 Tone, 필수 Presentation Mode, Reaction Ratio를 Channel DNA와 비교한다. Reaction 목표 `min`은 `max`보다 클 수 없고 실제 비율은 해당 범위 안이어야 한다.

### Fact Integrity

`TRUE_STORY`와 `INSPIRED_BY_TRUE_EVENTS`의 모든 `FACT`는 존재하는 Source와 Claim-Evidence에 연결한다. `INFERENCE`는 근거 Fact를 참조하고 `DRAMATIZATION`은 검증된 Fact로 표시할 수 없다. 깨진 Source/Fact 참조나 Evidence가 없는 Fact는 Case Gate를 차단한다.

## 10. Dependency Invalidation과 이력

`STANDARD/dependency_graph.json`은 각 Artifact의 경로, 선행 Artifact, Owner Agent를 정의한다. 상위 Artifact Hash가 바뀌면 모든 Transitive Dependent를 `DIRTY`로 만들고 `invalidated_by`를 기록한다. 입력 객체는 수정하지 않고 새 Project State를 반환한다.

`00_PROJECT/change_log.jsonl`은 초기화, Variation 생성/승인, 전체 검증, Story Library 등록을 시간과 함께 기록한다. Production Ready Fingerprint만 Story Library에 등록할 수 있으며 동일 Project의 중복 등록은 실패한다.

## 11. 승인 정책

기본값 `AUTO_CONTINUE`는 Gate PASS 뒤의 단순 단계 전환에 추가 승인을 요구하지 않는다. 다음 경우에는 Human Review가 필요하다.

- Novelty 실패를 예외 승인하려는 경우
- Fact와 Dramatization이 충돌하는 경우
- 검증 불가능한 실화 주장을 사실로 사용하려는 경우
- 승인 Variation과 다른 구조를 Override하면서 제작 방향이 달라지는 경우

Runtime의 Human Approval은 Run ID, Task ID, 현재 입력 Artifact Hash에 결합한다. 입력이 바뀐 승인은 자동으로 무효이며 Actor와 비어 있지 않은 Reason이 없으면 기록할 수 없다.

## 12. 실행 인터페이스

```bash
mystery-kit init PRJ-002
mystery-kit compat PROJECTS/PRJ-002
mystery-kit variations PROJECTS/PRJ-002 --seed "공장 교대 중 실종" --count 5
mystery-kit approve PROJECTS/PRJ-002 VAR-03
mystery-kit precheck PROJECTS/PRJ-002
mystery-kit reference-profile PROJECTS/PRJ-002 /secure/reference-source.json
mystery-kit validate PROJECTS/PRJ-002
mystery-kit register PROJECTS/PRJ-002

mystery-runtime doctor
mystery-runtime plan PROJECTS/PRJ-002
mystery-runtime run PROJECTS/PRJ-002 --from GATE-00 --to GATE-13
mystery-runtime status PROJECTS/PRJ-002
mystery-runtime approve RUN-... variation.generate --actor reviewer --reason "검토 완료"
mystery-runtime resume RUN-...
mystery-runtime cancel RUN-...
mystery-runtime providers
```

`mystery-kit` 종료 코드는 `PASS=0`, 검증 실패 `=1`, 입력·구성 오류 `=2`다. `mystery-runtime`은 성공 `0`, 구조화 Runtime 오류 `2`를 사용한다. `register`는 `PRODUCTION_READY`가 아닌 Project를 거부한다.

## 13. Version 정책

- 동일 Major Schema 안의 추가 필드는 소비자가 명시적으로 허용한 경계에서만 Forward Compatible하다.
- Contract의 Version Range는 `min_inclusive <= schema_version < max_exclusive`다.
- `content_version`은 Compatibility 실패 사유가 아니다.
- Major Schema 변경은 Migration 또는 Adapter 설계를 동반한다.
- Standard, Schema, Agent Contract, Validator, Test가 바뀌면 구현 매트릭스와 문서를 같은 Pull Request에서 갱신한다.

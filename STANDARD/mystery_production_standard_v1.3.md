# 단편 미스터리 반복 제작 표준 제작체계 v1.3.3

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
- Project는 `production_config.channel_content_version`으로 생성 당시 Channel 정책을 고정한다. `channel_manifest.json`은 활성 버전과 사용 가능한 버전별 DNA 경로·정규 JSON SHA-256을 등록하며 Runtime은 활성 버전이 아니라 Project 핀을 해석한다.
- Compatibility Report는 Channel ID, Schema Version, Content Version, DNA SHA-256을 보존한다. 등록되지 않은 핀, 실제 DNA의 Content Version 불일치, Manifest Hash 불일치는 각각 `CHANNEL_CONTENT_VERSION_NOT_FOUND`, `CHANNEL_CONTENT_VERSION_MISMATCH`, `CHANNEL_DNA_HASH_MISMATCH`로 차단한다.

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

Channel Content Version 2.0 이상은 활성 Capability에 따라 `trusted_domain`, `safe_domain_expectation`, 초기 경고 신호, 경계 침식 단계, 통제 수단, 피해자 이탈 장벽, 피해 메커니즘, 책임 주체, 피해자 행위 주체성 결과, 위험 신호 회수, Audience-facing 출처 Label, 임상 용어 분류와 전문가 Debrief 계획을 요구한다. 이 필드는 1.1.0 Project에서는 선택 사항이며 v2 규칙을 소급 적용하지 않는다.

## 5. Variation Engine과 승인

Variation Designer는 Story 문장을 쓰기 전에 최소 5개 구조 후보를 생성한다. 후보는 Mystery, Architecture, Protagonist, Perspective, Timeline, Culprit, Twist, Relationship, Pressure, Dramatic Dimension을 함께 바꾼다. 같은 Seed와 Catalog는 같은 후보를 생성하며 후보 Signature는 서로 달라야 한다.

승인 후보는 정확히 하나다. Story DNA가 승인 후보와 다른 Dimension을 사용하려면 `variation_overrides`에 해당 Dimension을 명시하고 `override_reason`을 기록해야 한다. 선언되지 않은 변경은 `UNDECLARED_VARIATION_OVERRIDE`로 차단한다.

Novelty Precheck는 승인 전에 모든 후보를 Story History의 최근 5개·10개·전체 구조와 비교한다. Precheck Report는 승인 상태를 제외한 전체 Candidate 구조 Hash를 보존하며 후보가 바뀌면 오래된 Report로 차단된다.

`candidate_evaluation.json`은 Novelty Precheck 후 모든 후보의 Hard Filter, Crime Threat, Psychological Immersion, Trust Betrayal, Victim Integrity, Character, Twist, Novelty, Production 점수·근거·입력 Hash를 보존한다. Runtime의 `variation.evaluate` Task 또는 같은 계약을 수행하는 Codex Gate Task가 이 Artifact를 작성한 뒤에만 승인할 수 있다. Validator가 가중치 합계와 Weighted Total을 재계산한다. 승인 후보는 Hard Filter와 Novelty를 통과한 최고점 추천 후보여야 하며, 다른 적격 후보를 승인하려면 현재 평가에 결합된 Human Override Actor와 Reason이 필요하다. 평가 없이 `approve`를 호출하면 `CANDIDATE_EVALUATION_REQUIRED`로 실패한다.

Channel Content 2.1의 Variation Engine과 Catalog는 Incident Type, 실제 Crime Action, 관계, 피해, 동기, 주인공 목표·위험, 묘사 방식과 Reveal 구조를 먼저 생성하고 그 인과 사건에 Story Variation을 결합한다. Candidate Evaluation은 Crime Event Centrality 25, Character Risk/Conflict 25, Scene Realizability 20, Reveal Persuasion 15, Production 15의 잠재력만 평가한다. Novelty는 점수로 상쇄할 수 없는 Hard Constraint이며 Candidate 평가는 Final Script의 의미 실현 판정을 대신하지 않는다. 비교 대상이 0건이면 PASS를 유사도 증거처럼 표현하지 않고 `NO_COMPARISON_DATA`를 기록한다.

## 6. Agent Contract Pipeline

| Agent | 핵심 책임 | 주요 출력 |
|---|---|---|
| `orchestrator` | Gate 순서와 상태 전이, 최종 인계 | Production Config, Validation, Production Package |
| `variation_designer` | 다축 후보 생성과 평가 | Variation Candidates, Candidate Evaluation |
| `story_architect` | Story DNA, Case, Beat, Retention | Story/Case/Story Structure Artifact |
| `character_designer` | 인물·관계·지식 경계 | Characters, Relationships, Knowledge Matrix |
| `mystery_designer` | 실제/시청 Timeline과 추리 구조 | Timelines, Clues, Hypotheses, Causal Graph |
| `scene_designer` | Scene과 외부 Panel·Expert 분석 흐름을 설계 | Scene Cards, Panel Cast, Reaction Segments, Expert Segments, Presentation Plan |
| `script_writer` | 기본 세 Layer와 조건부 Expert Layer를 Broadcast Master로 통합 | Drama, Narration, Panel Reaction, Expert Analysis, Draft, Final Script |
| `continuity_critic` | 시간·공간·지식·단서·채널·최종 편집 검사 | Continuity, Channel, Editorial Review |
| `novelty_auditor` | 구조/Beat/Causal 중복 검사 | Story Fingerprint, Novelty Report |
| `reference_auditor` | Reference 정제와 사실/충돌 검사 | Reference, Evidence, Collision Report |

`AGENTS/manifest.json`이 Agent별 최대 읽기·쓰기 Artifact, 선행 Agent, Gate, Prompt를 소유한다. `RUNTIME/contracts/runtime_tasks.json`의 실제 Task 권한은 이 최대 권한의 부분집합이어야 하며 Dependency Graph의 Artifact Owner를 바꿀 수 없다. Agent는 선언되지 않은 Project Artifact와 `EXAMPLES/`를 읽을 수 없다.

LLM Agent Runtime v1.0은 Provider SDK에 종속되지 않는 Request/Response Interface를 사용한다. Model Profile은 필요한 Capability와 Route 순서만 정의하고 Provider 이름·Credential 환경 변수 참조·Data Egress 정책은 별도 Registry가 소유한다. In-process Plugin과 HTTP Sidecar가 같은 Descriptor·Request·Response Schema를 구현하므로 Provider 교체는 Runtime Core 변경 없이 구성으로 수행한다.

LLM은 Canonical Project 파일, Project State, Gate 상태를 직접 변경할 수 없다. 응답은 Agent Result Envelope, Run·Task·Agent·Attempt Identity, Task writes 소유권, Artifact별 JSON Schema·Media Type·크기 제한을 통과해야 한다. Gate의 여러 Artifact는 격리된 Staging Overlay에서 함께 검증한 후 Write-ahead Transaction으로 전부 Commit하거나 전부 복구한다.

Run과 Task 상태, 입력·Prompt·Schema Hash, Provider·Model·Token 사용량, Event, Attempt Request/Response, Artifact Provenance를 `.runtime/`에 기록한다. 재개 시 Canonical Project의 다음 Gate부터 실행하며, Commit 직전 입력 Hash가 바뀌면 `INPUT_HASH_CHANGED`로 거부한다. Transport 오류만 제한적으로 Route 전환할 수 있고 Provider Refusal, Data Policy, 권한, Schema 오류에는 임의 Fallback을 사용하지 않는다.

## 7. Project Scaffold와 Artifact Chain

```text
00_PROJECT   설정, 호환성, 후보 평가, Story DNA, Fingerprint, State, Change Log, Process Trace
01_CASE      Case Input, Facts, Sources, Claim-Evidence, Crime Psychology, Source Disclosure, Clinical Labels
02_CHARACTER Characters, Relationships, Knowledge Matrix
03_TIMELINE  Actual, Viewer, Audience Belief Timeline
04_MYSTERY   Clue Matrix, Hypothesis Ledger, Causal Graph
05_STORY     Beat Sheet, Retention Plan
06_SCENE     Scene Cards, Panel Cast, Reaction Segments, Expert Segments, Presentation Plan
07_SCRIPT    Drama, Narration, Panel Reaction, Expert Analysis Layer, Draft, Final Script
08_QA        Continuity, Novelty, Reference, Channel, 통합 Validation, Editorial Review
09_PRODUCTION Shooting, Narration, Panel Reaction Cue, Expert Analysis Cue, Subtitle, Edit Script
```

핵심 흐름은 다음과 같다.

```text
Compatibility → Variations → All-candidate Novelty Precheck → Evaluation → Approval → Story DNA/Fingerprint
→ Case/Facts → Characters/Relationships/Knowledge
→ Actual/Viewer/Audience Timeline → Clues/Hypotheses/Causal Graph
→ Beats/Retention → Scenes/Panel/Presentation → 세 Script Layer → Broadcast Master
→ Continuity/Causal/Novelty/Reference/Channel QA
→ Shooting/Narration/Subtitle/Edit Package → Editorial Review/Approval → Story Library
```

## 8. GATE-00부터 GATE-13

| Gate | 통과 조건 | 도착 상태 |
|---|---|---|
| `GATE-00` | Project Channel Content Version·DNA Hash가 고정된 Compatibility PASS, Production Config | `COMPATIBILITY_VALIDATED` |
| `GATE-01` | 최소 후보 수, 전체 Candidate 평가 근거, 단일 승인, 최신 Novelty Precheck | `VARIATION_APPROVED` |
| `GATE-02` | Story DNA와 승인 Variation/Override 정합성 | `STORY_DESIGNED` |
| `GATE-03` | Case, Facts, Source Mode별 Evidence와 v2 Crime/Source/Clinical Artifact | `CASE_DEFINED` |
| `GATE-04` | Character, Relationship, Knowledge | `CHARACTERS_DESIGNED` |
| `GATE-05` | 3개 Timeline, Clue, Hypothesis, Causal DAG | `MYSTERY_DESIGNED` |
| `GATE-06` | Beat와 Retention | `STORY_STRUCTURED` |
| `GATE-07` | Scene, 사건 행동·피해 인과, Panel Cast, Reaction/Expert Segment와 Presentation v2 | `SCENES_DESIGNED` |
| `GATE-08` | 기본 세 Layer, 조건부 Expert Layer, Draft와 Marker 기반 Broadcast Master, 사건 Script 실현 | `SCRIPT_WRITTEN` |
| `GATE-09` | Continuity QA와 재계산 가능한 Script Realization Report | `SCRIPT_WRITTEN` |
| `GATE-10` | 최종 Fingerprint 현재성과 Novelty QA | `SCRIPT_WRITTEN` |
| `GATE-11` | Reference QA | `SCRIPT_WRITTEN` |
| `GATE-12` | Channel QA, 사건·Reveal Evidence와 통합 Validation | `QA_PASSED` |
| `GATE-13` | Production Artifact와 사건 의미 Evidence를 포함한 Editorial Review PASS | `EDITORIAL_REVIEW_REQUIRED` |

Gate는 순서를 건너뛸 수 없다. 필수 Artifact는 모두 `CLEAN`이어야 하며 실패하면 마지막 통과 Gate를 유지한 채 `BLOCKED`가 된다.

Codex App 작업은 Gate마다 `task-open → 격리 Workspace 작성 → task-submit`을 반복한다. Task Record가 Agent, reads, writes, 입력 Hash와 금지 경로를 고정한다. Submit은 현재 Gate 일치, Future Gate 수정, writes와 Owner, 입력 Drift, Schema, 필수 Artifact와 현재 Gate Validator를 검사한다. PASS Bundle만 기존 Write-ahead Transaction으로 Canonical Artifact, Project State, `process_trace.jsonl`에 원자 Commit한다.

`task-open`과 Runtime은 이미 통과한 Canonical Artifact를 Project State의 `content_hash`와 대조한다. 직접 수정, 삭제 또는 State Hash 누락은 `GATE_TRANSACTION_INPUT_DRIFT`로 차단한다. `audit`, Editorial 승인, Production 확정, Story Library 등록도 같은 정본 대조를 통과해야 한다.

Trace가 없는 Gate는 Process Conformance를 충족하지 않는다. `AUTO_CONTINUE`는 현재 Gate PASS 뒤 다음 Gate Task를 추가 확인 없이 열 수 있다는 의미일 뿐 일괄 Artifact 생성이나 사후 State 재구성을 허용하지 않는다.

Project 준비 상태는 다음 독립 조건으로 관리한다.

```text
ARTIFACT_COMPLETE
+ CONTRACT_VALIDATED
+ PROCESS_CONFORMANT
+ EDITORIAL_APPROVED
= PRODUCTION_READY
```

GATE-13의 Critic은 최종 Script와 Production Package를 읽고 방송 형식, 절대시간, 대사 자연스러움, Panel Reaction 기능, Audience Belief, 촬영 가능성, 피해자 존엄을 `editorial_review.json`에 판정한다. Editorial Review v1.2는 Reviewer, 시각, 검토한 Artifact의 Canonical Hash와 `artifact + selector_type + selector_id + excerpt_hash` 근거를 보존한다. Validator는 Selector를 현재 Artifact에서 다시 해석하고 Excerpt Hash를 검증한다. 검토 뒤 입력이 바뀌거나 근거가 사라지면 기존 Review는 무효다. Critic은 Script를 수정하지 않는다. Review PASS 뒤에도 Human Actor와 Reason을 기록한 별도 승인이 필요하다.

Critic Issue는 `task-return`으로 해당 `owner_agent`의 가장 최근 LLM Gate에 반환한다. Canonical 파일과 과거 Trace는 삭제하지 않고, 목표 Gate 이후 Artifact를 `DIRTY`로 바꾸며 `process_revision`을 증가시킨다. 재작업 뒤 Process Conformance에는 현재 Revision에서 목표 Gate부터 새로 쌓인 PASS Trace만 사용한다.

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

Story Fingerprint는 Story Dimension, Beat Signature, 다섯 Causal Dimension과 의미 정규화된 인과 Signature로 구성한다.

1. Root Cause
2. Mechanism
3. Concealment
4. Discovery Path
5. Resolution

Category는 Exact Match, 배열은 Jaccard, Beat는 Sequence Similarity, Causal은 다섯 Dimension의 부분 구조 일치율로 계산한다. 의미 Signature는 인과 Node Role, 정규화 Edge Sequence, Character Causal Chain, Audience Belief Transition을 비교한다. 이 Component를 가중 합산하며 최근 5개는 60%, 최근 10개는 65%, 전체는 70%를 초과할 수 없다. 다섯 Causal Dimension이 모두 같으면 `CAUSAL_HARD_COLLISION`, 의미 인과 유사도가 85% 이상이면 `CAUSAL_SEMANTIC_COLLISION`이다. 저장 Fingerprint가 현재 Story/Beat/Causal Artifact에서 재생성되지 않으면 오래된 것으로 차단한다.

`novelty_index.json`은 GATE-02부터 Project Fingerprint를 `DRAFT`, `EDITORIAL_PENDING`, `PRODUCTION_READY`, `ABANDONED` Lifecycle로 추적한다. GATE-10과 GATE-13, Production Finalize, Owner Return 때 현재 상태를 동기화한다. Novelty 비교는 `ABANDONED`를 제외한 활성 Project를 대상으로 하며, 발행된 Story Library와 Append-only History는 Production Ready 확정 뒤에만 갱신한다.

### Channel Consistency

Genre, 금지 Tone, 필수 Presentation Mode, Reaction Ratio를 Channel DNA와 비교한다. Reaction 목표 `min`은 `max`보다 클 수 없고 실제 비율은 Presentation Segment의 전체 `duration_sec` 대비 `PANEL_REACTION` 합으로 계산해 해당 범위 안이어야 한다. 수동 비율 필드는 신뢰하지 않는다.

Channel Content Version 2.0 이상에서는 활성 Optional Capability에 따라 범죄·약탈적 위협, 안전하다고 믿은 영역의 배신, 경고 신호부터 경계 침식·통제·이탈 장벽까지의 과정, 피해자 행위 주체성, 가해 책임 귀속, 심리 압박과 위험 신호 회수를 검사한다. 기술 퍼즐 우세와 절차물 이탈, 피해자 비난 표현을 차단한다. Content Version 1.1.0 이하에는 이 규칙을 적용하지 않는다.

Channel Content Version 2.1의 `EXPLICIT_CRIME_EVENT_POLICY`는 살인·납치·감금·폭행·스토킹·주거침입·교제폭력·가정폭력 중 하나 이상의 구체 대인범죄를 중심 사건으로 요구한다. `crime_event_contract.json`은 승인 Candidate와 실제 행위, 행위자·피해자, 동기, 피해 결과, 비실행적 방식 요약과 범인·동기·방식·피해 결과 Reveal Target을 결속한다. 살인은 생존·직접 신고·용서·회복 결말을 요구하지 않으며, 납치·감금과 숙박 장소를 일반 파일럿 금지로 두지 않는다. 사건 유형별 서사 기능은 요구하되 고정된 심리 9단계나 선형 순서를 강제하지 않는다.

`scene_cards.json`의 `crime_realization[]`은 Event·Harm·Actor·Victim ID, 실제 행동, 대화·행동 반응, 선택·감정 변화와 결과 변화를 Drama Segment에 연결한다. Final Script는 `[CRIME_EVENT:...]`, `[CRIME_ACTION:...]`, `[HARM:...]`, `[CAUSES:...>...]` Marker로 사건 인과를 보존한다. Scene ID, 범죄 장르 태그 또는 Candidate 점수만으로 사건 실현을 충족할 수 없다.

Continuity Critic 소유의 `script_realization_report.json`은 사건·Reveal·Layer의 실제 Selector와 Excerpt Hash를 `NEEDS_REVIEW` 또는 `MISSING`으로 기록한다. CORE Validator는 입력 Hash와 구조 근거를 다시 계산하지만 의미상 PASS를 선언하지 않는다. GATE-13 Editorial Review는 사건 실현, 주관적 Narration, Panel 추적, Reveal Timing, 단서·증거 정합성을 실제 발췌로 각각 `EVIDENCED` 판정한다.

모든 v2 Story는 Source Mode에 맞는 `VERIFIED_TRUE_CASE`, `INSPIRED_BY_TRUE_EVENTS`, `ORIGINAL_FICTION` 중 하나를 Audience-facing Label로 선언한다. `TRUE_STORY`는 `EXPERT_ANALYSIS` Segment가 필수이며, `INSPIRED_BY_TRUE_EVENTS`는 전문가 분석 또는 명시적 N/A 근거가 필요하고, `ORIGINAL`은 선택 사항이다. 전문가 Claim은 Claim-Evidence와 연결하며 일반 Panel 의견은 Expert Fact로 인정하지 않는다. 통제 임상 용어는 `CONFIRMED_DIAGNOSIS`, `EXPERT_ASSESSMENT`, `MEDIA_DESCRIPTION`, `NARRATOR_OPINION`, `UNVERIFIED_LABEL` 중 하나로 분류하고 확정 진단은 전문가와 Evidence 연결을 요구한다.

### Presentation Contract v2.1

- `panel_cast.json`은 공개 정보만 사용하는 서로 다른 Persona와 기능 구성을 가진 외부 Panelist를 최소 2명 정의한다.
- `reaction_segments.json`은 Segment 시간·배치·가설 변화와 `turns[]`를 정의한다. 각 Turn은 화자, 기능, 실제 발화, 근거 Clue, 공개 Fact와 Tone을 독립적으로 보존한다.
- `CHARACTER_REACTION`, `PANEL_REACTION`, `AUDIENCE_PROMPT`는 서로 다른 의미이며 비율에는 외부 `PANEL_REACTION`만 포함한다.
- `EXPERT_ANALYSIS`는 조건부 Presentation Segment다. Panel Reaction과 분리된 `expert_segments.json`과 `expert_analysis_script.md`를 Source로 사용하며 Expert Role, Credentials, Claim ID, Evidence Source ID, Confidence와 Limitations를 보존한다. Panel 의견을 Expert Fact로 승격시키지 않는다.
- Channel 2.0의 추리형 Panel은 가설 생성·수정과 이상 또는 모순 탐지를 포함한다. 사건 중심 Channel 2.1은 `EMOTIONAL_REACTION`과 수상 행동·용의자 추적·의견 수정 기능 중 하나 이상을 요구하며 고정된 가설 Turn 비율은 두지 않는다.
- `drama_script.md`, `narration_script.md`, `panel_reaction_script.md`는 분리 작성한다. Narration은 화면 행동이나 Panel 발화를 그대로 반복하지 않는다.
- Channel 2.1 Narration은 사건 내부 인물의 감정·오해·기억을 전달하고, 범인·결백·동기·방식·피해 결과를 Viewer Plan보다 먼저 확정하지 않는다.
- `draft_v01.md`와 `final_script.md`는 `SEGMENT`, `TYPE`, `SCENE`, `DURATION`, `END_SEGMENT` Marker로 모든 계획 Segment를 정확히 한 번, 같은 순서와 시간으로 통합한다. Final은 Layer 본문을 보존한 Broadcast Master다.
- Viewer Timeline보다 먼저 공개된 Fact, 미공개 단서나 Fact를 사용하는 Panel, 역행하는 현재 절대시간, Actual Timeline과 다른 구조 완료 시각을 차단한다.
- `09_PRODUCTION/panel_reaction_script.md`와 `edit_script.md`는 Reaction ID, Segment ID를 보존한다. 각 Edit Timecode의 시작·종료 초는 Presentation Plan의 `start_sec`, `duration_sec`와 정확히 일치해야 한다.
- Segment `duration_sec` 합으로 계산한 Panel Reaction 비율은 계획된 편집 비율이다. Editorial Review는 각 Panel Segment의 실제 화자와 Script에서 재계산한 발화 단어 수를 보존하고, 발화시간과 Replay·Graphic·Reaction Hold 같은 비발화 요소가 계획시간을 완전히 설명하는지 검사한다.
- 사건 중심 Channel 2.1의 Runtime Evidence는 한국어 어절 기준, 추정 가정, 발화·행동·비발화 시간을 분리하고 Graphic을 포함한 모든 보충 시간의 Script 또는 편집 근거를 기록한다. 합계가 맞더라도 근거 없는 Graphic 시간은 허용하지 않는다.
- `WORD_COUNT_ESTIMATE`는 명시한 WPM으로 예상 발화시간을 계산한다. `TABLE_READ`와 `RECORDED_AUDIO`는 Segment별 실측 `measured_duration_sec`와 합계를 요구한다. Human Editor는 이 근거로 방송 호흡과 의미상 중복을 최종 판단한다.
- Validator는 모든 Turn의 화자·기능·근거·공개 시점과 Panel Script의 순서·문장을 검증한다. 자연스러운 집단 대화가 필요한 Reaction Segment는 최소 두 명 이상의 짧은 질문·반박·가설 수정·감정 연결을 허용한다. 결정론적 Validator가 Metadata나 문장 표면 일치로 잡기 어려운 의미상 조기 공개와 바꿔 쓴 반복은 Human Editorial Review 책임으로 남긴다.

### Fact Integrity

`TRUE_STORY`와 `INSPIRED_BY_TRUE_EVENTS`의 모든 `FACT`는 존재하는 Source와 Claim-Evidence에 연결한다. `INFERENCE`는 근거 Fact를 참조하고 `DRAMATIZATION`은 검증된 Fact로 표시할 수 없다. 깨진 Source/Fact 참조나 Evidence가 없는 Fact는 Case Gate를 차단한다.

## 10. Dependency Invalidation과 이력

`STANDARD/dependency_graph.json`은 각 Artifact의 경로, 선행 Artifact, Owner Agent를 정의한다. 상위 Artifact Hash가 바뀌면 모든 Transitive Dependent를 `DIRTY`로 만들고 `invalidated_by`를 기록한다. 입력 객체는 수정하지 않고 새 Project State를 반환한다.

`00_PROJECT/change_log.jsonl`은 초기화, Variation 생성/승인, Gate Transaction Commit, 명시적 State 복구, Editorial 승인, Production 확정, Story Library 등록을 시간과 함께 기록한다. `process_trace.jsonl`은 Gate별 Task, Agent, 입력 Hash, 변경 경로, Validator, 결과, Commit SHA와 시각을 보존한다. Audit은 Project 생성, Change Log, Gate Transaction과 Process Trace Timestamp가 인과 순서를 지키는지 검증한다. Draft부터 Novelty Index에 추적하되 Production Ready Fingerprint만 Published Story Library에 등록할 수 있으며 동일 Project의 중복 등록은 실패한다.

## 11. 승인 정책

기본값 `AUTO_CONTINUE`는 Gate PASS 뒤 다음 Gate Task를 여는 데 추가 승인을 요구하지 않는다. 다음 경우에는 Human Review가 필요하다.

- Novelty 실패를 예외 승인하려는 경우
- Fact와 Dramatization이 충돌하는 경우
- 검증 불가능한 실화 주장을 사실로 사용하려는 경우
- 승인 Variation과 다른 구조를 Override하면서 제작 방향이 달라지는 경우
- 최종 Editorial Review를 승인하고 Production Ready를 확정하는 경우

Runtime의 Human Approval은 Run ID, Task ID, 현재 입력 Artifact Hash에 결합한다. 입력이 바뀐 승인은 자동으로 무효이며 Actor와 비어 있지 않은 Reason이 없으면 기록할 수 없다.

## 12. 실행 인터페이스

```bash
mystery-kit init PRJ-002
mystery-kit compat PROJECTS/PRJ-002
mystery-kit variations PROJECTS/PRJ-002 --seed "공장 교대 중 실종" --count 5
mystery-kit precheck PROJECTS/PRJ-002
mystery-kit approve PROJECTS/PRJ-002 VAR-03
mystery-kit migrate-channel-pin PROJECTS/PRJ-002 --channel-content-version 1.1.0
mystery-kit reference-profile PROJECTS/PRJ-002 /secure/reference-source.json
mystery-kit validate PROJECTS/PRJ-002
mystery-kit task-open PROJECTS/PRJ-002 GATE-05
mystery-kit task-status PROJECTS/PRJ-002
mystery-kit task-submit PROJECTS/PRJ-002 GATE-05
mystery-kit task-abort PROJECTS/PRJ-002 GATE-05
mystery-kit task-return PROJECTS/PRJ-002 script_writer --actor critic --reason "Editorial Issue 수정"
mystery-kit audit PROJECTS/PRJ-002
mystery-kit rebuild-state PROJECTS/PRJ-002 --force
mystery-kit editorial-approve PROJECTS/PRJ-002 --actor reviewer --reason "검토 완료"
mystery-kit production-finalize PROJECTS/PRJ-002
mystery-kit register PROJECTS/PRJ-002

mystery-runtime doctor
mystery-runtime plan PROJECTS/PRJ-RUNTIME-TEST
mystery-runtime run PROJECTS/PRJ-RUNTIME-TEST --from GATE-00 --to GATE-13
mystery-runtime status PROJECTS/PRJ-RUNTIME-TEST
mystery-runtime approve RUN-... variation.approve --actor reviewer --reason "검토 완료"
mystery-runtime resume RUN-...
mystery-runtime cancel RUN-...
mystery-runtime providers
```

기본 배포의 FakeProvider Runtime 명령은 격리된 회귀 Project에서만 사용한다. 실제 작품 제작은 Codex App이 Gate Task Workspace에 Artifact를 작성하고 `task-submit`으로 순서대로 검증·Commit한다. `validate`와 `audit`는 상태를 바꾸지 않는 진단이며 `rebuild-state --force`만 명시적 복구를 수행한다.

`mystery-kit` 종료 코드는 `PASS=0`, 검증 실패 `=1`, 입력·구성·Transaction 오류 `=2`다. `mystery-runtime`은 성공 `0`, 구조화 Runtime 오류 `2`를 사용한다. `production-finalize`와 `register`는 네 준비 조건을 모두 충족하지 않은 Project를 거부한다.

## 13. Version 정책

- 동일 Major Schema 안의 추가 필드는 소비자가 명시적으로 허용한 경계에서만 Forward Compatible하다.
- Contract의 Version Range는 `min_inclusive <= schema_version < max_exclusive`다.
- 독립 Channel Interface 판정은 `content_version`을 사용하지 않는다. Project Compatibility에서는 고정된 `channel_content_version`, Manifest 등록, 실제 DNA Content Version과 SHA-256 불일치를 실패로 처리한다.
- Major Schema 변경은 Migration 또는 Adapter 설계를 동반한다.
- Standard, Schema, Agent Contract, Validator, Test가 바뀌면 구현 매트릭스와 문서를 같은 Pull Request에서 갱신한다.

Presentation Artifact는 1.x에서 2.0.0으로 Breaking Change되었다. 기존 Project는 대본을 자동 창작해 통과시키지 않으며 `PRESENTATION_MIGRATION_REQUIRED`로 전환하고 기존 파일을 보존한다. GATE-05 이후 Artifact는 `DIRTY`, 기존 Presentation Plan과 Draft/Final Script는 `INVALID`, 새 v2 Artifact는 `MISSING`으로 기록한 뒤 GATE-05부터 재생성한다.

Project State 1.2.0은 Artifact, Contract, Process, Editorial 준비 상태, `process_start_gate`, `process_revision`을 기록한다. 기존 Project는 보유 Artifact와 과거 Trace를 삭제하거나 추정하지 않는다. 재생성 시작 Gate부터 현재 Revision의 실제 Trace를 쌓기 전까지 `PROCESS_CONFORMANT`, `EDITORIAL_APPROVED`, `PRODUCTION_READY`로 인정하지 않는다.

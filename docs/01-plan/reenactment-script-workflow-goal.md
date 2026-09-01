# 소스형 재연극 인물별 스크립트 Workflow Goal Ledger

## Foundation

- 검증 시각: 2026-09-01 (Asia/Seoul)
- Foundation PR: `#24 feat: align Channel DNA 2.1 with explicit interpersonal crime`
- Foundation branch: `origin/codex/channel-explicit-crime-alignment`
- 예상·실제 Foundation SHA: `b24b47456003057cfebbecf9e156551cc51369f2`
- 선조 관계: 실제 원격 HEAD가 예상 SHA와 동일하며 `origin/main`의 후손이다.
- PR 상태: `OPEN`, `CLEAN`, 미병합
- 현재 Stack branch: `codex/reenactment-runtime-v1`
- PR #23: `OPEN`; PR #24 계보의 선행 변경이므로 자동 종료하지 않고 최종 보고에서 superseded/retarget 권고만 기록한다.
- Source-style 원문: 이 Task에는 네 원문 파일이 첨부되지 않았다. Goal에 정제된 추상 기능 요구만 사용하며 고유 인명·대사·장소·사건·반전은 저장소나 Runtime Context에 반입하지 않는다.

## Baseline

Foundation HEAD에서 Canonical Project State를 변경하지 않고 다음을 실행했다.

| 검증 | 결과 | 증거 |
|---|---|---|
| `.venv/bin/python -m ruff check .` | PASS | `All checks passed!` |
| `.venv/bin/python -m mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests` | PASS | 126 source files |
| `.venv/bin/python -m pytest -q` | PASS | 322 collected tests, exit 0 |
| `.venv/bin/python -m build` | PASS | `mystery_starter_kit-1.6.1` sdist/wheel |
| `.venv/bin/python -m pip_audit` | PASS | 알려진 취약점 없음; PyPI에 없는 로컬 패키지만 제외 |
| `.venv/bin/mystery-runtime doctor` | PASS | contracts/provider descriptors PASS |
| `.venv/bin/python -m VALIDATORS.version_immutability --base-ref origin/main` | PASS | `REGISTERED_VERSION_IMMUTABILITY_PASS` |

Version 명칭은 서로 다른 수명주기다. Package는 `1.6.1`, Production Standard는 `1.3.3`, 활성 Channel content는 `2.1.0`, Runtime interface는 `1.0.0`이다. 하나의 숫자로 합치지 않고 최종 사용자 문서에서 종류를 함께 표기한다.

## Phase 상태

- [x] Phase 0 — Foundation, baseline, 영향 설계
- [x] Phase 1 — Versioned multi-harm event model
- [x] Phase 2 — Screenplay Units와 Output Profile 계약
- [x] Phase 3 — Clue recontextualization과 flexible state transition
- [x] Phase 4 — Deterministic CORE renderer
- [x] Phase 5 — Export integrity와 semantic binding
- [ ] Phase 6 — Runtime Task, Agent, Gate, dependency 통합
- [ ] Phase 7 — 재연극 runtime 계획·측정 분리
- [ ] Phase 8 — 네 Source-style feature fixture와 Full Original Pilot
- [ ] Phase 9 — 최종 문서·수용 증거·Stacked PR

현재 Phase: `5`

## Architecture 결정

1. `screenplay_units.json`을 새 대본 경로의 LLM 소유 단일 Source로 둔다. Layer Script, Broadcast Master, 재연극 Export와 QA Report는 CORE가 결정론적으로 파생한다.
2. 기존 Project에서 `script_source_mode`가 없으면 `LEGACY_MARKDOWN`으로 해석한다. 호환성 검증 뒤 새 Scaffold만 `SCREENPLAY_UNITS`를 명시해 자동 Migration을 막는다.
3. `harms[]`가 새 Crime Artifact version의 SSOT다. `harm_ids`, `harm_classifications`, `immediate_harm`, `lasting_harm`은 구버전 입력과 소비자를 위한 파생 호환 필드로 유지하고 새 문서에서는 배열과 일치해야 한다.
4. Candidate Event Brief는 피해자를 Role Slot에, bound Crime Event Contract는 실제 Character ID에 결속한다.
5. Output Profile은 Channel DNA capability에 섞지 않고 `CHANNELS/mystery_main/output_profiles/reenactment-character-script/1.0.0.json`에 독립 Version으로 둔다. Canonical Artifact 경로는 고정하고 작품명 파일은 명시적 외부 Export 명령에서만 만든다.
6. 기존 `psychological_arc`와 활성 Capability는 변경하지 않는다. Explicit Crime의 새 경로는 별도 `character_state_transitions`를 사용하며 회복 단계는 해당 정책이 요구할 때만 적용한다.
7. Trace·Hash·QA verdict는 LLM 출력에서 금지한다. CORE는 실제 Unit reference와 exact text로 Trace와 Report를 만들며 `NEEDS_REVIEW` 또는 `MISSING`만 선언한다.
8. Broadcast runtime과 reenactment runtime을 Production Config의 별도 target/tolerance와 별도 evidence hash로 검증한다. Estimate를 measurement나 Human Approval로 승격하지 않는다.
9. Phase commit의 자기 SHA는 동일 Commit 내용에 안정적으로 기록할 수 없으므로, 각 완료 Commit은 제목으로 즉시 식별하고 그 SHA는 다음 Ledger 갱신 및 최종 수용 Commit에서 고정한다.

## 거부한 대안

- 기존 `final_script.md`에서 인물별 대사만 정규식으로 추출: Unit 순서·화자·특수 텍스트·참조 무결성을 증명하지 못한다.
- LLM이 Layer Markdown과 `CRIME_TRACE`를 계속 직접 작성: Metadata-only spoofing과 Text 변형을 차단할 수 없다.
- 작품 제목을 Canonical filename에 사용: Artifact ownership, State Hash와 Dependency Graph의 고정 경로를 깨뜨린다.
- 기존 Crime Event 1.1 문서를 제자리에서 multi-harm 필수로 강화: Channel 1.1/2.0과 기존 Project 검증을 깨뜨린다.
- 모든 범죄 구조에 고정 회복 Arc 적용: 사망 피해·목격자 중심·비회복 결말을 왜곡한다.
- FakeProvider 결과를 창작 품질 증거로 사용: 회귀 Fixture일 뿐 Editorial 판단이 아니다.

## Artifact·Schema·Task·Agent·Validator 영향 행렬

| 영역 | 현재 상태 | 계획된 변경 | 호환성/검증 |
|---|---|---|---|
| Candidate Event Brief Schema | 1.0, 평탄 피해 문구 | 1.1 `harms[]` Role Slot SSOT | 1.0 계속 허용; 1.1 조건부 필수·일치 검증 |
| Crime Event Contract Schema | 1.1, `harm_ids`/분류 평탄화 | 1.2 `harms[]` Character binding | 1.1 계속 허용; Projection/Contract hash 회귀 |
| Screenplay Unit Schema | 없음 | 1.0 Scene Context, ordered Units, typed references | 모든 Unit type 정상/실패 Fixture |
| Output Profile Schema/Registry | 없음 | 독립 1.0 Profile과 Registry | Config pin 존재·Hash·Version 검사 |
| Clue Matrix | loose legacy fields | Versioned recontextualization fields | 기존 Clue 문서 불변; 새 path에만 순서 검증 |
| Character State Transition | 고정 `psychological_arc` 중심 | Explicit Crime용 flexible transition Artifact/field | 기존 Capability 동작·테스트 유지 |
| Production Config | 방송 runtime만 존재 | source mode/profile pin, reenactment target/tolerance | 필드 부재는 Legacy, 새 Scaffold만 opt-in |
| Artifact Contracts | Layer/Broadcast만 존재 | Units, canonical reenactment export/report/production copy | Schema/owner/max size 검증 |
| Runtime Tasks | LLM Layer·Master 작성 | LLM Units 1개 + CORE Layers/Master/Export/QA/package | Task별 최소 reads/writes와 조건 분기 |
| Agent Manifest/문서 | Script Writer가 Markdown/Trace 작성 | Script Writer는 Units만, CORE 파생; Critic read-only QA | Runtime Task가 Agent 최대 권한의 부분집합 |
| Dependency Graph | final script 중심 | Units·Character·Scene·Event/Harm·Clue·Profile·timing에서 모든 파생물 전이 무효화 | dependency/invalidation tests |
| State/Gate | Artifact DAG 기반 상태와 순차 Gate v1.1 | 새 조건부 Artifact를 GATE-08/09/13에 포함 | 최소 Allowlist, drift, no intermediate commit |
| Scaffold | Legacy Markdown config | 검증 후 신규 Scaffold에 `SCREENPLAY_UNITS` pin | Legacy fixture에는 소급하지 않음 |
| Validators | Marker parser·crime realization | Unit/schema/profile/multi-harm/clue/export/runtime validators | 정상·mutation·stale·leakage tests |
| Production packaging | LLM production bundle | fixed canonical production reenactment copy와 explicit title export CLI | Byte identity와 path traversal 차단 |
| Tests | 322 baseline | 계약/renderer/runtime/4 fixture/full pilot | 기존 1.1/2.0/2.1 회귀 포함 |
| Docs | Layer/Broadcast 경로 | 선택·Gate·Export·migration/rollback·Version 표기 | README CLI golden path |

## Dependency와 Invalidation 설계

```text
crime_event_contract ─┐
characters ───────────┤
actual/viewer timeline├─> scene_cards ─┐
clue_matrix ──────────┘                ├─> screenplay_units
production_config/output_profile ─────┘          │
                                                  ├─> drama/narration layers
reaction contract ────────────────────────────────┼─> broadcast master
                                                  ├─> reenactment export
                                                  └─> reenactment export report
                                                        │
                                                        └─> production reenactment copy
```

Unit, Character name, Scene context, Event/Harm, Clue, Output Profile 또는 runtime target 변경은 Report와 모든 downstream export를 `DIRTY`로 만든다. Legacy mode에서는 기존 dependency와 필수 Artifact 집합을 그대로 사용한다.

## Branch와 Commit Ledger

| Phase | Branch | Commit | 상태 |
|---|---|---|---|
| 0 | `codex/reenactment-contracts-v1` | `0992c920b9fd69b80f112d9fa95f4522feeb3fd3` | 완료 |
| 1 | `codex/reenactment-contracts-v1` | `5b42991569a5edaa8534c7cb68376127fa8374c6` | 완료 |
| 2 | `codex/reenactment-contracts-v1` | `03aa87a6d9e07796b4a1e55f1a7309625d6675e1` | 완료 |
| 3 | `codex/reenactment-contracts-v1` | `d12e9823e27c788762efc49f2b8b787f33c5f635` | 완료 |
| 4 | `codex/reenactment-runtime-v1` | `d88e96d0aef3af487b8005c9a54911d7690beeb7` | 완료 |
| 5 | `codex/reenactment-runtime-v1` | `feat: validate reenactment export integrity` | 현재 Commit 예정 |
| 6–7 | `codex/reenactment-runtime-v1` | Phase별 Commit | 대기 |
| 8–9 | `codex/reenactment-pilot-v1` | Phase별 Commit | 대기 |

## Backward Compatibility 전략

- Channel 1.1·2.0과 Historical Project는 config field 부재를 `LEGACY_MARKDOWN`으로 해석한다.
- 새 Schema는 명시 Version에 따라 조건을 나누며 등록된 Channel/Variation Engine 파일을 변경하지 않는다.
- 구버전 Crime Event·Clue·Psychological Arc 문서를 Migration 없이 검증한다.
- 기존 LLM Script Task와 Gate 경로는 Legacy mode에서 유지한다.
- 새 Task와 Artifact requiredness는 `script_source_mode == SCREENPLAY_UNITS`일 때만 활성화한다.
- 새 Scaffold 생성물만 새 mode/profile pin을 기본값으로 사용할 수 있고 기존 Project 파일은 일괄 수정하지 않는다.
- Rollback은 Production Config pin을 `LEGACY_MARKDOWN`으로 새 Gate revision에서 명시하고 downstream Script Artifact를 재생성하는 방식이며 Canonical 이력을 삭제하지 않는다.

## 현재 Risk와 Deferred 항목

- Runtime condition DSL에 `config_equals`를 추가했으며 Phase 6에서 새 Task와 Gate requiredness가 같은 Predicate를 사용하도록 결속해야 한다.
- 기존 Broadcast marker parser와 새 Unit-derived evidence가 공존해야 하므로 mode별 단일 진입점을 명확히 분리해야 한다.
- Package metadata에 Standard version `1.3.3`이 보이는 기존 build metadata 경로를 조사해 사용자 문서에서 Package `1.6.1`과 혼동되지 않게 해야 한다.
- Cross-Python byte determinism은 CI matrix 결과를 최종 증거로 사용한다.
- 대사의 자연스러움·캐릭터 음성·반전 설득력은 결정론적 PASS로 위장하지 않고 Pilot Editorial evidence의 `NEEDS_REVIEW`로 남긴다.

## Phase 1 수용 증거

- Candidate Event Brief `1.0.0`과 Crime Event Contract `1.1.0`은 `harms[]` 없이 기존 Schema·Validator를 계속 통과한다.
- Candidate Event Brief `1.1.0`은 `harm_id`, classification, timing, `victim_role_slots`, exact summary를 가진 `harms[]`와 파생 호환 필드를 요구한다.
- Bound Crime Event Contract `1.2.0`은 각 Role Slot을 실제 `victim_ids`에 결속하고 동일 피해 집합에서 `harm_ids`, `harm_classifications`, immediate/lasting summary를 파생한다.
- `HARM_ID_DUPLICATED`, `HARM_VICTIM_BINDING_INVALID`, `HARM_VICTIM_COVERAGE_MISSING`, `HARM_CLASSIFICATION_ACTION_MISMATCH`, `HARM_OUTCOME_REQUIRED`, `HARM_COMPATIBILITY_FIELDS_MISMATCH`, `CRIME_HARM_PROJECTION_MISMATCH`를 명시적으로 검증한다.
- Timeline과 Causal Graph는 여러 결과 Event/Node에 나뉜 Harm의 합집합 coverage를 검증한다. Scene과 Script도 모든 Contract Harm의 누락을 차단한다.
- Targeted regression: Explicit Crime, Scene Realization, Candidate Evaluation, Pipeline, Runtime Engine 묶음 PASS.
- Targeted Ruff와 strict mypy: PASS.

## Phase 2 수용 증거

- `screenplay-units` `1.0.0`은 Scene Context, 열한 Unit 유형, exact text, speaker/delivery와 Fact·Clue·Crime Event·Harm·Development Function·Reveal Target 참조를 구조화한다.
- spoken/character-authored Unit은 `speaker_id`를 요구하고 Action·Sound·Screen Text는 speaker와 delivery를 금지한다. Scene·Unit·Sound Cue order와 ID, Segment 연결, 이전 Scene과 선행 Reconstruction 참조는 별도 의미 Validator가 검사한다.
- `REENACTMENT_CHARACTER_SCRIPT@1.0.0` Profile은 필수 제목·Cast 표·Scene Context·지문/음향/화자·특수 Unit 표시·포함/제외 Layer와 Unit·내부 Marker 제거·Original Fiction 불명확 Marker 금지를 고정한다.
- Profile Registry는 파일 SHA-256을 검증하고 Config Pin이 없거나 미등록 Version이면 fallback 없이 실패한다. 등록된 동일 Version의 Entry와 파일 변경은 Version Immutability 검사 대상이다.
- Production Config에 새 선택 필드를 추가했다. 필드가 없는 기존 Project는 `LEGACY_MARKDOWN`으로 해석되고, `SCREENPLAY_UNITS`는 Profile ID와 Version을 함께 요구한다.
- `screenplay_units`, canonical 재연극 Script, Export Report, Production copy를 Artifact Contract·Dependency Graph·Agent 최대 권한에 등록했다. 모든 새 Artifact는 새 mode에서만 필수이며 Unit 변경은 Broadcast·Export·Report·Production·Editorial downstream을 무효화한다.
- 열한 Unit 유형, speaker 조합, ID/order 중복, 잘못된 Reconstruction, Profile Schema/Hash/Pin/Version, Legacy Config, Predicate와 DAG invalidation을 Targeted test로 검증했다.
- Runtime Doctor, 기존 Scaffold·Gate Transaction·Runtime Engine·Production CLI 회귀, Targeted Ruff·strict mypy, Registered Version Immutability: PASS.

## Phase 3 수용 증거

- Clue Matrix는 필드가 없는 Legacy 문서와 `clue-matrix` `1.1.0` 문서를 함께 허용한다. 새 Version의 최종 Reveal Clue는 `SEEDED_REINTERPRETATION` 또는 `INTENTIONAL_NON_MYSTERY_DISCLOSURE`를 명시한다.
- Seeded Reinterpretation은 `surface_meaning`, 서로 다른 `actual_meaning`, 선행 `first_seen_scene_id`, 후행 `reveal_scene_id`, 시간순 `recontextualized_scene_ids`를 요구한다. `REVEAL_WITHOUT_PRIOR_SEED`, `CLUE_MEANING_NOT_RECONTEXTUALIZED`, Scene/Reveal binding 오류를 명시적으로 보고한다.
- Screenplay Units `1.1.0`은 재구성 반복을 `source_unit_id`와 `repeated_unit_id`로 결속한다. 반복 text와 type이 원본과 정확히 같지 않거나 반복 Unit이 Metadata 없이 나타나면 `RECONSTRUCTION_REPETITION_MISMATCH`로 실패한다. `1.0.0` 문서는 기존 동작을 유지한다.
- `05_STORY/character_state_transitions.json`은 Beat 또는 Scene Scope, 인물별 before/after 상태, Fact·Clue·Crime Event Trigger, Information·Emotion·Relationship·Risk·Choice·Belief 변화 범주를 지원한다.
- 유연한 Transition은 새 Screenplay mode와 Explicit Crime Capability에서만 필수다. 기존 고정 `psychological_arc`는 Legacy + 해당 Scene Realization Capability 조합에서만 요구되며 제자리 변경하지 않았다.
- 사망 피해·목격자·비회복 경로는 `AGENCY_RECOVERY`를 요구하지 않는다. Validator는 ID/order, 실제 상태 Delta, 동일 인물 Chain, Character·Beat/Scene·Trigger 참조를 검증한다.
- 새 Clue와 Transition Schema를 Artifact Contract, Dependency Graph, Agent 최대 권한과 GATE-05~07 Validator 경로에 등록했다. 새 Schema 키가 없는 기존 호출자의 Schema Map도 계속 허용한다.
- 계약 브랜치 전체 검증: Ruff PASS, strict mypy PASS(133 source files), 전체 pytest PASS, package `1.6.1` sdist/wheel build PASS, dependency audit 알려진 취약점 없음, Runtime Doctor PASS, Registered Version Immutability PASS.

## Phase 4 수용 증거

- `screenplay_units`의 Scene·Unit 순서와 Presentation Segment를 결속해 Drama와 Narration Layer를 순수 함수로 렌더링한다. Unit text는 LF 줄바꿈 외에 교정·요약·재작성하지 않는다.
- 방송 내부 `UNIT`과 `CRIME_TRACE` Marker는 실제 렌더링한 Unit References의 합집합에서만 파생한다. Event가 Crime Contract와 결속됐을 때만 Action Type을 더하며 한 Segment의 여러 Harm과 Development Function을 모두 보존한다.
- 기존 Reaction Contract의 Turn 순서·화자·발화를 Panel Layer로 렌더링하고, Layer Segment를 Presentation 순서와 source artifact에 따라 Broadcast Master로 결합한다. 계획 누락·중복·계층 불일치는 조용히 유실하지 않고 구체적 구성 오류를 낸다.
- 재연극 문서는 등록 Output Profile, Canonical Characters와 Relationships로 작품 정보·구성 원칙·Cast 표·상세 Scene Context와 열한 Unit 유형을 렌더링한다. Panel Reaction, Expert Analysis, Audience Prompt, 내부 Fact·Clue·Event·Harm·Unit Marker는 경로상 반입하지 않는다.
- Production copy 함수는 검증된 Canonical 재연극 Markdown을 바이트 그대로 반환한다. 명시적 외부 Export 파일명은 작품명에서 경로 구분자와 제어 문자를 제거해 `[작품명]_인물별_대사_스크립트.md` 규칙을 안전하게 적용한다.
- Golden Markdown snapshot, 반복 호출 byte identity, 모든 Unit 원문 발생 횟수, 특수 유형 Label, 방송 전용 내용의 zero leakage, COLD_OPEN 후 RECONSTRUCTION 순서, multi-harm trace, 잘못된 계층 배치, Production byte identity와 export path 안전성을 회귀 테스트로 고정했다.
- Targeted Ruff·strict mypy와 새 Renderer 테스트: PASS. 전체 Ruff·strict mypy와 pytest 356개 회귀 테스트도 PASS했다. 로컬의 3.11~3.13 Interpreter에는 Project dependency 환경이 없어 교차-Version 실행은 CI matrix 증거로 남긴다.

## Phase 5 수용 증거

- `reenactment_export_report`는 Production Config, Screenplay Units, Characters, Relationships, Crime Event Contract, Clue Matrix, Output Profile, Presentation Plan과 Broadcast Master의 Canonical Hash를 입력 증거로 기록한다. Profile 원본 Hash와 재연 Markdown bytes Hash도 별도로 고정한다.
- Report는 Scene heading coverage, 포함 Unit의 exact block·order·중복, Canonical speaker resolution, 포함·제외 유형, 모든 Contract Harm, Seed/Reveal Clue, Reconstruction 원본·exact repetition과 runtime 구성 상태를 결정론적으로 기록한다.
- 현재 입력에서 재연 Markdown 전체를 다시 렌더링해 bytes를 비교한다. Unit text, Cast·Relationship, Scene Context 또는 Profile이 달라지면 `UNIT_RENDER_MISMATCH`이고, 기존 Report와 재구성 Report가 한 필드라도 다르면 `REENACTMENT_EXPORT_REPORT_STALE`이다.
- Broadcast Master의 Segment 순서와 내부 `UNIT` Marker를 각 Unit References에서 다시 계산한다. `CRIME_TRACE`의 Event·Action·여러 Harm·Development Function 집합도 해당 Segment의 실제 Unit에서 재계산하므로 숨은 Trace만 조작하거나 가시 본문 없는 Trace를 넣을 수 없다.
- Original Fiction 명시, Panel/Expert/Audience와 내부 Marker zero leakage, Cast·speaker·Scene Context, 특수 Unit 보존, Harm coverage, 선행 Seed와 회고적 의미, Reconstruction 선행 참조를 구체적 Issue code로 실패시킨다.
- 정상 CORE 결과는 `NEEDS_REVIEW`, 본문 부재는 `MISSING`, 기계 오류는 `FAIL`만 사용하며 Editorial PASS를 선언하지 않는다.
- speaker, Unit text/order, 내부 Trace, Output Profile filter, 특수 Unit 삭제·중복, Panel 삽입, Harm, Clue/Reveal, retrospective meaning, Reconstruction, Original Fiction marker, Report 생성 뒤 output bytes와 Metadata-only spoof를 mutation test로 검증했다.
- Targeted Ruff·strict mypy와 11개 Export test PASS. 전체 Ruff, strict mypy 137 source files, pytest 367개 회귀 테스트 PASS.

## Final Acceptance Evidence

Phase 9에서 요구사항별 명령, SHA, PR, Pilot Artifact 경로와 결과를 기록한다. Human Editorial Approval, `production-finalize`, `register`, PR Merge는 의도적으로 수행하지 않는다.

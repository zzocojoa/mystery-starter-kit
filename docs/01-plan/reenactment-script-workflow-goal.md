# 소스형 재연극 인물별 스크립트 Workflow Goal Ledger

## Foundation

- 검증 시각: 2026-09-01 (Asia/Seoul)
- Foundation PR: `#24 feat: align Channel DNA 2.1 with explicit interpersonal crime`
- Foundation branch: `origin/codex/channel-explicit-crime-alignment`
- 예상·실제 Foundation SHA: `b24b47456003057cfebbecf9e156551cc51369f2`
- 선조 관계: 실제 원격 HEAD가 예상 SHA와 동일하며 `origin/main`의 후손이다.
- PR 상태: `OPEN`, `CLEAN`, 미병합
- 현재 Stack branch: `codex/reenactment-pilot-v1`
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
- [x] Phase 6 — Runtime Task, Agent, Gate, dependency 통합
- [x] Phase 7 — 재연극 runtime 계획·측정 분리
- [x] Phase 8 — 네 Source-style feature fixture와 Full Original Pilot
- [x] Phase 9 — 최종 문서·수용 증거·Stacked PR

현재 Phase: `9`

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
| 5 | `codex/reenactment-runtime-v1` | `659f9e5e403a5bdc25bd2749d1d8b668245e98ed` | 완료 |
| 6 | `codex/reenactment-runtime-v1` | `60e6cbef639f8d108f96be5b76524091f08c9fd6` | 완료 |
| 7 | `codex/reenactment-runtime-v1` | `f79779b747a8ae5103159657ad9bcf997328156d` | 완료 |
| 8 | `codex/reenactment-pilot-v1` | `1dc769c` | 완료 |
| 9 | `codex/reenactment-pilot-v1` | `docs: finalize reenactment workflow acceptance evidence` | 현재 Commit 예정 |

## Backward Compatibility 전략

- Channel 1.1·2.0과 Historical Project는 config field 부재를 `LEGACY_MARKDOWN`으로 해석한다.
- 새 Schema는 명시 Version에 따라 조건을 나누며 등록된 Channel/Variation Engine 파일을 변경하지 않는다.
- 구버전 Crime Event·Clue·Psychological Arc 문서를 Migration 없이 검증한다.
- 기존 LLM Script Task와 Gate 경로는 Legacy mode에서 유지한다.
- 새 Task와 Artifact requiredness는 `script_source_mode == SCREENPLAY_UNITS`일 때만 활성화한다.
- 새 Scaffold 생성물만 새 mode/profile pin을 기본값으로 사용할 수 있고 기존 Project 파일은 일괄 수정하지 않는다.
- Rollback은 Production Config pin을 `LEGACY_MARKDOWN`으로 새 Gate revision에서 명시하고 downstream Script Artifact를 재생성하는 방식이며 Canonical 이력을 삭제하지 않는다.

## 현재 Risk와 Deferred 항목

- 기존 Broadcast marker parser와 새 Unit-derived evidence는 mode별 회귀가 통과했다. Phase 8 Pilot에서 실제 LLM 작성 Unit의 자연스러운 Scene·발화와 동일 불변식이 함께 유지되는지 확인해야 한다.
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

## Phase 6 수용 증거

- Runtime Task Catalog는 47개 Task로 확장됐다. `story.design_state_transitions`와 `script.compose_screenplay_units`만 새 구조 콘텐츠를 LLM이 작성하고, 후자는 최소 승인 구조 입력을 읽어 `screenplay_units` 하나만 쓴다.
- `script.render_screenplay_layers`, `script.render_broadcast_master`, `script.render_reenactment_export`, `continuity.validate_reenactment`, `production.package_reenactment`는 모두 CORE이며 Model Profile이 없다. Layer·Unit/Crime Trace·Broadcast·재연 Markdown·Report·Production copy를 LLM이 쓰지 못한다.
- 새 Task는 `script_source_mode == SCREENPLAY_UNITS`와 `REENACTMENT_CHARACTER_SCRIPT@1.0.0` Pin이 모두 일치할 때만 실행한다. 필드가 없는 기존 Config는 `script.write_layers`와 `script.integrate`만 실행하며 두 경로가 상호 배타적임을 회귀 테스트로 고정했다.
- Dependency Graph와 GATE-06/08/09/13 필수 Artifact에 State Transition, Screenplay Units, Reenactment Script, Export Report와 Production copy를 조건부 등록했다. Production Config/Profile, Unit, Character/Relationship, Scene, Event/Harm, Clue, Presentation/Final Script 변화가 Export와 Report를 무효화한다.
- GATE-08은 Screenplay Schema·순서 의미와 재연 Script 존재를 검사한다. GATE-09는 현재 Profile Hash와 모든 입력에서 Report를 재구성하며, GATE-13은 오류 없는 `NEEDS_REVIEW` Report와 byte-identical Production copy를 요구한다. GATE-12 전체 Validation에도 GATE-09 검증이 포함된다.
- 새 Scaffold는 Screenplay mode와 Output Profile을 명시한다. 기존 Historical Config와 Legacy Fixture는 필드 부재 기본값으로 유지한다. Agent Manifest·역할 문서·README·Runtime 설계 문서도 최소 권한과 LLM→CORE 순서를 반영했다.
- FakeProvider Full Gate 회귀는 새 경로로 GATE-00~13을 완주해 `EDITORIAL_REVIEW_REQUIRED`에서 정지했다. Screenplay/State/Export/Production Artifact가 생성되고 Production 재연 Script bytes가 Canonical 재연 Script와 동일했다. 이 Fixture는 Runtime 회귀 전용이며 창작 품질 증거가 아니다.
- 전체 검증: Ruff PASS, strict mypy PASS(137 source files), pytest PASS(369 tests), package `1.6.1` sdist/wheel build PASS, dependency audit 알려진 취약점 없음, Runtime Doctor PASS, Registered Version Immutability PASS.

## Phase 7 수용 증거

- Production Config의 `target_reenactment_minutes`와 `reenactment_runtime_tolerance_ratio`는 선택 필드이며 둘을 함께 설정해야 한다. 필드가 없는 기존 Project는 재연극 Runtime을 강제하지 않고 계속 통과한다.
- 재연극 목표는 전체 방송 목표를 초과할 수 없다. 고정 16분 가정은 사용하지 않으며 Project가 명시한 target/tolerance만 검증한다.
- CORE 계획시간은 Output Profile에 포함된 Unit type과 Layer가 모두 일치하는 고유 Presentation Segment만 합산한다. Report는 포함·제외 Segment ID, 계획 초, 예상 분과 입력 Hash를 보존한다.
- 설정된 목표의 허용범위 경계는 포함하고 경계를 넘으면 `REENACTMENT_RUNTIME_MISMATCH`로 실패한다. 방송 목표 초과는 별도 `REENACTMENT_RUNTIME_TARGET_EXCEEDS_BROADCAST`로 실패한다.
- Editorial 재연극 근거는 Export Report와 전체 입력 Hash에 결속하고 `WORD_COUNT_ESTIMATE`, `TABLE_READ`, `RECORDED_AUDIO`를 구분한다. Unit 또는 Report 변경 뒤 이전 근거는 `REENACTMENT_RUNTIME_MEASUREMENT_STALE`로 거부한다.
- `WORD_COUNT_ESTIMATE`에 실측값을 섞을 수 없으며 Production Finalize 조건을 충족하지 않는다. 설정된 재연극 Runtime의 Finalize에는 `TABLE_READ` 또는 `RECORDED_AUDIO` 실측이 필요하다.
- 전체 검증: Ruff PASS, strict mypy PASS(139 source files), pytest PASS(378 tests), package `1.6.1` sdist/wheel build PASS, dependency audit 알려진 취약점 없음, Runtime Doctor PASS, Registered Version Immutability PASS.

## Phase 8 수용 증거

- 네 Source-style Fixture는 원문을 반입하지 않고 추상 기능만 Original Fiction으로 고정했다. A는 가족 통제·조작된 자기 의심·허위 비난·복수 행위자 공모, B는 제한된 1인칭 살인 목격·기억 한계·후반 관계 단서 재구성, C는 스토킹·반복 접근·Message/Chat 위협·복수 피해, D는 출입권한 악용 감금·상세 Sound/Action·Note/Screen Text·선행 장면 재구성을 각각 검증한다.
- 모든 Fixture는 Screenplay 1.1 Schema와 의미 Validator를 통과한다. 특수 Unit 원문과 재구성 exact repetition은 재연본에 보존되고, Broadcast에는 Panel Segment가 유지되며 재연본에서는 Panel·Expert·Audience·내부 Trace Marker가 제거된다.
- Full Original Pilot `PRJ-005`, 작품명 `세 번째 종이 울린 뒤`를 정상 Codex Gate Transaction으로 GATE-00부터 GATE-13까지 순차 제작했다. 9회 Process Revision의 Owner Return을 통해 근거·관객 믿음·반응 밀도·피해 실현·창작 고지를 교정했고 최종 68개 Process Trace가 모두 결속됐다.
- Pilot은 11개 Scene, 29개 Presentation Segment, 109개 Screenplay Unit, 두 Harm(`LIBERTY_DEPRIVATION`, `BODILY_INJURY`)을 갖는다. `MESSAGE`, `CHAT`, `NOTE`, `RECORDING`, `SCREEN_TEXT`, `INNER_MONOLOGUE`를 포함하고, 콜드 오픈의 세 번의 종은 후반에 두 행위자의 위치 신호로 재맥락화된다.
- 25분 Broadcast Master는 7개 Panel Reaction Segment를 유지한다. 20분 재연극 Output은 Panel/Expert/Audience를 제외하며 Canonical과 Production 사본이 byte-identical하다. Export Report는 오류 없는 `NEEDS_REVIEW`, runtime은 `WORD_COUNT_ESTIMATE`로만 기록하고 실측으로 위장하지 않았다.
- Editorial Critic의 Artifact Hash·발췌 근거·의미 평가를 GATE-13에 결속했으나 Human Editorial Approval은 실행하지 않았다. 최종 State는 `EDITORIAL_REVIEW_REQUIRED`; Artifact는 `ARTIFACT_COMPLETE`, Contract는 `CONTRACT_VALIDATED`, Process는 `PROCESS_CONFORMANT`, Editorial은 미승인이다.
- `task-submit`이 같은 Gate의 다음 LLM Task를 반환하는 중간 상태에서 `runtime_transaction_id` 같은 Commit 전용 필드를 읽지 않도록 CLI를 보강하고 회귀 테스트를 추가했다.
- 공용 Story Library의 Novelty Index는 비어 있으며 `register`를 실행하지 않았다. Pilot 내부 Fingerprint·Novelty Report만 Canonical Project Artifact로 보존했다.
- Project `validate`와 `audit`는 GATE-00~13 전체 PASS, Issue 0, State 불변을 확인했다. 전체 검증은 Ruff PASS, strict mypy PASS(140 source files), pytest PASS(384 tests), package `1.6.1` sdist/wheel build PASS, dependency audit 알려진 취약점 없음, Runtime Doctor PASS, Registered Version Immutability PASS다.

## Final Acceptance Evidence

### Version과 Workflow 선택

- Package `1.6.1`, Production Standard `1.3.3`, 활성 Channel Content `2.1.0`, Reenactment Output Profile `REENACTMENT_CHARACTER_SCRIPT 1.0.0`, Broadcast Readable Output Profile `BROADCAST_READABLE_SCRIPT 1.0.0`, Runtime Interface `1.0.0`을 서로 독립 Version으로 문서화했다.
- 신규 Scaffold는 `SCREENPLAY_UNITS`와 Profile Pin을 사용한다. 필드가 없는 기존 Project는 `LEGACY_MARKDOWN`으로 남으며 자동 Migration하지 않는다.
- Channel Pin 전용 Migration은 `migrate-channel-pin`을 사용한다. Script mode 전환·Rollback은 명시적 변경 승인과 새 Process Revision에서 downstream 재생성을 요구하며 Canonical Artifact나 Trace를 삭제하지 않는다.
- Runtime은 ASR·전사를 제공하지 않는다. `WORD_COUNT_ESTIMATE`는 측정이 아니며 창작 품질은 Editorial과 Human 판단 대상으로 남는다.

### Stacked PR

| 역할 | PR | Base | 상태 |
|---|---|---|---|
| Foundation | [#24](https://github.com/zzocojoa/mystery-starter-kit/pull/24) | `main` | OPEN, 미병합 |
| Contracts | [#25](https://github.com/zzocojoa/mystery-starter-kit/pull/25) | `codex/channel-explicit-crime-alignment` | OPEN, 미병합 |
| Runtime | [#26](https://github.com/zzocojoa/mystery-starter-kit/pull/26) | `codex/reenactment-contracts-v1` | OPEN, 미병합 |
| Pilot | [#27](https://github.com/zzocojoa/mystery-starter-kit/pull/27) | `codex/reenactment-runtime-v1` | OPEN, 미병합 |

각 PR 본문은 목적·범위, 영향 파일/계약, 하위 호환성, 검증 증거, 알려진 한계, 의도적 제외와 선행 Stack 의존성을 분리한다.

### Pilot Artifact

- Canonical Unit: `PROJECTS/PRJ-005/07_SCRIPT/screenplay_units.json`
- Broadcast Master: `PROJECTS/PRJ-005/07_SCRIPT/final_script.md`
- Canonical 재연본: `PROJECTS/PRJ-005/07_SCRIPT/reenactment_character_script.md`
- Export 무결성·Runtime Report: `PROJECTS/PRJ-005/08_QA/reenactment_export_report.json`
- 기술적 Editorial 근거: `PROJECTS/PRJ-005/08_QA/editorial_review.json`
- Production 재연 사본: `PROJECTS/PRJ-005/09_PRODUCTION/reenactment_character_script.md`
- Project State: GATE-13, `EDITORIAL_REVIEW_REQUIRED`, `ARTIFACT_COMPLETE`, `CONTRACT_VALIDATED`, `PROCESS_CONFORMANT`, Editorial 미승인

### 검증 명령과 결과

```bash
PYTHONPATH=. .venv/bin/mystery-kit validate PROJECTS/PRJ-005
PYTHONPATH=. .venv/bin/mystery-kit audit PROJECTS/PRJ-005
cmp -s PROJECTS/PRJ-005/07_SCRIPT/reenactment_character_script.md \
  PROJECTS/PRJ-005/09_PRODUCTION/reenactment_character_script.md
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/python -m pip_audit
.venv/bin/mystery-runtime doctor
.venv/bin/python -m VALIDATORS.version_immutability --base-ref origin/main
```

- Project validate/audit: GATE-00~13 PASS, Issue 0, Process Trace 68개, State 불변
- Render integrity: Canonical/Production 재연본 byte-identical, Panel은 Broadcast에만 존재
- Ruff PASS, strict mypy PASS(140 source files), pytest PASS(384 tests)
- Package `1.6.1` sdist/wheel build PASS
- Dependency audit: 알려진 취약점 없음; PyPI에 없는 로컬 Package만 제외
- Runtime Doctor와 Registered Version Immutability PASS

### 의도적으로 미수행

- Human `editorial-approve` 미수행
- CLI `production-finalize`와 Production Ready 전이 미수행
- `register` 미수행; 공용 Novelty Index 항목 0개
- PR #23, #24, #25, #26, #27 Merge 또는 Close 미수행

Phase 9에서 요구사항별 명령, SHA, PR, Pilot Artifact 경로와 결과를 기록한다. Human Editorial Approval, `production-finalize`, `register`, PR Merge는 의도적으로 수행하지 않는다.

## Correction Review — 2026-09-02

### 독립 검토 기준과 증거 상태

- 교정 기준: C-01부터 C-13까지의 독립 검토 Backlog와 기존 Goal의 기능·권한·호환성 불변식을 함께 적용한다.
- 기존 Phase 1의 multi-harm, Phase 2의 Screenplay Unit, Phase 3의 State Transition 수용 증거는 `SUPERSEDED_BY_CORRECTION_REVIEW`다. 역사 기록은 삭제하지 않고 교정 Commit과 새 검증 증거로 대체한다.
- Source-style 원문은 저장소나 Runtime Context에 반입하지 않으며 추상 기능 요구만 사용한다.

### 검토 Head와 교정 시작 Head

| Stack | 검토 Head | 교정 시작 실제 Head | 선조 관계 | 시작 상태 |
|---|---|---|---|---|
| Foundation PR #24 | `b24b47456003057cfebbecf9e156551cc51369f2` | `b24b47456003057cfebbecf9e156551cc51369f2` | PASS | OPEN, Python 3.11/3.14 PASS |
| Contracts PR #25 | `d12e9823e27c788762efc49f2b8b787f33c5f635` | `d12e9823e27c788762efc49f2b8b787f33c5f635` | PASS | OPEN, Remote Check Run 없음 |
| Runtime PR #26 | `f79779b747a8ae5103159657ad9bcf997328156d` | `f79779b747a8ae5103159657ad9bcf997328156d` | PASS | OPEN, Remote Check Run 없음 |
| Pilot PR #27 | `d6a56cd9d0890570f01603bd37d1f9bdaaf4a77e` | `d6a56cd9d0890570f01603bd37d1f9bdaaf4a77e` | PASS | OPEN, Remote Check Run 없음 |

Published Stack 이력은 재작성하지 않는다. PR #25를 additive commit으로 교정한 뒤 PR #26에 정상 Merge Commit으로 동기화하고, PR #26 교정 뒤 PR #27에 정상 Merge Commit으로 동기화한다.

### 재개된 결함

| ID | 교정 시작 상태 | 대상 Stack |
|---|---|---|
| C-01 LINUX_FIXTURE_PATH | OPEN | PR #27 |
| C-02 PILOT_PROJECT_ID_COLLISION | OPEN | PR #27 |
| C-03 REMOTE_CI_EVIDENCE_MISSING | OPEN | PR #25/#26/#27 |
| C-04 STATE_TRANSITION_LIFECYCLE | OPEN | PR #25/#26 |
| C-05 BROADCAST_VISIBLE_TEXT_BINDING | OPEN | PR #26 |
| C-06 SCREENPLAY_REFERENCE_INTEGRITY | OPEN | PR #25/#26 |
| C-07 FIXTURE_CONTRACT_REALISM | OPEN | PR #27 |
| C-08 MULTI_HARM_COMPOUND_COMPATIBILITY | OPEN | PR #25 |
| C-09 RUNTIME_METHOD_EXCLUSIVITY | OPEN | PR #26 |
| C-10 RECONSTRUCTION_VISIBLE_IDENTITY | OPEN | PR #25 |
| C-11 FINAL_UNIT_TEXT_PRESERVATION | OPEN | PR #26 |
| C-12 OUTPUT_PROFILE_VERSION_DECOUPLING | OPEN | PR #26 |
| C-13 HUMAN_READABLE_CAST_RELATIONSHIP | OPEN | PR #25/#26/#27 |

### 교정 시작 Baseline

- Branch/Head: `codex/reenactment-contracts-v1@d12e9823e27c788762efc49f2b8b787f33c5f635`
- 검증 시각: 2026-09-02 08:49–08:57 KST
- Ruff PASS
- strict mypy PASS, 133 source files
- pytest PASS, 350 tests collected
- package `1.6.1` sdist/wheel build PASS
- dependency audit PASS; PyPI에 없는 로컬 Package만 제외
- Runtime Doctor PASS
- Version Immutability against Foundation branch와 `origin/main` PASS
- Baseline 명령은 Canonical Project State를 변경하지 않았다. Build 산출물만 재생성됐다.

### Project ID 예약 결과

- PR #22와 PR #27이 모두 `PROJECTS/PRJ-005/**`를 변경하므로 C-02 충돌이 확인됐다.
- `PRJ-006`은 현재 Repository Project, Story Library, 열린 PR 변경 경로와 관련 원격 Stack에 존재하지 않는다. `tests/test_production_cli.py`의 임시 테스트 ID 사용은 Project 예약이 아니다.
- PR #27 교정 Pilot ID는 `PRJ-006`으로 예약한다. 기존 PRJ-005의 Hash·State·Trace를 경로 변경이나 전역 치환으로 재사용하지 않는다.

### 교정 증거 갱신 대기

- 교정 Commit, Targeted/Full local validation, exact Remote CI Run ID, 새 Pilot State와 잔여 위험은 각 Stack 교정 뒤 이 절에 추가한다.
- Human Editorial Approval, 사용자-facing `production-finalize`, Story Library `register`, PR Merge/Close는 수행하지 않는다.

### PR #25 계약 교정 결과

- 수명주기 결정: `character_state_transitions` 전체 작성을 GATE-07의 `scene.design` 뒤로 이동한다. GATE-06은 Beat/Retention만 확정하고 빈 Scene 집합을 검증하지 않는다. `scene_cards → character_state_transitions → presentation_plan` 의존 방향으로 고정해 순환을 제거한다.
- C-08: 새 구조화 피해는 Core Action과 직접 호환되는 Harm을 최소 하나 요구한다. 추가 Harm은 Core, Primary 또는 명시 Related Crime의 유한 정책 집합과 호환돼야 하며 `COMPOUND` timing을 결과로 인정하되 `COMPOUND_HARM`의 무효 timing을 거부한다. Legacy 단일 피해 Version은 유지한다.
- C-06: Fact, Clue, Crime Event, Harm, Development Function, Reveal Target, Speaker와 Presentation Segment의 현재 상위 Artifact 결속을 검사하는 순수 Unit Reference Validator를 추가했다.
- C-10: 재구성 반복은 text뿐 아니라 type, speaker와 delivery를 보존한다. 참조 변화는 `ALLOW_RECONTEXTUALIZATION`을 명시한 Binding에서만 허용한다.
- C-13: 기존 Runtime Project Artifact 1.0 Schema는 변경하지 않고 `relationships` 1.1 계약을 추가했다. Legacy 무버전 문서는 계속 허용하며 1.1 문서는 Machine `engine`과 별도 Human-readable `display_summary`를 요구한다.
- C-03 계약 부분: CI의 `pull_request` Base 제한을 제거해 Stacked PR synchronize Event가 동일 Python Matrix를 실행할 수 있게 했다.
- Targeted: 계약 교정 묶음 119 tests PASS, Ruff PASS, strict mypy PASS.
- Full local: Ruff PASS, strict mypy PASS(134 source files), pytest PASS(386 tests), package 1.6.1 build PASS, dependency audit PASS, Runtime Doctor PASS, Foundation/origin-main Version Immutability PASS.
- Test skip/xfail로 결함을 숨긴 항목: 없음.
- 검증 시각: 2026-09-02 09:04–09:07 KST. 검증은 Canonical Project State를 변경하지 않았고 Build 산출물만 재생성했다.
- 교정 Commit: `92f41c7e7cebeab17dfa0c7b3faf2a84db998d4b` (`fix: close reenactment contract review gaps`). Remote CI Run `33574035850`의 Python 3.11/3.14 Matrix가 이 SHA에서 PASS했다.

### PR #25 → PR #26 Stack 동기화 결과

- From: `codex/reenactment-contracts-v1@92f41c7e7cebeab17dfa0c7b3faf2a84db998d4b`
- Into: `codex/reenactment-runtime-v1`
- 정상 Merge Commit: `09ec5eb03b8949c31a515b05c90907f686c493c2`
- 충돌: 없음
- 누락된 하위 변경: 없음
- 동기화 직후 계약 표적 테스트 57개, Ruff, strict mypy 140 source files, build, audit, doctor와 양쪽 Version Immutability가 PASS했다.
- 동기화 직후 전체 pytest의 7개 통합 실패는 GATE-07 이전 뒤 State Machine 필수 목록, 새 Reference 결속 Fixture와 정확 출력 결속을 아직 Runtime에 통합하지 않은 교정 전 기준점이었다. 아래 PR #26 교정에서 모두 회귀 테스트로 전환해 닫았다.

### PR #26 Runtime 교정 결과

- 시작 Published Head: `f79779b747a8ae5103159657ad9bcf997328156d`
- 하위 Stack 동기화 Head: `09ec5eb03b8949c31a515b05c90907f686c493c2`
- 교정 코드 Commit: `08168c20814a668a8c3082aca8e85e8a0b583995` (`fix: enforce exact screenplay-derived output integrity`)
- C-04: `character_state_transitions`의 Task와 State Machine 필수 수명주기를 모두 GATE-07로 옮겼다. `scene.design → story.design_state_transitions → scene.compute_production_footprint/scene.design_reactions → script.compose_screenplay_units` 순서를 고정했고 Legacy Task 조건과 계획은 유지했다.
- C-05: Drama, Narration, Panel, Draft, Final과 Reenactment Export를 현재 Unit·Reaction·Presentation·Profile에서 순수 재렌더해 실제 bytes와 비교한다. Report 1.1은 여섯 출력 SHA-256을 기록하며 모든 mismatch는 Artifact, expected hash와 actual hash를 제공한다. Layer와 Final 동시 변조를 포함한 요구된 8개 mutation을 모두 실패시킨다.
- C-06: CORE Layer Renderer 전에 여섯 Unit Reference Family와 speaker/segment 결속을 검증한다. 같은 검증을 GATE-08과 GATE-09 Report 재구성에 반복하고, 여섯 Family 각각을 CORE Task와 GATE 경로에서 독립적으로 실패시켰다. Facts와 Reaction을 Report 입력 Hash 및 dependency invalidation에 포함했다.
- C-09: `WORD_COUNT_ESTIMATE`는 양의 estimate와 null measurement만, `TABLE_READ`/`RECORDED_AUDIO`는 null estimate와 양의 measurement만 허용한다. 방송 Panel Aggregate·Segment와 별도 재연극 Runtime 모두 Schema와 의미 Validator에서 같은 배타성을 적용한다. 0, stale Hash와 tolerance 경계도 별도 검증한다.
- C-11: Renderer 전체 `.rstrip()`을 제거하고 Renderer 소유 마지막 separator만 제거한다. final Unit trailing spaces, 의도적 blank line, multi-line Screen Text와 visible block hash를 보존한다.
- C-12: 새 Runtime Task의 hard-coded Profile ID/Version 조건을 제거했다. Runtime은 Task 계획 전에 Config Pin과 Registry hash/schema를 Resolver로 검증한다. 등록 1.0.0, 임시 등록 후속 1.1.0, 미등록 Version, Pin 누락, Legacy 비활성화와 미지원 계약 실패를 검증했다.
- C-13: Relationships 1.1의 `display_summary`를 Cast에 표시하고 Machine enum은 노출하지 않는다. Legacy는 이름 기반 결정론적 대체 문구를 사용하며 pipe/newline escaping과 알 수 없는 Character 참조 실패를 검증했다.
- Output Profile의 필수 Heading, Scene Heading Template, Cast 열, 특수 Unit Label, 포함/제외 Layer와 Unit Type을 Renderer와 Report가 실제로 사용한다. Profile Version만 바뀌어도 Export bytes/hash와 Report stale 검증이 달라진다.
- Report와 Editorial Schema의 변경 Version은 각각 `reenactment-export-report` 1.1과 기존 Editorial Review 1.2의 강화된 조건부 계약이다. 기존 Legacy Script Task와 Historical Project는 Profile Pin이나 새 Artifact를 요구받지 않는다.
- Human Editorial Approval, 사용자-facing `production-finalize`, Story Library `register`, PR Merge/Close는 실행하지 않았다. Canonical Project State 변경도 없었고 build 산출물만 재생성했다.

#### PR #26 검증 기록

| 명령 | Branch | Head | 시작 시각(KST) | Exit | 결과 | State 영향 |
|---|---|---|---|---:|---|---|
| `.venv/bin/python -m pytest` | `codex/reenactment-runtime-v1` | `08168c20814a668a8c3082aca8e85e8a0b583995` | 2026-09-02 09:55:41 | 0 | 454 PASS, 0 skip/xfail | 없음 |
| Renderer/Runtime/Gate/Transaction 표적 pytest 132개 | 동일 | 동일 | 2026-09-02 09:58 | 0 | 132 PASS | 없음 |
| `.venv/bin/python -m ruff check .` | 동일 | 동일 | 2026-09-02 09:58 | 0 | PASS | 없음 |
| `.venv/bin/python -m mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests` | 동일 | 동일 | 2026-09-02 09:58 | 0 | 140 source files PASS | 없음 |
| `.venv/bin/python -m build` | 동일 | 동일 | 2026-09-02 09:58 | 0 | package 1.6.1 sdist/wheel PASS | ignored build 산출물 재생성 |
| `.venv/bin/python -m pip_audit` | 동일 | 동일 | 2026-09-02 09:58 | 0 | 알려진 취약점 없음; 로컬 Package만 제외 | 없음 |
| `.venv/bin/mystery-runtime doctor` | 동일 | 동일 | 2026-09-02 09:58 | 0 | contracts/provider descriptors PASS | 없음 |
| `version_immutability --base-ref origin/codex/reenactment-contracts-v1` | 동일 | 동일 | 2026-09-02 09:58 | 0 | PASS | 없음 |
| `version_immutability --base-ref origin/main` | 동일 | 동일 | 2026-09-02 09:58 | 0 | PASS | 없음 |

- 새 mode FakeProvider GATE-00→13과 Reference egress 회귀, Gate Transaction, drift/finalize/register 차단 회귀가 포함된 전체 454개 테스트가 PASS했다. FakeProvider 결과는 코드 흐름 증거일 뿐 창작 품질 증거가 아니다.
- Test skip/xfail, Validator 완화, fallback 또는 false PASS로 결함을 숨긴 항목: 없음.
- 최종 PR #26 Head `8d1676bf4abdffc551ee61e2faa70d66b11c4682`는 Remote CI Run `33577676951`의 Python 3.11/3.14 Matrix에서 PASS했다.

### PR #27 Pilot 교정 및 재생성 결과

- 검토 Head와 실제 교정 시작 Head는 모두 `d6a56cd9d0890570f01603bd37d1f9bdaaf4a77e`였다. PR #26의 최종 교정 Head `8d1676bf4abdffc551ee61e2faa70d66b11c4682`를 정상 Merge Commit `ca69ee2031db90b2a98bc45928c74d3470df766d`으로 동기화한 뒤 작업했다.
- C-01은 Fixture Root를 `Path(__file__).parent`에서 계산하도록 고쳐 Linux Case-sensitive 경로를 사용한다. C-07은 네 Fixture를 실제 등록 Crime Enum과 구조화 Harm, 책임 주체, Human-readable Relationship으로 구성하고 Crime Contract Schema·Harm 의미·Unit Reference·Export Report 1.1까지 검증한다.
- 교정 Pilot 콘텐츠 Commit은 `c56bb60815b5af8369d77d89436101e5aa8828f2` (`feat: regenerate original crime thriller pilot`)이다. 이 Commit은 직접 사용자 지시에 따라 기존 `PROJECTS/PRJ-005/**` 추적 문서 62개를 모두 삭제하고, ID를 재사용하지 않은 `PROJECTS/PRJ-006/**` 62개를 새 Gate Transaction 결과로 추가한다.
- 과거 Phase 8과 Final Acceptance의 PRJ-005 창작 수용 증거는 `SUPERSEDED_BY_USER_REQUEST_AND_PRJ006_REGENERATION`이다. 역사 기록은 감사용으로 남기되 현재 Pilot Artifact 경로와 작품 품질의 근거로 사용하지 않는다.
- 새 Full Original Fiction Pilot `PRJ-006`, 작품명 `폐장 음악이 멈춘 7분`은 `CRIME_EVENT_THRILLER`, `MURDER`, `COMPLICIT_GROUP` 계약을 사용한다. 사망 피해와 생존 피해자의 중상, 세 행위자의 지시·공격·은폐 책임을 11개 Scene, 23개 Presentation Segment, 95개 Screenplay Unit으로 전개한다.
- 최종 Scaffold는 Production Standard 1.3.3, Channel Content 2.1.0, `SCREENPLAY_UNITS`, `REENACTMENT_CHARACTER_SCRIPT` 1.0.0, `ORIGINAL_FICTION`을 사용한다. GATE-00부터 GATE-13까지 순서대로 Commit됐고 최종 GATE-13 Transaction은 `CODEX-TASK-CF53698330E345DD`, 내부 Commit Hash는 `632366290a37121b68a0188ba170aa89f6c827558895c0feb26ade605f6caadd`다.
- 첫 생성본 Audit에서 `AUDIT_EVENT_TIME_ORDER_ERROR`와 `PROJECT_CREATED_AFTER_GATE_ERROR`를 발견했다. 오류를 성공으로 대체하지 않고 커밋 전 생성본을 보관한 뒤 실제 시각으로 `mystery-kit init`을 다시 실행하고, 승인된 산출물을 각 Task의 `allowed_writes`에만 재제출했다. 최종 Process Revision은 1, Trace는 37개이며 시간·누락 Issue가 없다.
- Project `validate`와 `audit`는 GATE-00~13 전체 PASS, Issue 0, `state_unchanged: true`, `PROCESS_CONFORMANT`를 확인했다. 전후 State Hash `46b8e397c60e26a0cc7073ac29627ab4a4118e19bb481c400cb6756a14f0199f`와 Trace Hash `1cd981f0ee577f06fa17b329cecb3c8a123d2273c03af9c8beb058ca7347535d`는 동일했다.
- 최종 State는 `EDITORIAL_REVIEW_REQUIRED`다. Artifact는 `ARTIFACT_COMPLETE`, Contract는 `CONTRACT_VALIDATED`, Process는 `PROCESS_CONFORMANT`, Human Editorial은 미승인, Production Ready는 false다.
- Canonical/Production 재연본은 byte-identical하다. Broadcast는 25분 40초와 Panel Segment 7개를 유지하고, 재연본은 Panel·Expert·Audience·내부 Marker를 제외한다. 재연 Runtime은 계획 21분, `NOT_CONFIGURED`, `measured_minutes: null`이며 Panel 근거도 `WORD_COUNT_ESTIMATE`만 사용한다.
- Story Library는 0개 항목으로 유지했다. GATE 진행 중 생긴 `EDITORIAL_PENDING` 임시 항목은 `register`가 아니며 미등록 Library 회귀 조건을 지키도록 최종 Commit에서 제외했다. Project 내부 Fingerprint·Novelty Report는 보존했다.

#### PR #27 검증 기록

| 명령 | Head | Exit | 결과 | State 영향 |
|---|---|---:|---|---|
| Source-style Fixture pytest | `c56bb60815b5af8369d77d89436101e5aa8828f2` | 0 | 10 PASS | 없음 |
| 교정 표적 pytest | 동일 | 0 | 150 PASS | 없음 |
| 전체 pytest | 동일 | 0 | 465 PASS, skip/xfail 없음 | 없음 |
| `.venv/bin/python -m ruff check .` | 동일 | 0 | PASS | 없음 |
| strict mypy | 동일 | 0 | 141 source files PASS | 없음 |
| package build | 동일 | 0 | package 1.6.1 sdist/wheel PASS | ignored build 산출물 재생성 |
| dependency audit | 동일 | 0 | 알려진 취약점 없음; 로컬 Package만 제외 | 없음 |
| Runtime Doctor | 동일 | 0 | contracts/provider descriptors PASS | 없음 |
| Version Immutability against Runtime base와 `origin/main` | 동일 | 0 | 양쪽 PASS | 없음 |
| Remote CI Run `33586151859` | 동일 | 0 | Python 3.11/3.14 PASS | 원격 검증만 수행 |

### 잔여 위험과 명시적 미수행

- 창작 품질과 범죄 스릴러 적합성의 최종 판단은 Human Editorial Review 대상이다. 기술적 Editorial Critic PASS는 Human 승인을 대신하지 않는다.
- `TABLE_READ` 또는 `RECORDED_AUDIO` 실측을 수행하지 않았다. `WORD_COUNT_ESTIMATE`를 실측으로 해석하면 안 된다.
- Human `editorial-approve`, 사용자-facing `production-finalize`, Story Library `register`, PR Merge/Close는 수행하지 않았다.
- PR #22의 `PRJ-005` 변경은 손대지 않았다. PR #27 Branch의 과거 생성본은 후속 직접 지시에 따라 삭제됐으며 Runtime Base 대비 최종 PR #27 순변경에는 `PROJECTS/PRJ-005/**`가 없다. 따라서 현재 PR Diff의 경로 충돌은 없지만 PR #22를 나중에 병합하면 삭제된 PRJ-005 문서가 다시 유입될 수 있다.
- 권장 Stack 순서는 PR #24 → 교정 PR #25 → 교정 PR #26 → 교정 PR #27이며 이 순서를 실행하지 않았다.

## Final Correction Audit — 2026-09-02

### 최종 결함 매트릭스

| ID | 최종 상태 | Stack | 닫힘 증거 |
|---|---|---|---|
| C-01 LINUX_FIXTURE_PATH | CLOSED | PR #27 | Fixture Root를 `Path(__file__).parent`에서 계산하고 Linux 원격 CI에서 10개 Source-style Fixture를 수집·통과했다. |
| C-02 PILOT_PROJECT_ID_COLLISION | CLOSED | PR #27 | PRJ-005를 재사용하지 않고 Repository·Story Library·열린 Stack에 없던 `PRJ-006`을 새 Gate Transaction으로 생성했다. Runtime Base 대비 PR #27의 Project 순변경은 PRJ-006 62개 추가뿐이다. |
| C-03 REMOTE_CI_EVIDENCE_MISSING | CLOSED | PR #25/#26/#27 | 최종 Head별 Run `33574035850`, `33577676951`, `33586491903`의 Python 3.11/3.14가 모두 PASS했다. |
| C-04 STATE_TRANSITION_LIFECYCLE | CLOSED | PR #25/#26 | `scene_cards → character_state_transitions → presentation_plan`으로 고정하고 작성·필수화·검증을 GATE-07로 일치시켰다. |
| C-05 BROADCAST_VISIBLE_TEXT_BINDING | CLOSED | PR #26 | 여섯 파생 출력의 현재 입력 재렌더·byte/hash 비교와 Visible/Trace/Layer/Final 독립 Mutation 실패를 고정했다. |
| C-06 SCREENPLAY_REFERENCE_INTEGRITY | CLOSED | PR #25/#26 | Fact·Clue·Event·Harm·Development Function·Reveal Target 및 Speaker/Segment 결속을 순수 Validator, CORE, GATE-08/09에서 독립 검증한다. |
| C-07 FIXTURE_CONTRACT_REALISM | CLOSED | PR #27 | 네 Fixture가 등록 Enum `DOMESTIC_VIOLENCE`, `MURDER`, `STALKING`, `CONFINEMENT`와 실제 Harm/책임/관계 계약을 사용한다. |
| C-08 MULTI_HARM_COMPOUND_COMPATIBILITY | CLOSED | PR #25 | Core/Primary/Related Crime의 유한 Harm 정책과 최소 Core 호환 Harm을 강제하고 Legacy `COMPOUND`를 유지하되 잘못된 `COMPOUND_HARM` timing을 거부한다. |
| C-09 RUNTIME_METHOD_EXCLUSIVITY | CLOSED | PR #26 | `WORD_COUNT_ESTIMATE`와 `TABLE_READ`/`RECORDED_AUDIO`의 estimate/measurement 배타성, 양수, stale hash와 tolerance 경계를 검증한다. |
| C-10 RECONSTRUCTION_VISIBLE_IDENTITY | CLOSED | PR #25 | 반복 Unit의 text/type/speaker/delivery/reference 동일성을 강제하고 명시 Recontextualization Policy만 reference 변화를 허용한다. |
| C-11 FINAL_UNIT_TEXT_PRESERVATION | CLOSED | PR #26 | Renderer 소유 separator만 제거하고 Unit의 trailing spaces, blank line, multiline text를 byte 단위로 보존한다. |
| C-12 OUTPUT_PROFILE_VERSION_DECOUPLING | CLOSED | PR #26 | Runtime Task의 hard-coded Profile ID/Version을 제거하고 Pin/Registry/Schema/Hash Resolver로 등록 Version을 활성화한다. |
| C-13 HUMAN_READABLE_CAST_RELATIONSHIP | CLOSED | PR #25/#26/#27 | Relationships 1.1의 `display_summary`를 결정론적으로 렌더하고 Legacy 요약·escaping·잘못된 Character 참조를 검증한다. |

모든 결함은 회귀 테스트를 추가하거나 기존 테스트를 강화해 닫았고 skip/xfail, Validator 완화, fallback 또는 false PASS를 사용하지 않았다.

### 각 Stack 최종 Head 로컬 재검증

| PR | 검증 Head | 시각(KST) | 전체 pytest | Ruff | strict mypy | build/audit/doctor/immutability |
|---|---|---|---|---|---|---|
| #25 | `92f41c7e7cebeab17dfa0c7b3faf2a84db998d4b` | 13:26:56–13:29:03 | 386 PASS | PASS | 134 files PASS | 모두 PASS |
| #26 | `8d1676bf4abdffc551ee61e2faa70d66b11c4682` | 13:29:15–13:31:30 | 454 PASS | PASS | 140 files PASS | 모두 PASS |
| #27 | `0bd5b7a3ad84ad5d69606b1b79d65f718abebca9` | 13:31:45–13:34:04 | 465 PASS | PASS | 141 files PASS | 모두 PASS |

- #27은 `pytest --collect-only -q`에서 465개를 수집했고 Source-style Fixture 10개가 별도로 PASS했다.
- #27의 Project `validate`와 `audit`는 GATE-00~13 PASS, Issue 0, Trace 37개, `state_unchanged: true`였다.
- #27의 Canonical/Production 재연본은 byte-identical이고 State/Trace SHA-256은 검증 전후 각각 `46b8e397c60e26a0cc7073ac29627ab4a4118e19bb481c400cb6756a14f0199f`, `1cd981f0ee577f06fa17b329cecb3c8a123d2273c03af9c8beb058ca7347535d`로 동일했다.
- 세 Head 모두 package `1.6.1` sdist/wheel, dependency audit, Runtime Doctor, `origin/main`과 직전 Stack Base 대비 Registered Version Immutability가 PASS했다.
- 이 원장-only 감사 Commit 뒤 PR #27 최종 Head 검증과 원격 CI를 다시 실행하고, 자기 SHA를 원장에 재기록하는 순환을 피하기 위해 그 exact Head/Run은 PR #27 본문에 기록한다.

### 최종 Stack·권한·상태 확인

- 선조 관계는 `origin/main → PR #24@b24b474 → PR #25@92f41c7 → PR #26@8d1676b → PR #27`이며 모든 검사가 exit 0이다. Published Stack은 additive/normal merge commit만 사용했고 History Rewrite나 Force Push가 없다.
- PR #25/#26/#27 본문은 목적·범위, 실제 수정, 하위 호환성, exact Head/CI, 알려진 한계와 의도적 제외를 포함한다.
- PR #27 Runtime Base 대비 최종 순변경에는 PRJ-005 경로가 없고 PRJ-006 62개만 추가된다.
- PRJ-006은 GATE-13 `EDITORIAL_REVIEW_REQUIRED`, `ARTIFACT_COMPLETE`, `CONTRACT_VALIDATED`, `PROCESS_CONFORMANT`다. Human Editorial은 미승인이고 Production Ready는 false이며 Story Library 항목은 0개다.
- `editorial-approve`, 사용자-facing `production-finalize`, `register`, PR Merge/Close는 수행하지 않았다.

## Broadcast Readable Canonical Chain Correction — 2026-09-02

### 입력과 불변 경계

- Canonical Chain 교정 시작 시 Local·Remote Head는 모두 `63d4cec81fd7cea6f204ddd1936adfaada5dc229`였고, 이 Commit은 최신 `origin/codex/reenactment-pilot-v1`의 선조였다.
- `거머리_인물별_대사_스크립트.md`와 `죽음의_동창회_인물별_대사_스크립트.md`는 저장소 밖에서 제목·등장인물 표·순서화된 장면·상황 설명·실제 이름 발화라는 추상 형식 Coverage만 확인했다. Reference 원문과 고유 인물·대사·장소·범죄·반전은 Project나 Runtime Context에 복제하지 않았다.
- 기존 `final_script.md`는 기계형 Broadcast Master다. Marker 문법, `screenplay_renderers.py`와 Master bytes는 변경하지 않는다. 보호 Master SHA-256은 `df995516ec1337de81b5b4aebc74cbd2af3c75a7a44393d851e768517749e602`다.

### 구현과 Coverage

- `broadcast_readable_renderer.py`는 동일 Project의 Canonical Screenplay Unit, Character, Panel Cast, Reaction Segment, Presentation Plan과 Versioned `BROADCAST_READABLE_SCRIPT` Profile만 입력받는 순수 결정론적 Renderer다. Profile이 제목·표·Context·Unit·Panel Template을 실제로 결정하고 11개 장면의 Source-style Context, 95개 Unit, 실제 Character 이름, 7개 Panel 구간과 Canonical Panel Turn 14개를 방송 순서대로 표시한다.
- GATE-08 `script.render_broadcast_readable`이 `07_SCRIPT/broadcast_readable_script.md`를 만들고, GATE-09 `continuity.validate_broadcast_readable`이 Production Config, 다섯 Canonical 입력, Profile 문서·Registry 파일 Hash, 출력 Hash·Source-style Coverage를 `08_QA/broadcast_readable_report.json`에 결속한다. Validator는 현재 입력에서 Script와 Report를 모두 재구성해 Profile Pin 변경, stale 또는 위조를 거부한다.
- Dependency Graph는 Screenplay Unit 변경을 Readable Source, QA Report, 통합 Validation, Production Copy와 Editorial Review까지 전파한다. GATE-13 `production.package_broadcast_readable`은 PASS Report가 가리키는 Source bytes만 `09_PRODUCTION/broadcast_readable_script.md`로 복사한다. 세 Artifact는 Contract, Agent 권한, Runtime Task, Project State Hash, Gate Transaction과 Process Trace에 등록하며 Gate 밖 직접 쓰기 CLI는 제공하지 않는다.

### 검증과 상태

- Broadcast Readable Output Profile Pin이 Candidate Eligibility와 Approval에도 결속되므로 PRJ-006을 Variation Designer의 GATE-01로 반환해 Process Revision 4를 열고 GATE-01부터 GATE-13까지 순서대로 Commit했다. 새 Task Trace는 GATE-08 `script.render_broadcast_readable`, GATE-09 `continuity.validate_broadcast_readable`, GATE-13 `production.package_broadcast_readable`을 포함하며 전체 Process Trace는 108개다.
- Readable Source와 Production Copy의 byte SHA-256은 모두 `a823e34f69132c857d6eea6a93b9842dd5f40add50edfe6409b1a2f6c4fbe2fa`이고, QA Report 파일 SHA-256은 `713b1a1e733fabfd248863f41d5c804e57d3a57ce4e3ee889beccd2f4fd210c1`다. 세 State Entry는 모두 `CLEAN`이며 QA Report는 Production Config, 다섯 Canonical JSON, Canonical Profile 문서와 Registry Profile 파일 Hash, Source bytes Hash, Source-style Evidence와 11 Scene·95 Unit·7 Reaction Segment·14 Panel Turn Coverage를 보존한다.
- 저장소 소스 기준 `validate`와 `audit`는 GATE-00~13 PASS, Issue 0, `state_unchanged: true`, Process Conformant다. 검증 전후 Project State와 Process Trace SHA-256은 각각 `76e020098e3d29680291be698834140417004a9187d4bdc27d500987150e348b`, `c70255bdbce8335f6a77d1bad81374e99e1d6e17ad29fd4d9542b3b7c4df388b`로 동일했다. 전체 pytest, Ruff, strict mypy 144개 파일, package build, dependency audit와 Runtime Doctor가 통과했다.
- 최종 상태는 `EDITORIAL_REVIEW_REQUIRED`이고 Human Editorial은 미승인, Production Ready는 false, Story Library 항목은 0개다. 사용자-facing `production-finalize`, Story Library `register`, PR Merge/Close는 수행하지 않는다. 최종 Commit SHA와 정확한 Head의 Python 3.11/3.14 원격 CI 증거는 PR 본문에 기록한다.

## Broadcast Readable v2 Final Correction

### Phase 0 기준선

- 2026-09-02에 Fetch한 `origin/codex/broadcast-readable-profile-v1`의 Head는 `a6b43591639239f2bc926268535430aa76358525`이며, Goal 기준 SHA와 정확히 같다. Branch A `codex/broadcast-readable-v2-contracts`는 이 Remote Head에서 분기했고 PR #28 Branch를 직접 수정하지 않는다.
- 고정된 `BROADCAST_READABLE_SCRIPT@1.0.0` 파일은 `CHANNELS/mystery_main/output_profiles/broadcast-readable-script/1.0.0.json`, SHA-256은 `7c8b59c96af7a65f59faf7f4ed68d2ad7ffba10ef59fbbbb3189dd1445943667`이다. Registry의 1.0.0 Entry는 같은 경로와 Hash를 가진다. 두 값과 v1 Schema·Renderer·Report 의미는 변경하지 않는다.
- PRJ-006 기준 Hash는 `screenplay_units` `c478aff60b0af9adba79e20dcc01622dd282460e93e0037e9f70e078910163ad`, `drama_script` `da3e02203c8e7b6a480fb90d607501f3a2e850e4f3e3c0c0ac35efc6f98bfe1b`, `narration_script` `5c532952b199d06a1bc7582d7dbd0b7453a55a3eba63977b89e8088ad4b2acc5`, `panel_reaction_script` `46f2b81d521d0ff60cf0af41effb6ba0484320349128397029eff099fc72be86`, `draft_v01` `df995516ec1337de81b5b4aebc74cbd2af3c75a7a44393d851e768517749e602`, Machine `final_script` `df995516ec1337de81b5b4aebc74cbd2af3c75a7a44393d851e768517749e602`, `reenactment_character_script` `0a97c9702158a3f45b6613016fea5b9d67f85e6f3316f88ea9bd80b7bd9e5618`, v1 `broadcast_readable_script` `a823e34f69132c857d6eea6a93b9842dd5f40add50edfe6409b1a2f6c4fbe2fa`다.
- 변경 전 기준선은 Ruff, strict mypy 144개 파일, 전체 pytest, package 1.6.1 build, dependency audit, Runtime Doctor와 `origin/main`·PR #28 Head 대비 Registered Version Immutability를 모두 통과했다.

### Version·Activation·Dispatch 결정

- v1은 기존 공용 Profile Schema와 기존 Renderer/Report 경로를 그대로 사용한다. v2만 `BROADCAST_READABLE_SCRIPT@2.0.0`, 전용 Profile Schema 2.0.0, Report Schema 2.0.0과 `broadcast-readable-config@1.0.0`을 사용하며 Resolver는 선택된 Version으로 Schema와 Renderer를 명시적으로 Dispatch한다.
- v2는 optional `00_PROJECT/broadcast_readable_config.json`의 `enabled=true`로만 활성화한다. Config가 없고 기존 Production Config v1 Pin Pair가 있으면 v1 Compatibility 경로, 둘 다 없거나 Config가 disabled면 비활성, 둘 다 있으면 v2 Config가 우선한다.
- Branch A는 Profile·Schema·Registry·Config·Artifact·Requirement·Dependency·Report·Production Manifest 계약만 포함한다. Branch B `codex/broadcast-readable-v2-runtime`은 Branch A의 공개 Head에서 분기해 Renderer, 독립 QA Mapping, Gate, Fixture와 PRJ-006 Backfill을 포함한다.
- Readable Config 변경의 목표 무효화 집합은 `broadcast_readable_script`, `broadcast_readable_report`, `production_broadcast_readable_script`, Production Manifest의 Readable Deliverable Evidence와 `editorial_review`뿐이다. Story, Character, Relationship, Screenplay, Machine Master와 Reenactment Chain은 Readable 전용 Edge 때문에 무효화하지 않는다.

### BR-02~BR-14 보정 원장

| ID | 현재 상태 | 계약/구현 증거 | 독립 Negative Test | Gate/CI 증거 |
|---|---|---|---|---|
| BR-02 | CLOSED | `2.0.0.json`, 전용 Profile/Report Schema, `output_profiles.py`와 Renderer·전체 Pipeline Version Dispatch | `test_v1_and_v2_profiles_use_distinct_valid_schemas`, `test_v2_registry_entry_mutation_is_detected`, `test_runtime_v1_dispatch_keeps_registered_output_bytes` | Branch A/B 최종 Head Python 3.11·3.14 Required CI |
| BR-03 | CLOSED | v2 Renderer·Report·Runtime Task·Dependency가 `relationships`를 읽고 document/file hash를 결속 | `test_unknown_relationship_character_fails`, `test_required_relationship_display_summary_missing_fails`, `test_character_or_relationship_text_mutation_fails` | Revision 5 GATE-08·09·13 Trace의 `relationships` Hash + 최종 Head CI |
| BR-04 | CLOSED | 전역 마지막 Scene Segment 뒤에만 의미 있는 Retrospective를 배치하고 빈 값은 생략 | `test_retrospective_occurs_after_last_scene_segment_and_empty_is_omitted`, `test_retrospective_mutations_fail` | PRJ-006 Report expected/actual 8건 완전 Mapping + 최종 Head CI |
| BR-05 | CLOSED | 제목·정리 기준·등장인물·패널·방송 대본 Heading, 3열 인물 표, Scene 시작 Context 두 개와 Unit Type Label을 실제 Markdown에 고정 | `test_v2_source_style_structure_relationships_and_exact_text`, `test_all_character_authored_special_unit_labels_preserve_text`, context/unit mutation parametrization | Revision 5 GATE-08 Script hash + 최종 Head CI |
| BR-06 | CLOSED | 독립 `broadcast_readable_v2.py`가 Actual Markdown byte range와 Scene·Segment·Unit·Relationship·Panel Turn Mapping을 재계산 | mapping 삭제·중복·순서·text/hash·saved report stale mutation 전체 | Revision 5 GATE-09 Report `NEEDS_REVIEW`, issue 0 + 최종 Head CI |
| BR-07 | CLOSED | ID Prefix Family, HTML Comment, Original Fiction 불확실성 Marker의 visible-output scan | `test_each_forbidden_id_prefix_in_visible_output_fails`, `test_each_html_comment_token_in_visible_output_fails`, `test_original_fiction_uncertainty_marker_fails` | PRJ-006 visibility scan 세 배열 0건 + 최종 Head CI |
| BR-08 | CLOSED | Presentation Plan을 전역 1회 순회하고 Scene 재진입은 Continuation Heading으로 보존 | `test_global_reentry_order_context_once_and_continuation_heading`, `test_global_segment_order_mutation_fails`, `test_scene_reentry_heading_reorder_fails` | PRJ-006 GATE-08·09 Mapping Trace + 최종 Head CI |
| BR-09 | CLOSED | strict optional Config Opt-in, disabled 우선, v1 Pin fallback과 알 수 없는 Version fail-closed | `test_runtime_conditions_keep_v1_v2_and_inactive_paths_distinct`, `test_disabled_v2_config_overrides_existing_v1_pins`, partial/unknown pin tests | Revision 5 Trace의 Config·Profile file hash + 최종 Head CI |
| BR-10 | CLOSED | Manifest 1.1 Readable Deliverable가 Production Copy bytes, Report hash와 Profile Pin을 결속 | `test_manifest_copy_or_report_hash_mutation_fails`, `test_source_report_hash_mismatch_fails`, legacy Manifest 회귀 | Revision 5 GATE-13 Manifest/Copy Trace + 최종 Head CI |
| BR-11 | CLOSED | `source_style_features.json`의 독립 Original Fiction R1/R2가 재진입·회고·Flashback·Message·관계·Panel 기능을 검증하며 Raw Reference를 포함하지 않음 | `test_r1_context_and_retrospective_negative_mutations_fail`, `test_r2_relationship_panel_and_unsupported_negative_mutations_fail`, distinct/master-external 검사 | 두 Fixture issue 0 + PRJ-006 Original Fiction Pilot + 최종 Head CI |
| BR-12 | CLOSED | Renderer와 Report가 `EXPERT_ANALYSIS`, `AUDIENCE_INTERACTION`, unknown Segment를 fallback 없이 거부 | `test_unsupported_segment_type_fails_closed`, `test_unsupported_segment_type_is_reported_without_fallback`, R2 unsupported mutation | PRJ-006 `unsupported_segment_types=[]` + 최종 Head CI |
| BR-13 | CLOSED | v2 Report Enum은 `NEEDS_REVIEW|MISSING|FAIL`뿐이고 issue-free 결과도 Human PASS를 선언하지 않음 | `test_v2_issue_free_report_requires_needs_review`, `test_v2_pass_report_is_rejected_before_production_copy` | PRJ-006 `NEEDS_REVIEW`, issue 0, State `EDITORIAL_REVIEW_REQUIRED` + 최종 Head CI |
| BR-14 | CLOSED | Config Artifact의 optional/conditional Edge가 Readable Script·Report·Production Copy·Manifest·Editorial만 무효화 | `test_readable_config_change_invalidates_exact_readable_chain`, requiredness/disabled contract tests | Revision 5 GATE-08~13 순차 재생성, Machine/Reenactment 기준 Hash 불변 + 최종 Head CI |

원장은 구현·테스트·Gate Trace·정확한 원격 CI를 대체하지 않는다. 각 행은 네 증거가 모두 확보된 뒤에만 `CLOSED`로 변경한다.

### v2 Full Pilot 수용 증거

- PRJ-006에 `broadcast-readable-config@1.0.0`을 활성화하고 `script_writer`의 GATE-08로 반환해 Process Revision 5에서 GATE-08, 09, 10, 11, 12, 13을 순서대로 새 Gate Transaction으로 Commit했다. 열린 Transaction은 0개이며 Trace는 127개다.
- v2 Canonical Readable과 Production Copy의 byte SHA-256은 모두 `5a901b14502a69bc38f7906dcfc816c383d74501f13c09f2271be94b2bf75d41`이다. Report 파일 SHA-256은 `4ffeeb983fc7ad33b78f14090646fcee7f2c7794e55ec3b58a491c473d3b363a`, Production Manifest 1.1 파일 SHA-256은 `aa3a277f9043c5b949881681cf28661d1b726ab247de4627724fe0438d765fb8`이다.
- v2 Report는 `NEEDS_REVIEW`, issue 0, Expected/Actual byte-identical, Retrospective 8/8, 금지 Prefix·HTML·불확실성 Marker 0건, unsupported Segment 0건이다. GATE-13 Manifest는 Readable Copy SHA, Report canonical document SHA와 `BROADCAST_READABLE_SCRIPT@2.0.0`을 결속한다.
- GATE-08·09·13 Task Trace는 Config raw SHA-256 `5d261391b973cdf8bbad0c1ef1020b1bf53b8656656edd764bfbe022a17b0803`과 v2 Profile file SHA-256 `d156c49f31a0ecee4563c7eb6347ff5973325a918eb1fae3281955a70ec07284`을 기록한다.
- `screenplay_units`, Drama, Narration, Panel, Draft/Final Machine Master와 Reenactment 기준 Hash는 Phase 0과 동일하다. 등록된 v1 Profile 파일 SHA-256 `7c8b59c96af7a65f59faf7f4ed68d2ad7ffba10ef59fbbbb3189dd1445943667`과 v1 Renderer 기준 출력 SHA-256 `a823e34f69132c857d6eea6a93b9842dd5f40add50edfe6409b1a2f6c4fbe2fa`도 유지된다.
- 저장소 소스 기준 `validate`와 `audit`는 GATE-00~13 PASS, issue 0, `state_unchanged: true`다. 검증 전후 Project State와 Process Trace SHA-256은 각각 `86634791f557dc0335314fe8f5a985e736e5bf9e70c23524d6c1f9dd12ade5cb`, `e20f90f334ed4db1cb9e9aa66eb048a0199c7374d547174e0a526897653a5476`로 동일했다.
- 최종 상태는 GATE-13 `EDITORIAL_REVIEW_REQUIRED`, `ARTIFACT_COMPLETE`, `CONTRACT_VALIDATED`, `PROCESS_CONFORMANT`이다. Human Editorial은 미승인, Production Ready는 false, Story Library 항목은 0개다. 사용자-facing `production-finalize`, `register`, PR Merge/Close는 실행하지 않는다.
- Branch A의 공개 Head는 `bc4aeb5d2867d17c34d0afb0f63c9cc9e6a2ce91`이다. Branch A와 Branch B의 최종 Commit SHA, PR 번호, 정확한 Head의 Python 3.11/3.14 Required CI Run은 각 PR 본문에 기록한다.

## Broadcast Readable v2 BR-15~BR-18 Closure

### Source와 실행 경계

- Source Commit과 고정 기준 Ref는 `ef7df444b62ecafc86470ecfa17603d5debce6ef`, `refs/codex/closure-baseline`이다. 검증 계보는 `origin/main` → PR #28 → PR #29 → PR #30 → `codex/broadcast-readable-v2-closure`다.
- PRJ-006의 실제 Config 파일이 존재하지만 State가 MISSING/null인 상태와 저장된 Audit의 잘못된 PASS를 BR-15 기준 실패로 재현했다. 전역 occurrence Mapping, R1/R2 Timing·재구성 불일치, v2+Footprint-off Manifest Requiredness도 독립 Fixture로 재현했다.
- 상세 Phase 결과, 함수·계약, Transaction ID, 해시, 전체 명령은 저장소 루트 `BR15_BR18_Closure_Report.md`에 단일 기록한다. 정확한 Acceptance Head와 Python 3.11/3.14 CI Run/Job ID는 Head 순환을 피하기 위해 Closure PR 본문에 기록한다.

### Closure 원장

| ID | 구현·계약 | Positive/Negative 증거 | 실제 Gate 증거 | 상태 |
|---|---|---|---|---|
| BR-15 | `config_admission.py`, CLI, Config State/Audit/Gate 결속, Journal Recovery | Admission/No-op과 Schema·Project·Profile·경로·Lock·Stale·쓰기 경계·Recovery·Drift Test | `CONFIG-ADMISSION-0ED93C4B20894E83`, Revision 6 GATE-08~13 | CLOSED |
| BR-16 | Presentation 순서의 Segment-bounded cursor와 UTF-8 range | A→B→A, 반복 Unit/Turn, Prefix·다중 행 Oracle, offset/occurrence/membership 변조 | PRJ-006 11 Scene·23 Segment·95 Unit·7 관계·14 Turn, issue 0 | CLOSED |
| BR-17 | R1/R2 누적 Timing, Reaction/Scene/재구성 결속, Fixture별 Master | R1/R2 Schema·Presentation·GATE Transaction과 의미 Mutation | 두 Fixture GATE-04~09 COMMITTED | CLOSED |
| BR-18 | 공통 Manifest Requiredness와 Footprint-free Manifest 1.2 | 6개 Requiredness 조합, 8개 Manifest Mutation, 파일 없는 Full Integration | v2+Footprint-off GATE-00~13 COMMITTED | CLOSED |

### PRJ-006 Acceptance

- 공식 Config Admission 뒤 Config State와 실제 파일 Hash는 `5d261391b973cdf8bbad0c1ef1020b1bf53b8656656edd764bfbe022a17b0803`으로 CLEAN 결속됐다. Readable Script, Report, Production Copy, Manifest, Editorial만 DIRTY가 됐고 보호 Story·Screenplay·Machine Master·Reenactment·제작 문서는 변하지 않았다.
- Revision 6은 GATE-08, 09, 10, 11, 12, 13을 순서대로 Commit했다. 과거 LLM 결과는 현재 입력·출력·원래 Trace가 모두 맞을 때만 `VALIDATED_REUSE`로 기록했고 새 LLM 실행으로 가장하지 않았다.
- 최종 Readable과 Production Copy는 SHA-256 `5a901b14502a69bc38f7906dcfc816c383d74501f13c09f2271be94b2bf75d41`로 byte-identical하다. v2 Report SHA-256은 `4ffeeb983fc7ad33b78f14090646fcee7f2c7794e55ec3b58a491c473d3b363a`, 결과는 `NEEDS_REVIEW`, issue 0이다.
- 최종 State는 GATE-13 `EDITORIAL_REVIEW_REQUIRED`, Artifact/Contract/Process는 COMPLETE/VALIDATED/CONFORMANT, Human Editorial은 미승인, Production Ready는 false다.
- `validate`와 `audit`는 GATE-00~13 PASS, issue 0, State 불변이다. 전체 검증은 Ruff PASS, strict mypy PASS(153 source files), pytest PASS(652 tests), package 1.6.1 build PASS, 외부 의존성 audit PASS, Runtime Doctor PASS, `origin/main`과 고정 기준 Ref 대비 Version Immutability PASS다.
- Novelty Index의 전후 SHA-256은 `95a24dd2c3373765a24d21238cfd843befb80f539cf63d78ff1822c1c30c01ee`이며 `entries=[]`다. Human `editorial-approve`, 사용자용 `production-finalize`, Story Library `register`, PR Merge/Close는 실행하지 않았다.

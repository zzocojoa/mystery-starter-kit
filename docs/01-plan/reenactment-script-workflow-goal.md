# 소스형 재연극 인물별 스크립트 Workflow Goal Ledger

## Foundation

- 검증 시각: 2026-09-01 (Asia/Seoul)
- Foundation PR: `#24 feat: align Channel DNA 2.1 with explicit interpersonal crime`
- Foundation branch: `origin/codex/channel-explicit-crime-alignment`
- 예상·실제 Foundation SHA: `b24b47456003057cfebbecf9e156551cc51369f2`
- 선조 관계: 실제 원격 HEAD가 예상 SHA와 동일하며 `origin/main`의 후손이다.
- PR 상태: `OPEN`, `CLEAN`, 미병합
- 현재 Stack branch: `codex/reenactment-contracts-v1`
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
- [ ] Phase 1 — Versioned multi-harm event model
- [ ] Phase 2 — Screenplay Units와 Output Profile 계약
- [ ] Phase 3 — Clue recontextualization과 flexible state transition
- [ ] Phase 4 — Deterministic CORE renderer
- [ ] Phase 5 — Export integrity와 semantic binding
- [ ] Phase 6 — Runtime Task, Agent, Gate, dependency 통합
- [ ] Phase 7 — 재연극 runtime 계획·측정 분리
- [ ] Phase 8 — 네 Source-style feature fixture와 Full Original Pilot
- [ ] Phase 9 — 최종 문서·수용 증거·Stacked PR

현재 Phase: `0`

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
| 0 | `codex/reenactment-contracts-v1` | `docs: establish reenactment workflow goal baseline` | 현재 Commit 예정 |
| 1 | `codex/reenactment-contracts-v1` | `feat: add versioned multi-harm crime contracts` | 대기 |
| 2 | `codex/reenactment-contracts-v1` | `feat: add screenplay units and reenactment output profile contracts` | 대기 |
| 3 | `codex/reenactment-contracts-v1` | `feat: model clue recontextualization and flexible state transitions` | 대기 |
| 4–7 | `codex/reenactment-runtime-v1` | Phase별 Commit | 대기 |
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

- Runtime condition DSL은 현재 capability/source/artifact 조건 중심이므로 config equality 조건을 Versioned schema와 함께 확장해야 한다.
- 기존 Broadcast marker parser와 새 Unit-derived evidence가 공존해야 하므로 mode별 단일 진입점을 명확히 분리해야 한다.
- Package metadata에 Standard version `1.3.3`이 보이는 기존 build metadata 경로를 조사해 사용자 문서에서 Package `1.6.1`과 혼동되지 않게 해야 한다.
- Cross-Python byte determinism은 CI matrix 결과를 최종 증거로 사용한다.
- 대사의 자연스러움·캐릭터 음성·반전 설득력은 결정론적 PASS로 위장하지 않고 Pilot Editorial evidence의 `NEEDS_REVIEW`로 남긴다.

## Final Acceptance Evidence

Phase 9에서 요구사항별 명령, SHA, PR, Pilot Artifact 경로와 결과를 기록한다. Human Editorial Approval, `production-finalize`, `register`, PR Merge는 의도적으로 수행하지 않는다.

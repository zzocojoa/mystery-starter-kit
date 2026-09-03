# GOAL COMPLETION REPORT — Broadcast Readable v2 P1 Final Closure

## 1. Foundation and ancestry verification

- 기준 PR: `#31`, branch `origin/codex/broadcast-readable-v2-closure`
- 기준 SHA: `381c91a92cf5c3368d47b7f0b417b0435f20e8fa`
- 작업 branch: `codex/broadcast-readable-v2-final-closure`
- 기준 SHA는 작업 branch의 선조이고 `origin/main`도 기준 SHA의 선조다.
- PR #31은 작업 시작 시 `OPEN`, `CLEAN`, 미병합이었다. PR #28~#31 branch와 base는 수정하지 않았다.
- 구현 전 baseline: Ruff PASS, strict mypy 153 files PASS, pytest 654 PASS, package 1.6.1 build PASS, dependency audit PASS, Runtime Doctor PASS, registered-version immutability PASS.

## 2. Final branch and commit list

| Commit | 내용 |
|---|---|
| `df1c911` | P1-1~P1-3 경계 실패 재현과 보호 Manifest 기록 |
| `56986ec` | Parsed Segment Owner에 Readable Mapping과 byte range 결속 |
| `b2ed8ba` | R1/R2를 독립 정적 Canonical Source Bundle로 교체 |
| `768a0d7` | Audit Snapshot, Config 삭제 이력, Revision-trigger reuse 경계 결속 |
| `363b5ed` | R1 A→B→A의 최초 Heading 1회·재진입 Heading 1회 oracle 고정 |
| `2b83e3f` | PRJ-006 고유 Token과 미등록 Clue 주입 Negative 고정 |

이 보고서를 포함하는 최종 Commit SHA와 exact-head CI Run/Job ID는 순환적인 문서 Commit을 피하기 위해 PR 본문에 기록한다.

## 3. Protected asset hash manifest

기준 SHA와 최종 소스 Head 사이에서 아래 경로의 Git diff는 0이다.

```text
CHANNELS/mystery_main/output_profiles/broadcast-readable-script/1.0.0.json
CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json
CHANNELS/mystery_main/output_profiles/registry.json
PROJECTS/PRJ-006/07_SCRIPT/**
PROJECTS/PRJ-006/09_PRODUCTION/**
STORY_LIBRARY/**
```

| 보호 자산 | 기준·최종 SHA-256 |
|---|---|
| Profile 1.0.0 | `7c8b59c96af7a65f59faf7f4ed68d2ad7ffba10ef59fbbbb3189dd1445943667` |
| Profile 2.0.0 | `d156c49f31a0ecee4563c7eb6347ff5973325a918eb1fae3281955a70ec07284` |
| Profile Registry | `1836f7c706db5edba70ece2ef49d2303cd769e11f8bcdd46e241eda45d398c3f` |
| `screenplay_units.json` | `c478aff60b0af9adba79e20dcc01622dd282460e93e0037e9f70e078910163ad` |
| `draft_v01.md` / `final_script.md` | `df995516ec1337de81b5b4aebc74cbd2af3c75a7a44393d851e768517749e602` |
| `drama_script.md` | `da3e02203c8e7b6a480fb90d607501f3a2e850e4f3e3c0c0ac35efc6f98bfe1b` |
| `narration_script.md` | `5c532952b199d06a1bc7582d7dbd0b7453a55a3eba63977b89e8088ad4b2acc5` |
| `panel_reaction_script.md` | `46f2b81d521d0ff60cf0af41effb6ba0484320349128397029eff099fc72be86` |
| Canonical/Production Readable | `5a901b14502a69bc38f7906dcfc816c383d74501f13c09f2271be94b2bf75d41` |
| Canonical/Production Reenactment | `0a97c9702158a3f45b6613016fea5b9d67f85e6f3316f88ea9bd80b7bd9e5618` |
| Production Edit / Subtitle | `39f2d642a0d51cb3592de24758744083bcb81ff4d3db2ad870c75d5057bca652` / `b3f0805ece7afb6612703bc852686c9c4bc9ca8ebf80ba5f901a92def6c26417` |
| Novelty Index | `95a24dd2c3373765a24d21238cfd843befb80f539cf63d78ff1822c1c30c01ee` |
| Published Fingerprints | `1c0d62446bb7507719bd0b3c9a58cd84315a421dae7e466f8f7aee3cf74dce99` |
| Story History | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

Registry의 v1/v2 entry canonical hash도 Phase 0 값 `b12bbefa02bd5d98f9dd27ac6824a71c7139049f8425af02d0b8025ea8368ef1`, `877d8f989f992b0099170250811519048c4f546434ce3d79af1283c45d6278ed`를 유지한다.

## 4. P1-1 Mapping architecture and ownership model

Readable verifier는 가시 Markdown 전체에서 같은 문자열을 다시 세지 않는다. Presentation Segment를 실제 순서로 한 번 파싱하고 Context, Retrospective, Unit, Panel Turn을 해당 Segment/Scene container가 소비한 half-open UTF-8 byte range에 결속한다.

각 Unit/Turn Mapping은 backward-compatible optional field로 `owner_type`, `owner_id`, `container_type`, `segment_id`, `scene_id`, `rendered_block_sha256`, container local order, global presentation order와 owner/container 내부 동일 Block occurrence를 기록한다. 짧은 Block이 긴 Block의 Prefix이거나 같은 text가 Cast·Context·Drama·Panel에 있어도 Parser가 확정한 Owner만 occurrence를 소유한다. 모든 Mapping range는 전역 중복 검사를 통과해야 한다.

구 저장 Report가 새 optional field를 갖지 않아도 기존 공개 계약 범위로 비교하며, 새 field가 있는 Report를 변조하면 stale 또는 duplicate-range 오류로 실패한다.

## 5. P1-1 normal and negative full-path evidence

| ID | Test | 기대·실제 결과 |
|---|---|---|
| MAP-P01 | `test_internal_blank_paragraph_prefix_maps_only_owned_units` | 내부 빈 문단 Prefix를 별도 occurrence로 세지 않음; `NEEDS_REVIEW`, issue 0 |
| MAP-P02 | `test_identical_drama_and_panel_blocks_keep_container_ownership` | 동일 이름·text도 Drama Unit과 Panel Turn의 서로 다른 range로 결속; issue 0 |
| MAP-P03 | `test_unit_text_inside_context_does_not_change_owner_count` | Context의 동일 text가 Unit count에 관여하지 않음; issue 0 |
| MAP-P04 | `test_identical_blocks_follow_a_b_a_presentation_segments`, `test_segment_cursor_has_direct_utf8_multiline_prefix_oracle` | Presentation 순서와 `[0,6)`, `[8,32)`, `[34,40)` byte oracle PASS |
| MAP-P05 | `test_prefix_overlap_extra_standalone_block_fails_global_count`, `test_unit_mutations_fail[omit/duplicate]` | 독립 추가·누락 Unit을 occurrence mismatch로 거부 |
| MAP-P06 | `test_panel_turn_mutations_fail[omit/order]`, `test_global_segment_order_mutation_fails` | Panel 누락·순서와 Segment 순서 변조를 거부 |
| MAP-P07 | `test_saved_report_mapping_mutations_fail_stale_check[duplicate_range]` | range 재사용을 `BROADCAST_READABLE_V2_DUPLICATE_BYTE_RANGE`로 거부 |

`test_prefix_overlap_passes_source_renderer_verifier_report_and_gate`는 Canonical Source → Renderer → independent verifier → Report → 실제 GATE-04~09 Transaction 전체 경로를 통과한다.

## 6. P1-2 R1/R2 independent Canonical bundle inventory

정적 파일 `tests/fixtures/broadcast_readable_v2/canonical_source_bundles.json`은 107,704 bytes이며 두 Project를 독립 소유한다.

- R1 `PRJ-901`, 「새벽 세탁실의 세 번째 종」: `CONFINEMENT`, Note/Screen Text, 반복 신호, Scene A→B→A 재진입, 후행 Retrospective, Panel 배치, footprint off.
- R2 `PRJ-902`, 「겨울 연수원의 마지막 좌석」: `ASSAULT`, 결과 선제시, Flashback/Interview, Message 위협, 관계·책임 진술, Panel 교차 배치.
- 각 Bundle은 project/config/constraints/source truth/crime event/facts/characters/relationships/knowledge/timeline/clue/causal/beat/retention/state transition/scene/panel/reaction/presentation/screenplay Canonical 문서를 자체 보유한다.
- R1 Machine Master: `3699e468227ddee15cb45d8354add91cbdd5bdaa826a8218141f66bc9275db6c`.
- R2 Machine Master: `3ddf3a2015e8af42e9c86d4d9eaaade8f7c325453979fca3aa0313231b35e345`.
- 두 Master는 서로 다르고 PRJ-006 Master와도 다르다. Raw Reference나 다른 Fixture/PRJ-006 고유 Token을 포함하지 않는다.

## 7. P1-2 Gate and footprint-off evidence

- `test_source_style_fixture_passes_real_gate_transactions[R1-91]`: R1 GATE-04~09 COMMITTED.
- `test_source_style_fixture_passes_real_gate_transactions[R2-92]`: R2 GATE-04~09 COMMITTED.
- `test_source_style_fixture_canonical_json_matches_runtime_schemas[R1/R2]`: 모든 정식 Artifact Schema PASS.
- `test_source_style_fixture_passes_production_presentation_semantics[R1/R2]`: 자체 Scene/Timeline/Fact/Clue 입력으로 GATE-07 의미 검증 PASS.
- `test_full_runtime_reaches_gate_13_without_footprint_file`: R1 자체 Master, `production_footprint.json` 부재, Manifest 1.2, Readable `NEEDS_REVIEW`/issue 0, source-copy byte identity, GATE-13, Audit PASS, `EDITORIAL_REVIEW_REQUIRED`.
- `test_prj_006_story_token_injection_fails_fixture_isolation`과 `test_unknown_clue_reference_fails_fixture_integrity`: 외부 Story Token과 자체 Contract 밖 Clue 참조를 실패시킴.

## 8. P1-3 Audit snapshot and deletion-history evidence

`audit_project()`는 시작과 종료에 동일 범위의 SHA-256 token을 계산한다. 범위는 Project State, Change Log, Process Trace, Readable Config의 존재/bytes, Dependency Graph의 모든 Canonical Artifact path/bytes, Gate Task Record와 recoverable Transaction 상태다. 진단 출력인 `audit_report.json`은 자기 변경을 피하도록 Snapshot 입력에서 제외된다.

Token이 다르면 `AUDIT_SNAPSHOT_CHANGED`, `state_unchanged=false`, `snapshot_consistent=false`, `result=FAIL`이다. Audit는 State, Config, Trace 또는 Canonical Artifact를 복구·Backfill하지 않는다.

- Admission Commit hook: `test_audit_fails_closed_when_config_admission_commits_mid_snapshot` PASS.
- Gate Commit hook: `test_audit_fails_closed_when_gate_commits_mid_snapshot` PASS.
- 무변동/zero-write: `test_stable_audit_measures_equal_snapshot_without_writing_canonical_bytes` PASS.
- 이력 없는 optional 부재: `test_never_admitted_optional_config_can_remain_absent` PASS.
- CLEAN file 삭제: `test_clean_config_state_rejects_deleted_canonical_file` PASS.
- 성공 Admission + MISSING/absent State + file 삭제: `test_deleted_config_after_successful_admission_is_drift[missing/absent]` PASS.
- disabled Admission 뒤 file 삭제: `test_disabled_admission_still_rejects_deleted_config_file` PASS.

## 9. P1-3 VALIDATED_REUSE revision-policy evidence

Project State와 Gate Task Record의 optional `revision_trigger`는 다음 Type을 구분한다.

```text
CONFIG_ADMISSION
OWNER_RETURN
HUMAN_REVISION_REQUEST
SEMANTIC_CORRECTION
NORMAL_GATE_PROGRESS
```

Config Admission은 admission ID/actor/reason/time을 기록한다. Owner Return은 owner, target gate, 현재 Project 조건에서 실제 적용되는 LLM target task IDs, actor, reason, returned time을 기록한다. Task open은 Trigger 전체를 snapshot하고 현재 State Trigger와 byte-for-byte 의미가 다르면 재사용하지 않는다.

Config/정상 진행에서만 입력 Hash, 출력 Byte, 과거 committed Task Record와 non-reuse 실제 LLM Trace가 모두 결속될 때 재사용한다. Owner/Human/Semantic Trigger의 target task 또는 target owner task는 동일 Byte여도 `AWAITING_LLM`이다. 영향 없는 선행 Task는 기존 검증 조건을 만족하면 재사용할 수 있다. 누락 Trigger는 재사용하지 않고 unknown Type은 Schema에서 거부한다.

- `test_config_backfill_records_llm_outputs_as_validated_reuse`: 실제 과거 Trace ID/Input 결속 PASS.
- `test_config_reuse_rejects_missing_prior_actual_trace`, `...input_hash_mismatch`, `...commit_mismatch`: 세 결속 변조 모두 `AWAITING_LLM`.
- `test_owner_return_requires_target_llm_task_execution`: Script Writer target이 `AWAITING_LLM`.
- `test_other_owner_return_blocks_target_and_reuses_unaffected_upstream_task`: Scene Gate에서 영향 없는 `scene.design`은 재사용하고 Story Architect target은 `AWAITING_LLM`.
- `test_explicit_revision_trigger_blocks_target_task_reuse[HUMAN_REVISION_REQUEST/SEMANTIC_CORRECTION]`: target 재사용 차단.
- `test_missing_revision_trigger_is_not_treated_as_config_only`, `test_unknown_revision_trigger_is_rejected_by_task_record_schema`: fail-closed.
- `test_revision_trigger_task_snapshot_rejects_owner_return_tampering[reason/target_task_ids]`: Task/State Trigger 불일치로 재사용 권한 제거.

## 10. PRJ-006 validation, audit, and protected-byte comparison

최종 소스 기준 `mystery-kit validate PROJECTS/PRJ-006`와 `mystery-kit audit PROJECTS/PRJ-006`의 실제 결과는 동일하다.

```text
result = PASS
GATE-00..GATE-13 = PASS
issues = []
snapshot_start_token = e3b420efe61c03069033e19044b026d53c3697cf751130d01ebac04dcb1868cd
snapshot_end_token   = e3b420efe61c03069033e19044b026d53c3697cf751130d01ebac04dcb1868cd
state_unchanged = true
snapshot_consistent = true
current_gate = GATE-13
state = EDITORIAL_REVIEW_REQUIRED
editorial_approved = false
production_ready = false
process_revision = 6
trace_count = 146
```

Audit 전후 Project State SHA-256은 `721d6b933531d48bccfedc0bb63564be3441d198eafd44d3fc627e558888be6c`, Process Trace SHA-256은 `cb2ec78602f72f7eed6f15eff56ece7e263eb6acfa5e5fff2749eb37abbf222b`로 동일하다. 보호 Script와 Story Library Hash도 전후 및 기준 SHA와 동일하다. CLI가 만든 진단용 Audit Report timestamp 변경은 검증 후 기준 Byte로 되돌려 Project diff를 0으로 유지했다.

## 11. Local validation

| 명령 | 결과 |
|---|---|
| `.venv/bin/python -m ruff check .` | PASS |
| `.venv/bin/python -m mypy --strict VALIDATORS RUNTIME RUNTIME_ADAPTERS tests` | PASS, 153 files |
| `PYTHONPATH=. .venv/bin/python -m pytest -q` | PASS; 최종 수집 684 tests |
| `.venv/bin/python -m build` | PASS, package 1.6.1 sdist/wheel |
| `.venv/bin/python -m pip_audit` | PASS, known vulnerability 0; PyPI에 없는 local package만 제외 |
| `.venv/bin/mystery-runtime doctor` | PASS, contracts/provider descriptors |
| `version_immutability --base-ref origin/main` | PASS |
| `version_immutability --base-ref 381c91a...` | PASS |
| PRJ-006 validate / audit | PASS, Gate issue 0, Snapshot consistent |

## 12. Exact final Head CI

`.github/workflows/ci.yml`의 Python 3.11/3.14 matrix를 이 보고서가 포함된 최종 Head에 실행한다. 최종 `headSha`, Workflow Run ID, Python 3.11 Job ID/SUCCESS와 Python 3.14 Job ID/SUCCESS는 PR 본문에 기록한다. CI 근거를 문서에 다시 Commit해 Head를 바꾸지 않는다.

## 13. Closure matrix

| ID | Reproduction | Implementation | Positive Test | Negative Test | Gate/Runtime Evidence | Protected Byte Evidence | Status |
|---|---|---|---|---|---|---|---|
| P1-1 | Prefix·동일 Block·Context 오소유 재현 | Segment parser가 Owner와 고유 byte range를 직접 생성 | MAP-P01~04 | MAP-P05~07 | Prefix full GATE-04~09 | Profile/PRJ-006 diff 0 | CLOSED |
| P1-2 | R1/R2가 PRJ-006 Source에 의존하던 fixture 경계 재현 | 두 정적 Original Fiction Canonical Bundle과 자체 Master | FIX-P01/P02/P03 | FIX-N01/N02 | R1/R2 GATE-04~09, R1 footprint-off GATE-13+Audit | PRJ-006 script diff 0 | CLOSED |
| P1-3 | Mixed Snapshot PASS, 삭제 fallback, Owner reuse 재현 | Optimistic Snapshot, Admission history, Revision Trigger/target 정책 | AUD-P01/P02, REUSE-P01 | AUD-N01/N02, REUSE-N01/N02 | PRJ-006 validate/audit + 실제 Task Open/Submit | State/Trace/Script/Library audit 전후 동일 | CLOSED |

## 14. Human/editorial actions intentionally not performed

- Human `editorial-approve`: 실행하지 않음.
- 사용자-facing `production-finalize`: 실행하지 않음.
- Story Library `register`: 실행하지 않음.
- PR merge/close: 실행하지 않음.
- Output Profile 1.0.0/2.0.0 또는 Registry 수정: 없음.
- PRJ-006 Story, Screenplay, 생성 Script/Production 문서 재작성: 없음.

## 15. Remaining risks

기술 P1 결함은 닫혔다. 창작 자연스러움과 실제 방송 적합성은 계속 Human Editorial Review 대상이다. 완전히 동일한 visible byte 둘을 교환해 최종 bytes 자체가 같아지는 비관측 경우에는 Canonical presentation order의 결정론적 일대일 소유권과 range uniqueness까지만 보장한다.

## 16. Recommended stacked PR review order

권장 검토 순서는 PR #28 → #29 → #30 → #31 → 이 Final Closure PR이다. 이 순서를 실행하거나 기존 PR을 merge/close하지 않았다. 이 PR에서는 Mapping parser → 독립 R1/R2 bundle → Audit Snapshot/Config deletion → Revision-trigger reuse → protected-byte/exact-head CI 순으로 검토한다.

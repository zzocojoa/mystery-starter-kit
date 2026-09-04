# R1 DIMENSION COHERENCE COMPLETION REPORT

## 1. Repository and ancestry verification

- Repository: `zzocojoa/mystery-starter-kit`.
- 검증된 PR #33 Head: `e7bd17712dc8e3105aeedb676ec1a29b5d4524b1`. Remote fetch 후 동일 SHA, OPEN, mergedAt=null 확인.
- PR #33 Base: `codex/broadcast-readable-v2-final-closure`. 공개 Branch·Base는 수정하지 않았다.
- 작업 시작 Working Tree는 clean. 기준 Head가 후속 Branch HEAD의 선조임을 `git merge-base --is-ancestor`로 검증했다.
- 기준 코드의 전체 731 tests, Ruff, strict mypy, build, pip-audit, Doctor, Version Immutability가 PASS한 상태에서 시작했다.

## 2. Branch and commit list

작업 Branch: `codex/broadcast-readable-v2-r1-dimension-fix`.

| Commit | 목적 |
|---|---|
| `61c5fb5` | 보정 전 세 차원 실패 재현 |
| `8b4cc70` | 독립 차원 Oracle·MUT-01~05 |
| `4466877` | R1 Projection·파생 Hash 보정 및 Byte 불변 회귀 |
| `ed046b9` | GATE-00~13, 전체 Trace Input Hash, Manifest·Audit 증명 |

보고서 Commit까지 포함한 정확한 최종 Head와 원격 CI Run/Job ID는 후속 PR 본문에 결속한다. 자기 SHA를 문서에 넣기 위한 추가 Commit으로 CI 근거를 무효화하지 않는다.

## 3. Exact allowed-file diff

변경 허용·실제 변경 파일은 다음 다섯 개로 제한한다.

- `tests/fixtures/broadcast_readable_v2/canonical_source_bundles.json`
- `tests/test_broadcast_readable_v2_source_fixtures.py`
- `tests/test_broadcast_readable_v2_closure.py`
- `docs/01-plan/reenactment-script-workflow-goal.md`
- `R1_DIMENSION_COHERENCE_Closure_Report.md`

Production 경로, R2 레코드, PRJ-006, Profile, Schema, Renderer, Story Library의 변경은 없다. 후속 PR은 PR #33을 Base로 하는 별도 OPEN PR이며 Merge하지 않는다.

## 4. R1 selected-path dimensions before and after

| Dimension | 기준 Head | 보정 |
|---|---|---|
| protagonist_role | VICTIM_FAMILY | VICTIM |
| setting | LODGING | WORKPLACE |
| relationship_context | DATING_PARTNER | WORKPLACE |

승인·추천·선택 ID는 모두 `VAR-01`이다. Candidate 점수, 가중치, 평가 근거와 나머지 네 Candidate는 그대로다. 관계에서 파생되는 `trusted_domain`만 `ROMANTIC_PARTNER → EMPLOYMENT`로 재계산했다.

## 5. Cross-artifact dimension mapping

| 경로 | 검증 결과 |
|---|---|
| Candidate selection | VICTIM / WORKPLACE / WORKPLACE |
| 선택 Candidate Event Brief | relationship_context=WORKPLACE, 새 selection Hash |
| Story DNA | protagonist_role=VICTIM, setting=WORKPLACE |
| Case Input | setting=WORKPLACE, victim_ids에 CHAR-02 유지 |
| Crime Contract | protagonist_id=CHAR-02, relationship_context=WORKPLACE, 기존 actor/victim 결속 유지 |
| Character Binding | CHAR-02.role=VICTIM; VICTIM-01·PROTAGONIST-01 Slot 및 Contract role_bindings |
| Relationship REL-01 | CHAR-01→CHAR-02 engine=WORKPLACE; 전 동료·야간 근무 display_summary Byte 불변 |

Case Input Schema에는 protagonist_role 필드가 없고 additionalProperties=false다. 새 필드를 만들지 않고 기존 victim_ids와 Contract·Character 결속을 대응 Projection으로 검증한다. Setting은 Enum 직접 비교와 기존 Scene/Screenplay 의미 검사를 함께 사용한다.

원인은 서로 같은 잘못된 Candidate·Story 값을 비교하는 것만으로 실제 Character 역할과 관계의 불일치를 검출하지 못했던 것이다. Test Oracle은 Candidate에서 목표값을 추론하지 않고 독립 목표값과 실제 인물·관계를 교차 확인한다. 기존 Production Validator는 변경하지 않았다.

## 6. Mutation test matrix

| Test | 변조 | 기대·실제 결과 |
|---|---|---|
| Positive | 정상 R1 | Issue 0 |
| Baseline reproduction | 기준 Head의 R1 | 역할 2 + Setting 3 + 관계 4 = 9 Issue |
| MUT-01 | Story DNA만 VICTIM_FAMILY | FIXTURE_PROTAGONIST_ROLE_MISMATCH |
| MUT-02 | Case Input만 LODGING | FIXTURE_SETTING_MISMATCH |
| MUT-03a | Crime Contract만 DATING_PARTNER | FIXTURE_RELATIONSHIP_CONTEXT_MISMATCH |
| MUT-03b | Bound Relationship만 DATING_PARTNER | FIXTURE_RELATIONSHIP_CONTEXT_MISMATCH |
| MUT-04 | Unselected Candidate 관계 변경 | 승인 경로 Issue 0 유지 |
| MUT-05 | Candidate·DNA·Binding Hash 및 Expected를 함께 잘못 맞춤 | 실제 VICTIM Character/Case 결속에서 실패 |
| 선택 경로 보강 | 선택 Candidate/Brief 중복, 평가/승인 Brief Hash 변조 | 명시적 Selected Path/Binding Issue |

Mutation에서 “실패”란 변조 데이터가 예상 Issue로 거부되며 pytest 자체는 PASS한다는 뜻이다. 핵심 Positive·Mutation·Builder 8 tests PASS. 전체 Source Fixture 57 tests가 표적 회귀에 포함된다. skip/xfail 추가 또는 Severity 완화는 없다.

## 7. Derived hash regeneration evidence

`derived_policy_profile`, `candidate_signature`, `canonical_json_hash`, `evaluate_variation_precheck_bound`, `build_candidate_eligibility_bound`, `candidate_evaluation_input_hashes`, `build_candidate_approval`, `build_bound_crime_event_contract`를 사용했다.

`validate_candidate_evaluation`과 `validate_candidate_approval`는 Issue 0이며 정상 `approved_variation_output`은 점수 조작 없이 VAR-01을 선택한다. Fixture의 저장 Hash끼리만 비교하지 않고 기존 Builder로 산출물을 다시 계산하는 회귀가 있다.

| Artifact | Canonical document SHA-256 또는 Text byte SHA-256 |
|---|---|
| `variation_candidates` | `fe004c4f278b0dd48312e634fbb9a341a7bee05cfcc2607a4f6bdd1dddaadabb` |
| `candidate_event_briefs` | `30bb8e74d2a70e7306ad89c1855f1e089097b4e75a1b6642411f1162c6a66dc0` |
| `candidate_evaluation` | `58082b74db6f3b851aba8b0bce6d1c3be18c004d09e0f14b800d83af8d22db7a` |
| `candidate_approval` | `1207fd5e0a2a2e6a1281ebdb631166e9827555491b1af1a1a0ab1e14cd1c506b` |
| `story_dna` | `a51037e7fa9214eaa49bda74e5e618211fd19615d468b795daf10705b6e95ac8` |
| `case_input` | `457713f68287d2e46a828c7757acfa461fb53b31248fc4e881df69723ab27742` |
| `facts` | `f7696506d237f236aec1cf2647ffaefa7a56b91c131d4511d76c069accbbaf6f` |
| `crime_event_contract` | `f0ac235760563cca6e3377fb9a17a0c91ff88003cef705f2990a64a477a31cec` |
| `relationships` | `68cbfe4155ca53d9479810284da6baddeb4302fed881a7f589999511acf12404` |
| `actual_timeline` | `653f0d2180dc9274393dec7fff3ab15fedf5e280fc1b90ebc801ba6fef59375b` |
| `viewer_timeline` | `bf50951bda2c89db87ad882d49053df5b3352003f3ac2780997bbf6d75ec1397` |
| `clue_matrix` | `2e7643e1677d9dfebb09ba55e0fbcfe0172d9149746b30613825bfc7481d6164` |
| `scene_cards` | `10a50b1aa28e5d83903d36ff1ed63a3f8a3b72e467ad9764e9347fc20eb6df82` |
| `reaction_segments` | `5e868671beae44f2189d2a4b68033b845bc0cefa595d60a3fc4599c5056ff1f3` |
| `presentation_plan` | `b116b49733059562fda821d4c5194beb323a7d93733800b22e34e037fd56059b` |
| `screenplay_units` | `68129fefd7aa6dd7ce48df322eaff76c76d42794b59dddd51ddff38503662245` |
| `final_script` | `9c2f0f0c09bfe9505fc9a48404a56be2f6cfd47d2b47cae60148ea19fdd9a2ac` |
| `broadcast_readable_report` | `d657a6363e52b83fc2ea66b454ffeb72ff03282d51fbe6d09498d19558d9e043` |
| `production_broadcast_readable_script` | `f79b0bd9b54feaf5fecf34a5f30f3ff89dcfd9100c2d2d91cfebc999cbfd2c37` |
| `production_manifest` | `10415b950c2049194c8b1750fe98c96ae5795ae0e9e618247f1dbceb68eb5721` |

JSON Hash는 기존 canonical serializer를 사용한다. Process Trace는 실제 저장된 UTF-8 pretty-JSON Byte Hash를 사용하므로 두 Hash 표현을 혼동하지 않는다.

## 8. R1 Gate-00 through Gate-13 hash chain

증거 실행: `test_full_runtime_reaches_gate_13_without_footprint_file`, 1 PASS, 27.45초. 격리 Test Project `PRJ-901`, Process Revision 1. 기존 Staging Adapter의 현재 `allowed_writes` 경계를 그대로 유지한다.

테스트 입력 경계에서 실제 Variation Generator가 만든 미승인 Pool의 VAR-01 세 차원과 직접 파생 Profile/Signature만 보정한다. 선택/승인 상태는 PENDING으로 유지하며 실제 CORE Output Gateway, Eligibility, Evaluation, Approval, Gate Validator가 승인 여부를 결정한다. 승인 기록의 시각만 Fixture의 기존 approved_at에 고정하여 문서 Hash를 재현한다. Production Generator·Task Catalog·Validator 수정이나 Gate PASS Mock은 없다. 이는 R1 Fixture Source를 검증하는 테스트이며, 일반 생성기가 항상 이 세 차원을 자동 선택한다는 증거는 아니다.

| Gate | Trace 수 | 내부 Gate Commit Hash |
|---|---:|---|
| GATE-00 | 1 | `e89cc39162cbb73652f13d34cea212089da9a7d2bbcaef5fe132c793095c7e6c` |
| GATE-01 | 8 | `5fd09a6b08f1867e7d3eb0160959fc6ee153e04526f3ebbc23243167f8ced3bf` |
| GATE-02 | 1 | `d57bd98f4e4e4b841bca4ac72d7680cf92117bd0ebe6106012192145335381fd` |
| GATE-03 | 3 | `182ed786b7664e76ffe70432c653a3d48326ebaa35b8dae3b3b740457cec2f6b` |
| GATE-04 | 2 | `d2551ae2c326d764c4ab81df371c247bfaec9d15423e1d13823b1254f987a19b` |
| GATE-05 | 1 | `1f7a80f6a77560176b226000bdc963fc8dd52159ff7ce54ea13cfc3daca491f1` |
| GATE-06 | 1 | `d8cc854356ecc625ad4d1e0ce1fc45e3606c9bc981b5fab34d3bac0f62c5de58` |
| GATE-07 | 3 | `104d42f2a21c651abbc2e7a61a3099cc13814b31086fce33aeb548fcbba99103` |
| GATE-08 | 5 | `2fed15a88fb611f9385aa36902bc920151f3735cbd40941fff225a170eb95df2` |
| GATE-09 | 4 | `da9f77315da9795d7a3508390ad65b6cd6d23a99fd6ef9f814985a25a64caa1f` |
| GATE-10 | 1 | `d5cd4a58cf033b32abb07e0831638c2d8e2b4924bbe223561bff3c8622cfad80` |
| GATE-11 | 1 | `f2b41496828e230058bee616d8db3fa706989f36f67edc5f6ec6c47e72c44fa9` |
| GATE-12 | 2 | `d7890258456171751833db45b6d9e7e511eed5c40c6314c9efba2095b1dce597` |
| GATE-13 | 6 | `dcb1bd2df7e7ce68df07ccc7f2fb163181685e7e4af6fd8fe4a87dd1344e2f03` |

39개 실제 Trace의 입력 Hash 386개를 검사한다. 승인 전 다섯 Task는 PENDING Variation Byte와 비교하고, GATE-13이 읽은 validation_report는 GATE-12 직후 캡처 Byte와 비교한다. Output Profile 리소스도 실제 Versioned 파일 Byte로 검증한다. 나머지는 동일 Project Canonical Byte와 직접 일치한다.

Runtime Catalog상 Evaluation·Approval은 GATE-01에서 생성되며, Goal이 요구한 GATE-02 Evaluation 및 GATE-03 Approval Snapshot에서도 동일 Hash를 확인한다. GATE-04에서는 실제 Canonical Artifact로 차원 Oracle을 다시 실행한다. GATE-05/07/08 Source Hash, GATE-09 Report, GATE-13 Production Copy·Manifest를 Fixture/기존 Builder와 대조한다.

- Report: 2.1.0 / OWNER_BOUND_1 / NEEDS_REVIEW / issues=[].
- Profile: BROADCAST_READABLE_SCRIPT@2.0.0.
- enforce_final_footprint=false, production_footprint.json 없음.
- Manifest: 1.2.0, Source Report Hash와 Readable Byte 결속.
- State: EDITORIAL_REVIEW_REQUIRED, ARTIFACT_COMPLETE, CONTRACT_VALIDATED, PROCESS_CONFORMANT.
- Audit: PASS, editorial_approved=false, production_ready=false, state_unchanged=true.
- Audit Snapshot 전후: `2651f12cdd22d6f22f6c7ba4ea0f6876c74062b4a08ea598058a5246ec2bd615`.
- State Byte Hash: `0eecc704e958ed12a762c1206c7baca115528d7064712ebf00ce1a097b86ec7c`.
- Trace Byte Hash: `03263eb58ca7e74f9018391ab4d57fb35dae2b8f57e3aaa66e2d261ad93d4457`.
- Gate 내부 Commit/Trace ID는 실행별로 달라지며 위 값은 이 증거 실행의 기록이다.

## 9. R1 visible script byte invariance

기준 Head의 Bundle을 Git에서 다시 읽어 동일한 보호 Renderer로 렌더링하고 보정 후 출력과 직접 Byte 비교했다.

| 출력 | 변경 전 = 변경 후 SHA-256 |
|---|---|
| Machine Final | `9c2f0f0c09bfe9505fc9a48404a56be2f6cfd47d2b47cae60148ea19fdd9a2ac` |
| Canonical Readable | `f79b0bd9b54feaf5fecf34a5f30f3ff89dcfd9100c2d2d91cfebc999cbfd2c37` |
| Production Readable Copy | `f79b0bd9b54feaf5fecf34a5f30f3ff89dcfd9100c2d2d91cfebc999cbfd2c37` |

R1의 비수정 Artifact 21개는 Bundle 내 원본 JSON 구간 Byte까지 비교했다. Facts, Character, Timeline, Clue, Scene, Panel, Presentation, Screenplay Text가 그대로다. REL-01 display_summary, Evaluation scores/weights, Unselected Candidate도 불변이다. 이 불변 Hash는 수정 가능한 Fixture Expected Metadata와 독립된 회귀 Oracle에 고정되어 있다.

## 10. R2 and PRJ-006 regression invariance

- R2 전체 레코드(Artifact+Metadata) 원본 Byte 불변. Canonical record SHA-256 `e8ec178264a53a29a27e911a63012d79a44bc7fa784d58e6a2e68b4f2d26c27e`.
- R2 Machine `89a1a099c084f9c56e8416b57d387aa9efd4b6db1c238408bf3d254851636cc9`.
- R2 Readable `7ebe714f4f7954932d05cf92d6caa7a446c049bf94f01b94ea3730959c9791eb`.
- PRJ-006 Historical Report 2.0 Compatibility test PASS. R2에는 R1 Target이나 테스트 Source 보정을 적용하지 않는다.

| 보호 경로 | 기준 = 현재 Git Tree |
|---|---|
| RUNTIME | `5d0b05e3ff464c4ab154818f54def921d5efa5b0` |
| RUNTIME_ADAPTERS | `779c8098382f43c3328250e7d10b9f55063931c7` |
| VALIDATORS | `347b70328b1e917df0565894cc0bd5008525f698` |
| AGENTS | `2c09ea4c7401dac1d833ea364ba19dd6a04b4430` |
| CHANNELS | `f61ad4da925c922d4e20160664cea36b15b5b3b9` |
| STANDARD | `1a484524d8b0cfc8c8a318d5b7f6ec44ecb2f818` |
| PROJECTS/PRJ-006 | `f8021e4164ff83dfa8cd665ee557a43c67b1f5c6` |
| STORY_LIBRARY | `e6330aa1f967e4db0ab06ce1e15525292420a478` |

각 보호 디렉터리는 기준 Head 대비 전체 diff 0이다. 따라서 Profile v1/v2, Registry, Report 2.0/2.1 Schema, 모든 Renderer와 PRJ-006 전체 Byte가 포함된다.

## 11. Full local validation

로컬 Python 3.14.2, 보정 코드 Commit ed046b9와 동일한 코드로 검증한다.

| 검증 | 결과 |
|---|---|
| 지정 5개 파일 표적 pytest | 237 PASS, 191.46초 |
| 전체 pytest | 758 PASS, 307.77초, skip/xfail 없음 |
| Ruff | PASS |
| strict mypy VALIDATORS RUNTIME RUNTIME_ADAPTERS tests | 153 source files PASS |
| package build | 1.6.1 sdist/wheel PASS |
| pip-audit | 알려진 취약점 없음; PyPI에 없는 로컬 editable package 1.3.3은 도구가 제외 |
| mystery-runtime doctor | contracts/provider descriptors PASS |
| Version Immutability vs origin/main | PASS |
| Version Immutability vs e7bd17712dc8e3105aeedb676ec1a29b5d4524b1 | PASS |

## 12. Exact-head remote CI

최종 문서 Commit 후 Push하고 후속 OPEN PR의 정확한 Head에서 Python 3.11·3.14 `SUCCESS`를 확인한다. CI Run의 headSha와 최종 PR headRefOid가 같아야 한다. Run/Job ID·URL·최종 Head는 PR 본문이 단일 증거 위치다. 이 문서에 자기 Commit SHA를 넣기 위해 성공 CI 뒤 새 Commit을 만들지 않는다.

## 13. Human/editorial/merge actions intentionally not performed

Human editorial-approve, 사용자-facing production-finalize, Story Library register, PR Merge/Close, 기존 PR Base 변경, force-push, 공개 Commit amend/rebase는 실행하지 않는다. 격리 회귀의 GATE-13 내부 `production.finalize`는 validation_report를 생성하는 CORE Task이며 Human Production Ready 확정 명령이 아니다. 기존 전체 회귀에서 이 생명주기 명령을 테스트하는 임시 Project는 실제 작품 승인·등록과 구분한다.

## 14. Remaining risks

- 범위는 R1 Test Fixture 차원 보정이다. 일반 작품의 장르 품질 개선이나 실제 작품 재생성은 이번 결과에 포함하지 않는다.
- 가시 콘텐츠는 의도적으로 그대로 두었다. Human Editorial Review는 별개이며 기술적 PASS를 창작 승인으로 해석하지 않는다.
- PR #24~#33의 미병합 Stack을 유지한다. 이 PR의 성공은 기존 PR을 Merge/Close할 권한이 아니다.
- Test 입력 보정과 고정 승인 시각의 범위는 R1 GATE-00~03이고 Context 종료 후 복원된다.

## 15. Final status

로컬 Artifact·Mutation·Gate·보호 Byte 증거는 위와 같다. 전체 회귀와 **이 보고서 Commit을 포함한 정확한 Head의 원격 CI**까지 확인하기 전에는 GOAL COMPLETED를 선언하지 않는다. 최종 판정은 PR 본문의 Head·CI 증거와 사용자에게 전달하는 완료 보고에 기록한다.

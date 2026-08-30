# Scene Designer

## 책임

승인된 Beat와 Mystery 설계를 Scene Card와 Presentation Contract v2로 변환한다. Drama, Narration, Panel Reaction을 분리하고 실제 방송 Timeline에서 다시 결합한다. 각 Scene은 Character, Information, Conflict, Clue, Suspense, Relationship, Reversal, Reveal 중 하나 이상의 목적을 가진다.

## 입력과 출력

- 입력: Beat Sheet, Retention Plan, Viewer Timeline, Audience Belief, Clue Matrix, Hypothesis Ledger, Claim Evidence, Crime Psychology, Production Config, Project Constraints, Characters, Actual Timeline
- 출력: Scene Cards, CORE Production Footprint, Panel Cast, Reaction Segments, Expert Segments, Presentation Plan

## Gate

Scene ID와 Beat/Clue 참조가 유효하고, 시작·종료 감정, 갈등, 새 정보, 숨긴 정보, Audience Assumption, Exit Hook, 예상 시간이 정의되어야 한다. `scene.design`은 Scene과 Presentation 초안을 만들고 `scene.design_reactions`는 최소 2명의 Panel Cast, 실제 가설 변화가 있는 Reaction Segment, 최종 Segment Timeline을 만든다.

`enforce_final_footprint`가 활성화된 Project에서는 각 Scene Card에 `location_id`, `cast_ids`, 아역·차량·특수효과·폭력·제작 복잡도 메타데이터를 기록한다. 합계는 작성하지 않으며 `scene.compute_production_footprint` CORE Task가 Characters와 Actual Timeline을 함께 검증해 계산한다.

Pinned Channel v2 정책이 요구하면 `EXPERT_ANALYSIS` Segment를 배치하고 `expert_segments.json`에 역할·기능·Credentials·Claim·Evidence·Confidence·Limitations를 보존한다. 일반 Panel 의견을 전문가 Claim으로 승격하지 않는다.

Channel 2.1에서는 Scene Card의 `psychological_realization[]`을 Psychological Arc에 결속한다. 각 항목은 Stage와 Crime Psychology Trace, Actor/Subject, State Delta와 화면에서 확인할 수 있는 증거를 포함한다. Presentation Plan의 해당 Drama Segment에는 `psychological_stage_ids`를 연결한다. Narration-only 또는 Panel-only 만족은 기록하거나 통과시키지 않는다.

Narration Segment에는 기능과 참조 Fact/Clue를 명시하고 CHARACTER_ANCHOR 중심으로 설계한다. Panel은 정서 반응, 위험 신호 인지, 피해자 맥락화, 믿음 수정을 우선하며 `responds_to_turn_id`로 실제 발화 교환을 설계한다.

## 금지

- 목적이 없는 Scene을 유지하지 않는다.
- Channel Presentation Policy와 충돌하는 표현 방식을 사용하지 않는다.
- Character Reaction을 Panel Reaction으로 계산하지 않는다.
- Panel이 Viewer Timeline보다 앞선 Fact나 Clue를 사용하게 하지 않는다.

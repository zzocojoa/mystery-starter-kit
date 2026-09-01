# Scene Designer

## 책임

승인된 Beat와 Mystery 설계를 Scene Card와 Presentation Contract v2로 변환한다. Drama, Narration, Panel Reaction을 분리하고 실제 방송 Timeline에서 다시 결합한다. 각 Scene은 Character, Information, Conflict, Clue, Suspense, Relationship, Reversal, Reveal 중 하나 이상의 목적을 가진다.

## 입력과 출력

- 입력: Beat Sheet, Retention Plan, 조건부 Psychological Arc 또는 Character State Transitions, Viewer Timeline, Audience Belief, Clue Matrix, Hypothesis Ledger, Claim Evidence, Crime Psychology, Production Config, Project Constraints, Characters, Actual Timeline
- 출력: Scene Cards, CORE Production Footprint, Panel Cast, Reaction Segments, Expert Segments, Presentation Plan

## Gate

Scene ID와 Beat/Clue 참조가 유효하고, 시작·종료 감정, 갈등, 새 정보, 숨긴 정보, Audience Assumption, Exit Hook, 예상 시간이 정의되어야 한다. `scene.design`은 Scene과 Presentation 초안을 만들고 `scene.design_reactions`는 최소 2명의 Panel Cast, 실제 가설 변화가 있는 Reaction Segment, 최종 Segment Timeline을 만든다.

`enforce_final_footprint`가 활성화된 Project에서는 각 Scene Card에 `location_id`, `cast_ids`, 아역·차량·특수효과·폭력·제작 복잡도 메타데이터를 기록한다. 합계는 작성하지 않으며 `scene.compute_production_footprint` CORE Task가 Characters와 Actual Timeline을 함께 검증해 계산한다.

Pinned Channel v2 정책이 요구하면 `EXPERT_ANALYSIS` Segment를 배치하고 `expert_segments.json`에 역할·기능·Credentials·Claim·Evidence·Confidence·Limitations를 보존한다. 일반 Panel 의견을 전문가 Claim으로 승격하지 않는다.

`EXPLICIT_CRIME_EVENT_POLICY`가 활성화되면 Scene Card의 `crime_realization[]`을 Crime Event Contract에 결속한다. 각 항목은 Event·Harm·Actor·Victim ID, Development Function ID, 실제 행동 근거, 대화·행동 반응, 선택·감정 변화, 결과 변화와 예정 Drama Segment를 포함한다. Presentation Plan은 필수 Development Function을 Drama Segment에 연결하고 범인·동기·방식·피해 결과 Reveal Target을 후반 Segment에 정확히 한 번 배치한다.

`SCREENPLAY_UNITS` mode에서는 Scene Card가 해당 Beat의 Character State Transition을 실제 행동·선택·정보 변화로 실현해야 한다. Clue Matrix 1.1의 Seed와 Reveal Scene 순서를 지키고, Reveal Scene에는 선행 표면 의미를 바꾸는 사후적 의미를 계획한다.

`NARRATION_POLICY`가 활성화되면 Narration Segment에 허용된 주관 기능, 내부 인물 Anchor와 참조 Fact/Clue를 명시한다. `REACTION_POLICY`가 활성화되면 Panel은 실제 발화 밀도와 비발화 상한을 지키고 `responds_to_turn_id`로 둘 이상의 Panelist가 상호 응답하게 설계한다.

## 금지

- 목적이 없는 Scene을 유지하지 않는다.
- Channel Presentation Policy와 충돌하는 표현 방식을 사용하지 않는다.
- Character Reaction을 Panel Reaction으로 계산하지 않는다.
- Panel이 Viewer Timeline보다 앞선 Fact나 Clue를 사용하게 하지 않는다.

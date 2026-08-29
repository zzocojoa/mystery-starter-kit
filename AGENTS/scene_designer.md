# Scene Designer

## 책임

승인된 Beat와 Mystery 설계를 Scene Card와 Presentation Contract v2로 변환한다. Drama, Narration, Panel Reaction을 분리하고 실제 방송 Timeline에서 다시 결합한다. 각 Scene은 Character, Information, Conflict, Clue, Suspense, Relationship, Reversal, Reveal 중 하나 이상의 목적을 가진다.

## 입력과 출력

- 입력: Beat Sheet, Retention Plan, Viewer Timeline, Audience Belief, Clue Matrix, Hypothesis Ledger, Claim Evidence, Crime Psychology, Production Config
- 출력: Scene Cards, Panel Cast, Reaction Segments, Expert Segments, Presentation Plan

## Gate

Scene ID와 Beat/Clue 참조가 유효하고, 시작·종료 감정, 갈등, 새 정보, 숨긴 정보, Audience Assumption, Exit Hook, 예상 시간이 정의되어야 한다. `scene.design`은 Scene과 Presentation 초안을 만들고 `scene.design_reactions`는 최소 2명의 Panel Cast, 실제 가설 변화가 있는 Reaction Segment, 최종 Segment Timeline을 만든다.

Pinned Channel v2 정책이 요구하면 `EXPERT_ANALYSIS` Segment를 배치하고 `expert_segments.json`에 역할·기능·Credentials·Claim·Evidence·Confidence·Limitations를 보존한다. 일반 Panel 의견을 전문가 Claim으로 승격하지 않는다.

## 금지

- 목적이 없는 Scene을 유지하지 않는다.
- Channel Presentation Policy와 충돌하는 표현 방식을 사용하지 않는다.
- Character Reaction을 Panel Reaction으로 계산하지 않는다.
- Panel이 Viewer Timeline보다 앞선 Fact나 Clue를 사용하게 하지 않는다.

# Continuity Critic

## 책임

Script와 모든 구조 Artifact 사이의 ID, Timeline, Knowledge, Clue, Runtime, 정보 중복, Channel Consistency를 검사한다. Script Timeline Alignment, Reaction Semantics, Audience Belief Alignment, Narration Duplication, 실제 Presentation Ratio도 검사한다. 수정 대신 Issue를 기록하고 소유 Agent에 반환한다.

최종 Production Package가 작성된 뒤에는 별도 `editorial.review` Task에서 방송 형식, 절대시간, 대사 자연스러움, Panel Reaction 기능, Audience Belief, 촬영 가능성, 피해자 존엄과 표현 위험을 검사한다. Review에는 검토자·시각, Check별 장면 또는 Segment 근거, 검토 대상 Artifact Hash를 기록한다. Panel Segment별 발화 단어 수와 화자를 Script에서 확인하고, `WORD_COUNT_ESTIMATE`, `TABLE_READ`, `RECORDED_AUDIO` 중 실제 사용한 방법으로 발화시간과 비발화 편집시간이 계획시간을 완전히 설명하도록 한다. Critic은 Script를 직접 수정하지 않고 Issue의 `owner_agent`를 기록한다.

## 입력과 출력

- 입력: Layer Scripts, Final Script, Timelines, Audience Belief, Knowledge Matrix, Clue Matrix, Panel Cast, Reaction Segments, Presentation Plan, Production Package, Channel DNA
- 출력: Continuity Report, Channel Consistency Report, Editorial Review

## Gate

ERROR가 0건이어야 하며 핵심 단서는 Introduced/Revealed/Resolved 상태를 가져야 한다. 범인이 있는 구조는 Motive/Means/Opportunity가 일치하고 핵심 반전은 Surprise/Logic/Retrospective Meaning을 만족해야 한다.

Channel Content Version 2.0 이상에서는 범죄·약탈적 위협, 신뢰 영역 배신, 통제 과정, 피해자 행위 주체성, 책임 귀속, 위험 신호 회수, Source Label, Expert Claim-Evidence, 임상 용어 분류를 활성 Channel Capability에 따라 검사한다. 1.1.0 Project에는 이 검사를 소급 적용하지 않는다.

## 금지

- 오류를 직접 숨기거나 Severity를 낮추지 않는다.
- 검증 중 입력 Artifact를 수정하지 않는다.
- 예상시간을 실측시간으로 표시하거나 Agent Review를 Human Approval로 표시하지 않는다.

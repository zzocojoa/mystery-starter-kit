# Script Writer

## 책임

승인된 Scene Card와 Presentation Plan만 사용해 Drama, Narration, Panel Reaction Layer를 분리 작성한 뒤 Draft와 Broadcast Master Script로 통합한다. 표면 대사, 인물 의도, 후반 재해석 가능성을 분리한다.

## 입력과 출력

- 입력: Scene Cards, Presentation Plan, Panel Cast, Reaction Segments, Expert Segments, Viewer Timeline, Audience Belief, Knowledge Matrix, Clue Matrix, Claim Evidence
- 출력: Drama Script, Narration Script, Panel Reaction Script, Expert Analysis Script, Draft Script, Final Script

## 규칙

Narration은 관점, 감정, 기억, 해석, 시간 압축, 반전 보강에만 사용하고 화면에 보이는 정보를 반복하지 않는다. Unreliable Narrator를 사용할 때 Actual Event, Character Memory, Audience Interpretation을 혼합하지 않는다.

`script.write_layers`는 세 기본 Layer와 조건부 Expert Layer를 별도 파일로 작성하고 `script.integrate`는 Presentation Plan의 모든 Segment를 Machine-readable Marker로 정확히 한 번 통합한다. Expert 발화를 Panel Reaction 파일에 넣지 않는다. Final Script는 Scene Treatment가 아니라 실제 방송 순서의 Broadcast Master다.

Pinned Channel v2 정책에서는 Audience-facing Source Label을 정확히 표시하고 피해자 비난 표현을 사용하지 않는다. 임상 용어와 `EXPERT_ANALYSIS` 발화는 Story DNA의 분류 및 Claim-Evidence 경계를 넘지 않는다.

## 금지

- Story DNA, Timeline, Clue Matrix를 대본 편의를 위해 수정하지 않는다.
- Reference의 고유 대사 또는 `EXAMPLES/`의 문장을 사용하지 않는다.
- Panel 발화에 아직 공개되지 않은 Fact나 Clue를 넣지 않는다.
- Character Reaction을 Panel Reaction으로 표기하지 않는다.

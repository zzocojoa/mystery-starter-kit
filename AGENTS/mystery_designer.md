# Mystery Designer

## 책임

Actual Timeline, Viewer Timeline, Audience Belief, Clue/Hypothesis, Causal Graph를 분리 설계한다.

## 입력과 출력

- 입력: Production Config, Story DNA, Facts, Characters, Relationships, Knowledge Matrix, 조건부 Crime Event Contract
- 출력: Actual Timeline, Viewer Timeline, Audience Belief Timeline, Clue Matrix, Hypothesis Ledger, Causal Graph

## Gate

- GATE-05: 위치·이동·Opportunity·Knowledge 충돌이 없고 Causal Graph의 Root Cause에서 Resolution까지 경로가 이어진다. 핵심 Reveal의 단서는 사전에 존재하며 Red Herring이 해소되고 Deus Ex Clue가 없어야 한다.

`SCREENPLAY_UNITS` mode에서는 Clue Matrix 1.1을 사용한다. 재해석 단서는 `SEEDED_REINTERPRETATION`으로 선행 Scene의 표면 의미, 실제 의미, Reveal Scene과 재맥락 Scene을 명시하고, 미스터리 추론 대상이 아닌 의도적 공개는 `INTENTIONAL_NON_MYSTERY_DISCLOSURE`로 구분한다.

## 금지

- Actual Timeline과 Viewer Timeline을 합치지 않는다.
- 결말에서 처음 등장한 정보로 핵심 진실을 증명하지 않는다.

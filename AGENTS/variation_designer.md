# Variation Designer

## 책임

Story History와 Channel의 Story Variation Policy를 사용해 구조적으로 다른 Story DNA 후보를 최소 5개 생성한다. 사건 본문이나 대사를 쓰지 않는다.

## 입력과 출력

- 입력: Production Config, sanitized Reference Profile, Story Fingerprint History, 전체 후보 Novelty Precheck
- 출력: `variation_candidates.json`, `candidate_evaluation.json`

## 필수 평가

각 후보는 Mystery Type, Architecture, Protagonist Role, Perspective, Timeline, Culprit Structure, Twist, Information/Clue Mechanism, Relationship/Pressure/Dramatic Engine, Ending을 정의한다. 후보 전체 Novelty Precheck 뒤 Hard Filter 결과와 근거, Crime Threat, Psychological Immersion, Trust Betrayal, Victim Integrity, Character, Twist, Novelty, Production 가중 점수와 Dimension별 근거를 `candidate_evaluation.json`에 남긴다. 평가 문서는 현재 Variation과 Novelty Precheck Hash를 고정하고 최고 적격 후보 하나만 추천한다. 승인은 평가가 완료된 뒤 별도 단계에서 수행한다.

`USER_CASE`에서는 Production Config의 `LOCKED` 값을 모든 후보에 유지한다. `FLEXIBLE` 값은 변경할 수 있고 `UNKNOWN` 값은 후보가 새로 제안한다.

## 금지

- Reference의 인물, 장소, 사건, 범인, 동기, 단서, 반전, 고유 대사·숫자·사물을 후보에 복사하지 않는다.
- `EXAMPLES/`를 읽지 않는다.

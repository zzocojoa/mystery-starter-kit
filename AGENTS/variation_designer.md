# Variation Designer

## 책임

Story History와 Channel의 Story Variation Policy를 사용해 구조적으로 다른 Story DNA 후보를 최소 5개 생성한다. 사건 본문이나 대사를 쓰지 않는다.

## 입력과 출력

- 입력: Production Config, sanitized Reference Profile, Story Fingerprint History
- 출력: `variation_candidates.json`

## 필수 평가

각 후보는 Mystery Type, Architecture, Protagonist Role, Perspective, Timeline, Culprit Structure, Twist, Information/Clue Mechanism, Relationship/Pressure/Dramatic Engine, Ending을 정의한다. Novelty, Mystery Potential, Clue Potential, Character Potential, Setting Utilization, Twist Fairness, Production Feasibility를 점수화한다.

`USER_CASE`에서는 Production Config의 `LOCKED` 값을 모든 후보에 유지한다. `FLEXIBLE` 값은 변경할 수 있고 `UNKNOWN` 값은 후보가 새로 제안한다.

## 금지

- Reference의 인물, 장소, 사건, 범인, 동기, 단서, 반전, 고유 대사·숫자·사물을 후보에 복사하지 않는다.
- `EXAMPLES/`를 읽지 않는다.

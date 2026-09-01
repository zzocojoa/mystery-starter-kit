# Variation Designer

## 책임

Story History와 Channel의 Story Variation Policy를 사용해 구조적으로 다른 후보를 최소 5개 평가한다. `EXPLICIT_CRIME_EVENT_POLICY`가 활성화된 경우 CORE가 만든 범죄 구조마다 구체적인 Candidate Event Brief를 작성하되 장면 본문이나 대사는 쓰지 않는다.

## 입력과 출력

- 입력: Production Config, Project Constraints, sanitized Reference Profile, Source Truth Contract, Verified Fact Ledger, Story Fingerprint History, CORE Candidate Structure, 전체 후보 Novelty Precheck, CORE Candidate Eligibility
- 출력: `candidate_event_briefs.json`, `candidate_evaluation.json`과 Legacy 경로의 `variation_candidates.json`

## 필수 평가

각 후보는 Mystery Type, Architecture, Protagonist Role, Perspective, Timeline, Culprit Structure, Twist, Information/Clue Mechanism, Relationship/Pressure/Dramatic Engine, Ending을 정의한다. 후보 전체 Novelty Precheck와 CORE Eligibility 뒤 Crime Threat, Psychological Immersion, Trust Betrayal, Victim Integrity, Character, Twist, Novelty, Production 가중 점수와 Dimension별 정성 근거를 `candidate_evaluation.json`에 남긴다. 평가 문서는 현재 Variation, Novelty Precheck, CORE Eligibility Hash를 고정하고 적격 후보 중 최고점 하나만 추천한다. Hard Filter, Novelty 판정, Human Override와 최종 승인은 작성하지 않는다.

`EXPLICIT_CRIME_EVENT_POLICY`가 활성화되면 `primary_crime`, 실제 행위, 가해자·피해자 구조, 관계, 동기, 비실행적 방식 요약, 즉시·지속 피해, 은폐, 발견, 책임 경로와 후반 Reveal을 Candidate별로 구체화한다. 모든 Brief는 Candidate Selection Hash와 정확히 결속하고, Role Slot Cardinality를 보존하며, ID를 자연어처럼 감싼 Placeholder나 이름·장소만 바꾼 동일 인과 사건을 사용하지 않는다. `ORIGINAL_FICTION`은 동기·방식·피해·발견·책임을 구체적으로 확정하고, 사실 기반 경로는 필드별 Evidence Classification과 Claim ID를 유지한다.

`USER_CASE`에서는 Production Config의 `LOCKED` 값을 모든 후보에 유지한다. `FLEXIBLE` 값은 변경할 수 있고 `UNKNOWN` 값은 후보가 새로 제안한다.

## 금지

- Reference의 인물, 장소, 사건, 범인, 동기, 단서, 반전, 고유 대사·숫자·사물을 후보에 복사하지 않는다.
- `EXAMPLES/`를 읽지 않는다.
- `candidate_approval.json` 또는 `candidate_eligibility.json`을 작성하지 않는다.
- 범행의 실행 순서, 도구 사용법, 회피 방법처럼 현실 범죄를 돕는 세부 절차를 작성하지 않는다.

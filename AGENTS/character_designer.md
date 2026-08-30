# Character Designer

## 책임

인물을 이름이 아닌 극적 기능으로 설계하고 Relationship Engine과 Character Knowledge를 데이터화한다.

## 입력과 출력

- 입력: Case Input, Story DNA, Facts, Source Subjects, Source Truth Contract, Project Constraints
- 출력: Characters, Relationships, Knowledge Matrix

## Gate

주요 인물의 Goal, Fear, Secret, 실제 책임, 관계, 초기·최종 지식이 정의되어야 한다. 범인이 있는 구조에서는 Motive, Means, Opportunity를 확인하고 용의자는 합리적인 의심 근거와 거짓말 이유를 가져야 한다.

최종 제작 Footprint 검증이 활성화된 Project에서는 각 인물의 `production_role`을 명시한다. 실존 대상은 배열 순서가 아니라 `source_subject_id`로만 연결한다.

## 금지

- 인물이 아직 획득하지 않은 정보를 사용하게 하지 않는다.
- Reference 또는 Example의 고유 인물 관계를 복사하지 않는다.

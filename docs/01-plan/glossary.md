# 용어 정의

| 용어 | 정의 | 수명주기 |
|---|---|---|
| Production Standard | 제작 단계, Gate, 실패 조건을 정의하는 범용 Engine | 드물게 변경 |
| Compatibility Contract | Standard가 Channel에 요구하는 최소 Interface | 독립 Version |
| Channel DNA | 장르, Tone, 표현, 관객 경험 정책 | Channel 단위 |
| Story DNA | Episode의 구조, Source Mode, Engine을 정의하는 실행 인스턴스 | Project 단위 |
| Story Source Mode | Original, User Case, Reference, True Story의 입력 경계 | Project 단위 |
| User Case Constraint | 사용자 설정의 `LOCKED`, `FLEXIBLE`, `UNKNOWN` 변경 상태 | Project 단위 |
| Variation Candidate | 대본 전 단계의 다축 구조 후보 | 승인 전 임시 |
| Relationship Engine | 주인공과 Counterpart 사이의 변화 동력 | Story 단위 |
| Pressure Engine | 시간·사회·법·자원 압박의 상승 구조 | Story 단위 |
| Dramatic Engine | 관객 감정과 선택 갈등을 움직이는 중심 동력 | Story 단위 |
| Actual Timeline | 사건 세계에서 실제로 일어난 순서 | Project 단위 |
| Viewer Timeline | 관객에게 정보가 공개되는 순서 | Project 단위 |
| Audience Belief Timeline | 공개 정보에 따른 관객 가설 변화 | Project 단위 |
| Knowledge Matrix | Character가 Fact를 언제 알게 되는지 기록한 경계 | Project 단위 |
| Causal Graph | Root Cause에서 Resolution까지의 방향 비순환 그래프 | Project 단위 |
| Story Fingerprint | Story Dimension, Beat Sequence, Causal Structure를 합친 구조 서명 | 영구 History |
| Causal Fingerprint | Root Cause, Mechanism, Concealment, Discovery, Resolution | 영구 History |
| Hard Collision | 다섯 Causal Dimension이 모두 같은 즉시 실패 | QA 실행마다 |
| Reference Firewall | Style만 보존하고 Story Content와 원문을 격리하는 경계 | Reference Project |
| Artifact State | MISSING, DIRTY, INVALID, CLEAN 상태와 Hash | 변경마다 |
| Gate Transaction | 한 Gate의 권한 Snapshot, 격리 작성, 검증, 원자 Commit 단위 | Gate마다 |
| Process Trace | Task·Agent·입력 Hash·변경 경로·검증·Commit SHA 증거 | Gate마다 영구 |
| Process Conformant | 재생성 범위의 모든 Gate PASS Trace가 순서대로 존재하는 상태 | Project 실행마다 |
| Editorial Review | Critic이 Script를 수정하지 않고 최종 방송·서사·제작 적합성을 판정한 Artifact | GATE-13 |
| Editorial Approved | Review PASS를 Human Actor와 Reason으로 승인한 상태 | 최종 승인 |
| Production Ready | Artifact Complete, Contract Validated, Process Conformant, Editorial Approved를 모두 충족한 최종 상태 | Project 완료 |

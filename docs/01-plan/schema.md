# 스키마 설계

## 핵심 엔티티

| 엔티티 | 식별자 | 필수 필드 | 관계 |
|---|---|---|---|
| Compatibility Contract | `contract_family` + `contract_version` | 지원 Schema 범위, 필수·선택 Capability, 호환성 정책 | Channel DNA를 판정 |
| Standard Defaults | `defaults_version` | 선택 Capability별 기본값 | 누락된 Optional만 보완 |
| Channel DNA | `channel_id` + `schema_version` | 5개 Required Capability | Story DNA의 허용 범위를 제약 |
| Compatibility Report | Channel 실행 단위 | 판정, Capability 상태, 무시 필드, 오류 | PASS일 때만 Story 생성 허용 |
| Story DNA | `project_id` | 미스터리 구조, 관점, 시간선, 반전, 정보·단서 장치 | Project를 생성 |
| Story Fingerprint | `project_id` | 구조적 특징 | Novelty QA 비교 |

## Required Capability

| 이름 | 책임 | 최소 제약 |
|---|---|---|
| `GENRE_POLICY` | 장르 범위와 현실성 | 허용 장르 1개 이상, realism |
| `TONE_POLICY` | 일관된 정서와 금지 톤 | 핵심 톤 1개 이상 |
| `PRESENTATION_POLICY` | Drama/Narration/Reaction 결합 방식 | 표현 모드, 관객 위치, 정보 순환 |
| `AUDIENCE_CONTRACT` | 관객에게 약속하는 추리 경험 | Fair Play 여부, 약속 1개 이상 |
| `STORY_VARIATION_POLICY` | 반복 요소와 가변 요소 분리 | 고정·가변 차원 각각 1개 이상 |

## 판정 순서

1. Contract와 Defaults 자체 Schema를 검증한다.
2. Channel의 Required Capability 존재 여부와 내부 Schema를 검증한다.
3. Optional Capability가 없으면 동일 이름의 Standard Default를 적용한다.
4. Schema Family와 Major 호환 범위를 검증한다.
5. 검증이 끝난 뒤 미지의 상위 필드와 Capability를 보고하고 무시한다.
6. 오류가 하나라도 있으면 `FAIL`, 아니면 `PASS`를 반환한다.

## 버전 규칙

호환 범위는 `min_inclusive <= schema_version < max_exclusive`로 판정한다. `content_version`은 보고서에 기록하지만 판정에는 사용하지 않는다. 같은 Major Version의 새 필드는 `additionalProperties`로 허용해 Forward Compatibility를 유지한다.

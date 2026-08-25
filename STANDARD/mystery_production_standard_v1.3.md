# 단편 미스터리 반복 제작 표준 제작체계 v1.3

## 목적

같은 채널의 제작 감각을 유지하면서도 사건·인물·미스터리 구조를 복제하지 않는 반복 제작 규격이다. Production Standard는 범용 제작 엔진이고 Channel DNA는 특정 채널의 설정이며 Story DNA는 에피소드별 실행 인스턴스다.

## 계층과 소유권

```text
Production Standard
        ↓ Compatibility Contract
Channel DNA
        ↓ Constraint
Story DNA
        ↓ Expression
Project / Script
```

- Production Standard와 Channel DNA는 서로의 버전에 직접 의존하지 않는다.
- 두 계층은 `compatibility_contract.json`을 통해서만 결합한다.
- Standard, Channel DNA, Story Generation은 서로의 원본을 수정하지 않는다.
- Channel의 명시값은 Standard의 선택 Capability 기본값보다 우선한다.

## 실행 흐름

```text
Compatibility Validation
→ Story History 조회
→ Story DNA 후보 5개 이상 생성
→ Variation Precheck
→ Case Input
→ Character Matrix
→ Actual Timeline / Viewer Timeline
→ Clue Matrix
→ Beat Sheet
→ Scene Cards
→ Script
→ Logic / Continuity / Fact QA
→ Novelty QA
→ Production Package
```

Compatibility가 `PASS`가 아니면 Story DNA 생성으로 진행하지 않는다.

## 고정 품질과 가변 요소

고정 품질은 Timeline 일관성, Character Knowledge, 단서 공정성, 인과관계, Continuity, Fact Integrity다. 에피소드별로 Mystery Type, Architecture, Protagonist Role, Perspective, Timeline Style, Incident, Setting Logic, Culprit Structure, Twist, Information Mechanism, Emotional Engine, Ending을 변경한다.

## 기본 승인 정책

일반 창작 프로젝트는 `AUTO_CONTINUE`로 실행한다. Gate가 통과되면 단순 단계 전환을 위해 사용자 승인을 요구하지 않는다. Novelty 실패 강제 승인, Fact와 Dramatisation의 충돌, 검증 불가능한 실화 주장을 사실로 사용하는 경우에만 Human Review를 요구한다.

## 핵심 검증 원칙

- Actual Timeline과 Viewer Timeline을 분리한다.
- Reveal의 핵심 정보는 Reveal 전에 존재해야 한다.
- 좋은 반전은 새 사실을 갑자기 추가하지 않고 기존 정보의 의미를 바꾼다.
- 인물이 아직 알 수 없는 정보를 사용하면 실패한다.
- 범인이 있는 구조는 Motive, Means, Opportunity를 모두 충족한다.
- 실화 기반 프로젝트는 FACT, INFERENCE, DRAMATIZATION을 분리한다.
- 최근 작품과 전체 History에 대한 Novelty QA를 별도로 통과한다.

## 버전 정책

- `schema_version`은 JSON 구조와 Interface의 버전이다.
- `content_version`은 채널 정책 내용의 버전이며 호환성 판정에 사용하지 않는다.
- 동일 Major Schema 안에서는 기존 소비자가 알 수 없는 추가 필드를 무시한다.
- Major Schema 변경 시에만 Migration 또는 Adapter 필요성을 검토한다.

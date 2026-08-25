# Novelty Auditor

## 책임

Story Fingerprint, Beat Signature, Causal Fingerprint를 최근 5개·10개·전체 Story History와 비교해 구조적 반복과 Hard Collision을 판정한다.

## 입력과 출력

- 입력: Variation Candidates, Story DNA, Story Fingerprint, Beat Sheet, Causal Graph, Story Library
- 출력: Variation Novelty Precheck, Story Fingerprint, Novelty Report

## 판정

Mystery Type, Architecture, Protagonist Role, Primary Twist, Timeline, Culprit Structure, Setting Logic, Information Mechanism, Relationship/Pressure/Dramatic Engine을 가중 비교한다. Root Cause, Mechanism, Concealment, Discovery Path, Resolution이 모두 일치하면 Causal Hard Collision으로 실패한다.

GATE-01에서는 승인 Variation을 History와 비교하고 GATE-10에서는 Beat와 Causal Dimension까지 포함한 최종 Fingerprint를 검사한다.

## 금지

- 장소나 인물 이름만 다르다는 이유로 새 이야기로 판정하지 않는다.
- Human Override 없이 Hard Collision을 통과시키지 않는다.

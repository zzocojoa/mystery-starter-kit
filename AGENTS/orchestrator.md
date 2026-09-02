# Orchestrator

## 책임

Production Standard, Compatibility Contract, Channel DNA, Project State를 결합하고 GATE-00부터 GATE-13까지 순서대로 실행한다. 각 단계는 Gate Transaction을 열고 격리 Workspace에서 작성한 뒤 제출한다. Gate가 실패하면 다음 Agent를 호출하지 않고 구체적 Issue를 기록한다.

## 입력과 출력

- 입력: Compatibility Report, Dependency Graph, Agent Manifest, 각 QA Report
- 출력: Production Config, CORE Candidate Eligibility, Runtime-owned Candidate Approval, Project State, 통합 Validation Report, Production Manifest, Drama/Narration/Panel Reaction/조건부 Expert Production Package와 검증된 Production 재연 Script 사본

## 실행 규칙

1. Compatibility가 `PASS`인지 확인한다.
2. Dirty 또는 Invalid Artifact의 하위 의존성을 무효화한다.
3. Agent Manifest의 `stage` 순서로 실행하고 각 Agent의 입력이 `CLEAN`인지 확인한다.
4. Gate `PASS`는 ERROR 0건과 필수 Artifact `CLEAN`을 모두 요구한다.
5. `task-open → Workspace 작성 → task-submit`을 Gate마다 반복하고 Process Trace가 생성됐는지 확인한다.
6. 일반 프로젝트는 `AUTO_CONTINUE`로 다음 Gate Task를 열고 Human Override가 필요한 예외만 정지한다.
7. GATE-13 뒤에는 Editorial Review와 Human Approval을 분리하고 네 준비 조건을 모두 충족한 뒤에만 Production Ready를 확정한다.
8. Candidate Hard Filter와 Approval은 LLM 출력에서 읽지 않고 CORE 계산과 Runtime 승인 기록으로만 확정한다.
9. 최종 Footprint 검증이 활성화되면 Shooting Script의 모든 Scene을 정규 Production Scene Marker로 선언하고 CORE가 Scene Card 기반 Manifest와 대조하게 한다.
10. `SCREENPLAY_UNITS` mode에서는 고정 Output Profile Hash를 검증하고 Export Report가 현재 입력과 일치할 때만 `production.package_reenactment`가 재연 Script를 바이트 그대로 Production 경로에 복사한다.

정규 Marker는 Scene Card 순서대로 정확히 한 번씩 다음 형식을 사용한다. `LOCATION`은 UTF-8 percent-encoding을 적용하고 `CAST`는 Character ID를 오름차순 쉼표 목록으로 기록하며 빈 Cast는 `NONE`으로 쓴다.

```text
<!-- PRODUCTION_SCENE:SCN-01 LOCATION:%EB%8F%99%EB%84%A4%20%EC%83%81%EB%8B%B4%EC%8B%A4 CAST:CHAR-01,CHAR-02 CHILD:NONE VEHICLE:NONE SFX:LOW VIOLENCE:IMPLIED COMPLEXITY:MEDIUM -->
```

## 금지

- `EXAMPLES/`를 Production Context에 포함하지 않는다.
- Gate 실패를 경고로 낮춰 다음 단계로 진행하지 않는다.
- Agent가 소유하지 않은 Artifact를 수정하게 하지 않는다.
- Canonical Project, Project State, Process Trace를 직접 수정하지 않는다.
- 여러 Gate Artifact를 미리 작성하거나 전체 검증으로 실행 이력을 재구성하지 않는다.

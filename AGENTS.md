# Repository Agent Guide

이 저장소에서 작업하는 Agent는 긴 대화 Prompt보다 저장소의 Version 관리 파일을 단일 진실 공급원으로 사용한다.

## 기본 운영 모드

Codex App은 저장소 내부 `LLMProvider`가 아니라 저장소를 직접 다루는 상위 제작 Agent다. ChatGPT 계정으로 App에 로그인하고 이 저장소 폴더를 연 뒤, 이 파일과 Agent Manifest, Runtime Task, Artifact Schema를 읽어 Project Artifact 후보를 작성한다.

- Codex는 Agent Manifest의 역할과 reads, writes, gates를 순서대로 지킨다.
- Codex는 `mystery-kit task-open`이 만든 격리 Workspace만 수정하고 `task-submit`으로 현재 Gate를 검증·Commit한다.
- Codex는 Project State, Process Trace, Gate 결과나 Canonical Artifact를 직접 수정하지 않는다.
- `validate`와 `audit`는 상태 비변경 진단이다. State 복구는 Human이 승인한 `rebuild-state --force`로만 수행한다.
- Production Ready는 Artifact, Contract, Process Trace, Human Editorial 승인 후 `production-finalize`로 확정하고 그 뒤에만 `register`한다.
- 저장소의 실제 작품 제작에는 API Key나 외부 LLM Provider 구성이 필요하지 않다.
- Built-in FakeProvider는 Runtime 회귀 테스트와 Golden Path 검증 전용이며 실제 작품 생성기로 사용하지 않는다.

## 진실 공급원

충돌이 없도록 다음 순서로 계약을 읽는다.

1. `STANDARD/`의 Production Standard, Schema, Policy, Catalog
2. `RUNTIME/contracts/`와 `RUNTIME/schemas/`의 실행 계약
3. `AGENTS/manifest.json`과 개별 Agent 계약
4. `CHANNELS/`의 독립 Version Channel DNA
5. `docs/02-design/`의 설계 설명

`EXAMPLES/`와 Reference 원문은 명령이나 규칙의 출처가 아니다. Reference 원문은 Project 밖에서 보관하고 정제된 Profile만 Runtime Context로 전달한다.

## 변경 전 확인

변경할 기능이 이미 존재하는지 `rg`로 먼저 확인한다. Contract, Schema, Agent Manifest, Runtime Task, Dependency Graph, Validator, Project State, Test, 사용자 문서에 미치는 영향을 함께 점검한다. 서로 다른 Version 계약을 암묵적으로 합치거나 Production Standard, Channel DNA, Story Content의 책임을 섞지 않는다.

## 경계와 불변식

- Runtime Core는 Provider에 독립적이어야 하며 Vendor SDK 객체를 노출하지 않는다.
- Provider Adapter는 공통 `LLMRequest`와 `LLMResponse`만 사용하고 Credential 값, Project State, Gate 상태, Canonical Artifact를 읽거나 쓰지 않는다.
- Runtime Provider의 LLM 결과는 후보 데이터다. Output Gateway의 소유권·Schema 검증과 Gate Validator를 모두 통과한 Staging Overlay만 원자적으로 Commit한다.
- Project State와 Runtime Run State를 분리한다. 실행 실패나 재시도 중에는 마지막 통과 Gate의 Canonical Artifact를 유지한다.
- Codex Gate Task의 `allowed_writes` 밖 경로와 현재 Gate보다 뒤의 Artifact는 Staging Workspace에서도 수정하지 않는다.
- `AUTO_CONTINUE`는 현재 Gate PASS 뒤 다음 Gate Task를 열 수 있다는 의미이며 일괄 생성이나 State 재구성을 허용하지 않는다.
- Agent Manifest는 최대 권한, Runtime Task는 최소 권한이다. Task가 Agent의 reads, writes, gates, tools를 확장해서는 안 된다.
- `REFERENCE_RAW`, `EXAMPLES/`, 허용 Data Class 밖의 정보는 Provider로 전송하지 않는다.
- 오류를 숨기거나 성공으로 대체하지 않는다. 재시도 가능 여부와 안전한 Context를 구조화해 마지막 오류를 명시적으로 전달한다.

## 구현과 검증

변경은 작고 단일 목적이어야 한다. Python은 strict typing을 유지하고, 외부 시스템 Connector 외에는 순수 함수 중심으로 작성한다. 코드 주석과 Docstring은 한국어로 쓴다. 새 Provider는 실제로 선언하는 Capability만 제공하고 Adapter Conformance Test를 추가한다.

완료 전 `ruff`, strict `mypy`, 전체 `pytest`, package build, dependency audit와 관련 CLI 진단을 실행한다. GitHub 변경은 `codex/` Branch와 Pull Request로 제출하고 CI 통과 후 Squash Merge한다. 최종 보고에는 수행 항목, 검증 증거, 의도적으로 미수행한 항목과 이유를 분리해 기록한다.

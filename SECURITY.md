# 보안 정책

## 지원 범위

현재는 `main` 브랜치의 최신 버전만 보안 수정 대상으로 유지한다.

## 취약점 보고

보안 취약점은 공개 Issue에 작성하지 않는다. 저장소의 [Private Vulnerability Reporting](https://github.com/zzocojoa/mystery-starter-kit/security/advisories/new)을 사용하고 다음 정보를 포함한다.

- 영향을 받는 파일과 버전
- 재현 조건과 최소 재현 절차
- 예상되는 영향
- 알고 있는 완화 방법

비밀값, 접근 토큰, 실제 개인정보는 보고서와 로그에 포함하지 않는다.

## Runtime 보안 경계

- Provider Credential은 `provider_registry.json`에 값을 저장하지 않고 환경 변수 이름만 참조한다.
- Reference 원문과 `EXAMPLES/`는 Provider Context에 포함하지 않는다.
- Provider는 Canonical 파일, Project State, 임의 Shell·파일 쓰기·Network 도구에 직접 접근하지 않는다.
- 모든 Agent 출력은 Task 소유권과 Artifact Schema를 통과한 뒤 Staging에 기록한다.
- Run Event와 오류에는 Provider 원문 예외, Credential, Raw Reference를 기록하지 않는다.

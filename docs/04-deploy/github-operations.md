# GitHub 운영 가이드

## 저장소 정책

- 원격 저장소: `zzocojoa/mystery-starter-kit`
- 공개 범위: Private
- 기본 브랜치: `main`
- 병합 방식: Squash Merge
- 병합 후 작업 브랜치: 자동 삭제
- 코드 소유자: `@zzocojoa`

## Pull Request Gate

`main`에 반영하기 전에 다음 GitHub Actions Check가 통과해야 한다.

| Check | 검증 범위 |
|---|---|
| Python 3.11 | 최소 지원 Python에서 lint, type, test, build, audit |
| Python 3.14 | 현재 Python에서 lint, type, test, build |

## Dependabot

매주 월요일 다음 두 생태계를 검사한다.

- Python 패키지
- GitHub Actions

자동 생성된 Pull Request도 일반 변경과 동일한 CI를 통과해야 하며 자동 병합하지 않는다.

## 복구 절차

1. 잘못된 Squash Merge의 Commit SHA와 영향을 확인한다.
2. GitHub의 Revert 기능으로 복구 Pull Request를 만든다.
3. 전체 CI가 통과하면 복구 Pull Request를 병합한다.
4. 데이터 Schema 변경이 포함되었다면 이전 파일을 강제로 되돌리지 않고 호환 가능한 Forward Fix를 우선한다.
5. 보안 사고는 공개 Issue 대신 Private Vulnerability Reporting으로 관리한다.

Force Push와 `git reset --hard`를 공유 브랜치 복구 방법으로 사용하지 않는다.

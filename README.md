# Mystery Starter Kit

[![CI](https://github.com/zzocojoa/mystery-starter-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/zzocojoa/mystery-starter-kit/actions/workflows/ci.yml)

Production Standard, Channel DNA, Story DNA의 버전 수명주기를 분리하고 Capability Negotiation으로 연결하는 실행 가능한 초기 규격이다.

## 검증 실행

```bash
python -m VALIDATORS.cli \
  --contract STANDARD/compatibility_contract.json \
  --defaults STANDARD/standard_defaults.json \
  --channel CHANNELS/mystery_main/channel_dna.json \
  --contract-schema STANDARD/schemas/compatibility_contract.schema.json \
  --defaults-schema STANDARD/schemas/standard_defaults.schema.json \
  --channel-schema STANDARD/schemas/channel_dna.schema.json \
  --output PROJECTS/PRJ-001/00_PROJECT/compatibility_report.json
```

종료 코드는 `PASS=0`, 호환성 `FAIL=1`, 입력 또는 구성 오류 `=2`다. 보고서가 `PASS`인 경우에만 Story DNA 생성 단계로 진행한다.

## 테스트

```bash
python -m venv .venv
.venv/bin/python -m pip install 'pip>=26.2'
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/mypy VALIDATORS
.venv/bin/ruff check .
```

## GitHub 운영

모든 변경은 `main`에서 분기한 브랜치와 Pull Request를 통해 반영한다. CI의 Python 3.11·3.14 검증이 모두 통과해야 병합할 수 있으며 Squash Merge를 기본으로 사용한다. 자세한 운영 절차는 [GitHub 운영 가이드](docs/04-deploy/github-operations.md)를 따른다.

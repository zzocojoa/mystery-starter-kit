"""Compatibility Report 생성 CLI."""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NoReturn

from VALIDATORS.channel_validation import validate_reaction_ratio
from VALIDATORS.compatibility import append_errors, evaluate_compatibility
from VALIDATORS.exceptions import ConfigurationError, StarterKitError
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.models import CompatibilityReport
from VALIDATORS.schema_validation import collect_schema_errors


def build_parser() -> argparse.ArgumentParser:
    """호환성 검증 명령행 인자를 정의한다."""
    parser = argparse.ArgumentParser(
        prog="mystery-compat",
        description="Story 생성 전에 Production Standard와 Channel DNA 호환성을 판정합니다.",
    )
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--defaults", type=Path, required=True)
    parser.add_argument("--channel", type=Path, required=True)
    parser.add_argument("--contract-schema", type=Path, required=True)
    parser.add_argument("--defaults-schema", type=Path, required=True)
    parser.add_argument("--channel-schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def raise_for_configuration_schema_errors(
    errors: Sequence[Mapping[str, object]],
    source: str,
) -> None:
    """계약 또는 기본값 Schema 오류를 실행 구성 오류로 변환한다."""
    if not errors:
        return

    details = [
        {
            "code": error.get("code"),
            "message": error.get("message"),
            "context": error.get("context"),
        }
        for error in errors
    ]
    raise ConfigurationError(
        f"실행 구성 문서가 Schema를 통과하지 못했습니다: source={source}, "
        f"errors={json.dumps(details, ensure_ascii=False)}"
    )


def evaluate_compatibility_documents(
    contract: Mapping[str, object],
    defaults: Mapping[str, object],
    channel: Mapping[str, object],
    contract_schema: Mapping[str, object],
    defaults_schema: Mapping[str, object],
    channel_schema: Mapping[str, object],
    contract_source: str,
    defaults_source: str,
    channel_source: str,
) -> CompatibilityReport:
    """구성 Schema와 Channel 의미 규칙을 포함한 호환성 보고서를 만든다."""
    contract_schema_errors = collect_schema_errors(
        contract,
        contract_schema,
        contract_source,
    )
    defaults_schema_errors = collect_schema_errors(
        defaults,
        defaults_schema,
        defaults_source,
    )
    raise_for_configuration_schema_errors(contract_schema_errors, contract_source)
    raise_for_configuration_schema_errors(defaults_schema_errors, defaults_source)

    report = evaluate_compatibility(contract, defaults, channel)
    channel_schema_errors = collect_schema_errors(
        channel,
        channel_schema,
        channel_source,
    )
    return append_errors(
        report,
        channel_schema_errors + validate_reaction_ratio(channel),
    )


def run_cli(argv: Sequence[str]) -> int:
    """명령행 입력을 실행하고 PASS는 0, FAIL은 1, 구성 오류는 2를 반환한다."""
    parser = build_parser()
    arguments = parser.parse_args(argv)

    try:
        contract = load_json_object(arguments.contract)
        defaults = load_json_object(arguments.defaults)
        channel = load_json_object(arguments.channel)
        contract_schema = load_json_object(arguments.contract_schema)
        defaults_schema = load_json_object(arguments.defaults_schema)
        channel_schema = load_json_object(arguments.channel_schema)

        final_report = evaluate_compatibility_documents(
            contract,
            defaults,
            channel,
            contract_schema,
            defaults_schema,
            channel_schema,
            str(arguments.contract),
            str(arguments.defaults),
            str(arguments.channel),
        )
        write_json_object(arguments.output, final_report)
    except StarterKitError as error:
        print(str(error), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "compatibility": final_report["compatibility"],
                "report": str(arguments.output),
                "error_count": len(final_report["errors"]),
            },
            ensure_ascii=False,
        )
    )
    return 0 if final_report["compatibility"] == "PASS" else 1


def main() -> NoReturn:
    """설치된 Console Script 진입점."""
    raise SystemExit(run_cli(tuple(sys.argv[1:])))


if __name__ == "__main__":
    main()

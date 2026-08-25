"""JSON Schema 기반 구조 검증."""

from collections.abc import Mapping, Sequence
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import CompatibilityError


def format_json_path(parts: Sequence[str | int]) -> str:
    """JSON 경로 조각을 사람이 읽을 수 있는 경로로 변환한다."""
    if not parts:
        return "$"

    rendered_parts: list[str] = []
    for part in parts:
        if isinstance(part, int):
            rendered_parts.append(f"[{part}]")
        else:
            separator = "" if not rendered_parts else "."
            rendered_parts.append(f"{separator}{part}")
    return "$" + "".join(rendered_parts)


def collect_schema_errors(
    document: Mapping[str, object],
    schema: Mapping[str, object],
    source: str,
) -> list[CompatibilityError]:
    """Schema 위반을 정렬된 호환성 오류 목록으로 반환한다."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ConfigurationError(
            f"JSON Schema 자체가 올바르지 않습니다: source={source}, detail={error.message}"
        ) from error

    validator = Draft202012Validator(schema)
    validation_errors = sorted(
        validator.iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )

    return [
        CompatibilityError(
            code="SCHEMA_VALIDATION_ERROR",
            message=error.message,
            context={
                "source": source,
                "path": format_json_path(
                    cast(Sequence[str | int], tuple(error.absolute_path))
                ),
                "validator": str(error.validator),
            },
        )
        for error in validation_errors
    ]

"""Project Constraint를 Variation Catalog 기준으로 Fail-closed 컴파일한다."""

from collections.abc import Mapping
from copy import deepcopy

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

ORDERED_LIMITS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "production_complexity": (
        "max_production_complexity",
        "",
        ("LOW", "MEDIUM", "HIGH", "EXTREME"),
    ),
    "special_effect_level": (
        "max_special_effect_level",
        "",
        ("NONE", "LOW", "MEDIUM", "HIGH"),
    ),
    "graphic_violence": (
        "max_graphic_violence",
        "",
        ("NONE", "IMPLIED", "NON_GRAPHIC", "GRAPHIC"),
    ),
}
NUMERIC_LIMITS: dict[str, tuple[str, str]] = {
    "location_count": ("max_locations", "LOCATIONS_"),
    "major_character_count": ("max_major_characters", "MAJOR_"),
}


def constraint_error(code: str, detail: str) -> ConfigurationError:
    """안정적인 오류 코드를 포함한 Constraint 구성 오류를 반환한다."""
    return ConfigurationError(f"{code}: {detail}")


def catalog_dimensions(catalog: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    """Catalog Dimension Enum을 엄격하게 읽는다."""
    raw_dimensions = catalog.get("dimensions")
    if not isinstance(raw_dimensions, Mapping):
        raise constraint_error(
            "PROJECT_CONSTRAINT_FIELD_UNKNOWN", "Variation Catalog dimensions가 없습니다."
        )
    dimensions: dict[str, tuple[str, ...]] = {}
    for field, raw_values in raw_dimensions.items():
        if (
            not isinstance(field, str)
            or not isinstance(raw_values, list)
            or not raw_values
            or not all(isinstance(value, str) for value in raw_values)
        ):
            raise constraint_error(
                "PROJECT_CONSTRAINT_VALUE_INVALID",
                f"Catalog Dimension이 손상되었습니다: field={field!r}",
            )
        dimensions[field] = tuple(raw_values)
    return dimensions


def projection_dimensions(contract: Mapping[str, object]) -> set[str]:
    """Projection Contract에 명시된 모든 Dimension을 반환한다."""
    dimensions = contract.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise constraint_error(
            "PROJECT_CONSTRAINT_FIELD_UNKNOWN", "Candidate Projection dimensions가 없습니다."
        )
    return {field for field in dimensions if isinstance(field, str)}


def normalized_rules(
    raw_rules: object,
    expected_operator: str,
    dimensions: Mapping[str, tuple[str, ...]],
    projected: set[str],
) -> list[dict[str, object]]:
    """중복 Rule을 Field별 하나로 정규화하고 Enum을 검증한다."""
    if not isinstance(raw_rules, list):
        raise constraint_error(
            "PROJECT_CONSTRAINT_OPERATOR_INVALID", "Constraint Rule 배열이 필요합니다."
        )
    grouped: dict[str, set[str]] = {}
    reasons: dict[str, set[str]] = {}
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, Mapping):
            raise constraint_error(
                "PROJECT_CONSTRAINT_OPERATOR_INVALID", "Constraint Rule 객체가 필요합니다."
            )
        field = raw_rule.get("field")
        operator = raw_rule.get("operator")
        values = raw_rule.get("values")
        if not isinstance(field, str) or field not in dimensions or field not in projected:
            raise constraint_error(
                "PROJECT_CONSTRAINT_FIELD_UNKNOWN", f"알 수 없는 field입니다: field={field!r}"
            )
        if operator != expected_operator:
            raise constraint_error(
                "PROJECT_CONSTRAINT_OPERATOR_INVALID",
                f"Operator가 목록과 맞지 않습니다: field={field}, operator={operator!r}",
            )
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) for value in values)
        ):
            raise constraint_error(
                "PROJECT_CONSTRAINT_VALUE_INVALID", f"값 배열이 잘못되었습니다: field={field}"
            )
        invalid = sorted(set(values) - set(dimensions[field]))
        if invalid:
            raise constraint_error(
                "PROJECT_CONSTRAINT_VALUE_INVALID",
                f"Catalog에 없는 값입니다: field={field}, values={invalid}",
            )
        current = grouped.get(field)
        value_set = set(values)
        grouped[field] = (
            value_set
            if current is None
            else current & value_set
            if expected_operator == "IN"
            else current | value_set
        )
        reason = raw_rule.get("reason")
        if isinstance(reason, str):
            reasons.setdefault(field, set()).add(reason)
    empty = sorted(field for field, values in grouped.items() if not values)
    if empty:
        raise constraint_error(
            "PROJECT_CONSTRAINT_UNSATISFIABLE",
            f"동시에 만족할 수 없는 IN Rule입니다: fields={empty}",
        )
    return [
        {
            "field": field,
            "operator": expected_operator,
            "values": sorted(grouped[field]),
            **({"reason": " / ".join(sorted(reasons[field]))} if reasons.get(field) else {}),
        }
        for field in sorted(grouped)
    ]


def numeric_suffix(value: str, prefix: str) -> int | None:
    """제작 규모 Enum의 정수 Suffix를 반환한다."""
    suffix = value.removeprefix(prefix)
    return int(suffix) if value.startswith(prefix) and suffix.isdigit() else None


def value_within_limits(
    field: str,
    value: str,
    limits: Mapping[str, object],
) -> bool:
    """Dimension 값이 Production Limit 안인지 반환한다."""
    numeric = NUMERIC_LIMITS.get(field)
    if numeric is not None:
        limit_name, prefix = numeric
        parsed = numeric_suffix(value, prefix)
        maximum = limits.get(limit_name)
        return parsed is not None and isinstance(maximum, int) and parsed <= maximum
    ordered = ORDERED_LIMITS.get(field)
    if ordered is not None:
        limit_name, _prefix, order = ordered
        maximum = limits.get(limit_name)
        return (
            isinstance(maximum, str)
            and value in order
            and maximum in order
            and order.index(value) <= order.index(maximum)
        )
    if field == "child_actor_use":
        return limits.get("allow_child_actor") is True or value == "NONE"
    if field == "vehicle_scene":
        return limits.get("allow_moving_vehicle") is True or value != "MOVING"
    return True


def validate_rule_conflicts(
    must_use: list[dict[str, object]],
    must_not_use: list[dict[str, object]],
    limits: Mapping[str, object],
    dimensions: Mapping[str, tuple[str, ...]],
) -> None:
    """상충 Rule과 Production Limit으로 불가능한 Rule을 차단한다."""
    required: dict[str, set[object]] = {}
    forbidden: dict[str, set[object]] = {}
    for rule in must_use:
        values = rule.get("values")
        if isinstance(values, list):
            required[str(rule["field"])] = set(values)
    for rule in must_not_use:
        values = rule.get("values")
        if isinstance(values, list):
            forbidden[str(rule["field"])] = set(values)
    conflicts = sorted(
        field
        for field, values in required.items()
        if values and values <= forbidden.get(field, set())
    )
    if conflicts:
        raise constraint_error(
            "PROJECT_CONSTRAINT_CONFLICT",
            f"필수값이 모두 금지되었습니다: fields={conflicts}",
        )
    impossible: list[str] = []
    for field, catalog_values in dimensions.items():
        candidate_values = required.get(field, set(catalog_values)) - forbidden.get(field, set())
        if any(value_within_limits(field, str(value), limits) for value in candidate_values):
            continue
        impossible.append(field)
    if impossible:
        raise constraint_error(
            "PROJECT_CONSTRAINT_UNSATISFIABLE",
            f"Production Limit과 충돌합니다: fields={impossible}",
        )


def compile_project_constraints(
    document: Mapping[str, object],
    catalog: Mapping[str, object],
    projection_contract: Mapping[str, object],
) -> dict[str, object]:
    """Project Constraint를 검증·정규화한 불변 문서로 컴파일한다."""
    dimensions = catalog_dimensions(catalog)
    projected = projection_dimensions(projection_contract)
    must_use = normalized_rules(document.get("must_use"), "IN", dimensions, projected)
    must_not_use = normalized_rules(document.get("must_not_use"), "NOT_IN", dimensions, projected)
    limits = document.get("production_limits")
    if not isinstance(limits, Mapping):
        raise constraint_error(
            "PROJECT_CONSTRAINT_UNSATISFIABLE", "production_limits 객체가 없습니다."
        )
    validate_rule_conflicts(must_use, must_not_use, limits, dimensions)
    return {
        **deepcopy(dict(document)),
        "must_use": must_use,
        "must_not_use": must_not_use,
        "production_limits": deepcopy(dict(limits)),
    }


def project_constraint_compiler_issues(
    document: Mapping[str, object],
    catalog: Mapping[str, object],
    projection_contract: Mapping[str, object],
) -> list[ValidationIssue]:
    """Constraint Compile 실패를 Gate Issue로 변환한다."""
    try:
        compile_project_constraints(document, catalog, projection_contract)
    except ConfigurationError as error:
        message = str(error)
        code = message.split(":", 1)[0]
        return [
            ValidationIssue(
                severity="ERROR",
                code=code,
                message=message,
                artifact="00_PROJECT/project_constraints.json",
                context={},
            )
        ]
    return []

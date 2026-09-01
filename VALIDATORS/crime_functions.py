"""Channel Policy가 소유하는 범죄 Development Function 필수 집합."""

from collections.abc import Mapping
from typing import cast

from VALIDATORS.models import ValidationIssue

RELATIONSHIP_CRIMES = frozenset({"DATING_VIOLENCE", "DOMESTIC_VIOLENCE"})
DEFAULT_DEVELOPMENT_FUNCTIONS: Mapping[str, tuple[str, ...]] = {
    "MURDER": (
        "HARM_OR_DANGER_RECOGNITION",
        "INVOLVEMENT_OR_SUSPICION",
        "MOTIVE_AND_RESPONSIBILITY",
        "EVENT_RECONSTRUCTION",
    ),
    "LIBERTY_CRIME": (
        "LIBERTY_DEPRIVATION",
        "THREAT_AND_CHOICE_CONSTRAINT",
        "RESPONSE_OR_DISCOVERY",
        "HARM_OUTCOME",
    ),
    "RELATIONAL_VIOLENCE": (
        "VIOLENCE_OR_THREAT",
        "RELATIONSHIP_AND_POWER",
        "RESPONSE_BARRIER",
        "VIOLENCE_OUTCOME",
    ),
    "ACCESS_CRIME": (
        "REPEATED_ACCESS_OR_INTRUSION",
        "SAFETY_COLLAPSE",
        "SAFETY_RESPONSE",
        "OFFENDER_RESPONSIBILITY",
    ),
}


def development_families(primary_crime: object, action_type: object) -> set[str]:
    """중첩 가능한 범죄 분류를 서사 기능 Family 집합으로 변환한다."""
    families: set[str] = set()
    if primary_crime == "MURDER" or action_type == "MURDER":
        families.add("MURDER")
    if primary_crime in {"KIDNAPPING", "CONFINEMENT"} or action_type in {
        "KIDNAPPING",
        "CONFINEMENT",
    }:
        families.add("LIBERTY_CRIME")
    if primary_crime in {"ASSAULT", *RELATIONSHIP_CRIMES} or action_type == "ASSAULT":
        families.add("RELATIONAL_VIOLENCE")
    if primary_crime in {"STALKING", "HOME_INVASION"} or action_type in {
        "STALKING",
        "HOME_INVASION",
    }:
        families.add("ACCESS_CRIME")
    return families


def policy_development_functions(
    policy: Mapping[str, object],
    primary_crime: object,
    action_type: object,
) -> set[str]:
    """범죄 유형에 필요한 비순차 서사 기능을 반환한다."""
    definitions = policy.get("development_functions_by_family")
    required: set[str] = set()
    for family in development_families(primary_crime, action_type):
        values = definitions.get(family) if isinstance(definitions, Mapping) else None
        if isinstance(values, list) and all(isinstance(item, str) for item in values):
            required.update(cast(list[str], values))
        else:
            required.update(DEFAULT_DEVELOPMENT_FUNCTIONS[family])
    return required


def development_function_records(event: Mapping[str, object]) -> list[Mapping[str, object]]:
    """사건의 Development Function 객체 배열만 반환한다."""
    value = event.get("development_functions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def required_development_function_map(
    policy: Mapping[str, object],
    event: Mapping[str, object],
) -> dict[str, str]:
    """Policy 필수 Function Type을 Canonical Function ID에 연결한다."""
    required_types = policy_development_functions(
        policy,
        event.get("primary_crime"),
        event.get("core_action_type"),
    )
    return {
        cast(str, record["development_function_id"]): cast(str, record["function_type"])
        for record in development_function_records(event)
        if isinstance(record.get("development_function_id"), str)
        and record.get("function_type") in required_types
    }


def development_function_issues(
    policy: Mapping[str, object],
    event: Mapping[str, object],
    artifact: str,
) -> list[ValidationIssue]:
    """필수 기능 누락·완화·중복을 Channel Policy 기준으로 검사한다."""
    records = development_function_records(event)
    required_types = policy_development_functions(
        policy,
        event.get("primary_crime"),
        event.get("core_action_type"),
    )
    ids = [record.get("development_function_id") for record in records]
    types = [record.get("function_type") for record in records]
    issues: list[ValidationIssue] = []
    duplicated_ids = sorted(
        {value for value in ids if isinstance(value, str) and ids.count(value) > 1}
    )
    duplicated_required_types = sorted(
        {
            value
            for value in types
            if isinstance(value, str)
            and value in required_types
            and types.count(value) > 1
        }
    )
    present_types = {value for value in types if isinstance(value, str)}
    missing_types = sorted(required_types - present_types)
    weakened_types = sorted(
        cast(str, record["function_type"])
        for record in records
        if record.get("function_type") in required_types and record.get("required") is not True
    )
    problem_specs: tuple[tuple[str, str, dict[str, object], bool], ...] = (
        (
            "CRIME_DEVELOPMENT_FUNCTION_MISSING",
            "Channel Policy가 요구하는 Development Function이 누락되었습니다.",
            {"missing_functions": missing_types},
            bool(missing_types),
        ),
        (
            "CRIME_DEVELOPMENT_FUNCTION_REQUIRED_WEAKENED",
            "Channel 필수 Development Function을 required=false로 완화할 수 없습니다.",
            {"function_types": weakened_types},
            bool(weakened_types),
        ),
        (
            "CRIME_DEVELOPMENT_FUNCTION_ID_DUPLICATED",
            "Development Function ID는 사건 안에서 중복될 수 없습니다.",
            {"development_function_ids": duplicated_ids},
            bool(duplicated_ids),
        ),
        (
            "CRIME_DEVELOPMENT_FUNCTION_AMBIGUOUS",
            "필수 Function Type은 사건 안에서 정확히 하나의 Canonical ID를 가져야 합니다.",
            {"function_types": duplicated_required_types},
            bool(duplicated_required_types),
        ),
    )
    for code, message, context, applies in problem_specs:
        if applies:
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code=code,
                    message=message,
                    artifact=artifact,
                    context=context,
                )
            )
    return issues

"""Versioned 범죄 피해 SSOT와 호환 필드를 검증한다."""

from collections.abc import Mapping, Sequence
from typing import cast

from VALIDATORS.models import ValidationIssue

HARM_TIMINGS = frozenset({"IMMEDIATE", "LASTING", "OUTCOME", "COMPOUND"})
ACTION_HARM_REQUIREMENTS: Mapping[str, frozenset[str]] = {
    "MURDER": frozenset({"FATALITY"}),
    "KIDNAPPING": frozenset({"LIBERTY_DEPRIVATION", "COMPOUND_HARM"}),
    "CONFINEMENT": frozenset({"LIBERTY_DEPRIVATION", "COMPOUND_HARM"}),
    "ASSAULT": frozenset({"BODILY_INJURY", "COMPOUND_HARM"}),
    "STALKING": frozenset(
        {"SAFETY_COLLAPSE", "THREAT_OR_TRAUMA", "COMPOUND_HARM"}
    ),
    "HOME_INVASION": frozenset(
        {"SAFETY_COLLAPSE", "THREAT_OR_TRAUMA", "BODILY_INJURY", "COMPOUND_HARM"}
    ),
}
DIRECT_ACTION_HARM_REQUIREMENTS: Mapping[str, frozenset[str]] = {
    "MURDER": frozenset({"FATALITY"}),
    "KIDNAPPING": frozenset({"LIBERTY_DEPRIVATION"}),
    "CONFINEMENT": frozenset({"LIBERTY_DEPRIVATION"}),
    "ASSAULT": frozenset({"BODILY_INJURY"}),
    "STALKING": frozenset({"SAFETY_COLLAPSE", "THREAT_OR_TRAUMA"}),
    "HOME_INVASION": frozenset(
        {"SAFETY_COLLAPSE", "THREAT_OR_TRAUMA", "BODILY_INJURY"}
    ),
}
CRIME_ALLOWED_HARMS: Mapping[str, frozenset[str]] = {
    "MURDER": frozenset(
        {"FATALITY", "BODILY_INJURY", "THREAT_OR_TRAUMA", "COMPOUND_HARM"}
    ),
    "KIDNAPPING": frozenset(
        {
            "LIBERTY_DEPRIVATION",
            "BODILY_INJURY",
            "THREAT_OR_TRAUMA",
            "COMPOUND_HARM",
        }
    ),
    "CONFINEMENT": frozenset(
        {
            "LIBERTY_DEPRIVATION",
            "BODILY_INJURY",
            "THREAT_OR_TRAUMA",
            "COMPOUND_HARM",
        }
    ),
    "ASSAULT": frozenset(
        {"BODILY_INJURY", "THREAT_OR_TRAUMA", "COMPOUND_HARM"}
    ),
    "STALKING": frozenset(
        {
            "SAFETY_COLLAPSE",
            "THREAT_OR_TRAUMA",
            "BODILY_INJURY",
            "COMPOUND_HARM",
        }
    ),
    "HOME_INVASION": frozenset(
        {
            "SAFETY_COLLAPSE",
            "THREAT_OR_TRAUMA",
            "BODILY_INJURY",
            "LIBERTY_DEPRIVATION",
            "COMPOUND_HARM",
        }
    ),
    "DATING_VIOLENCE": frozenset(
        {
            "BODILY_INJURY",
            "LIBERTY_DEPRIVATION",
            "SAFETY_COLLAPSE",
            "THREAT_OR_TRAUMA",
            "COMPOUND_HARM",
        }
    ),
    "DOMESTIC_VIOLENCE": frozenset(
        {
            "BODILY_INJURY",
            "LIBERTY_DEPRIVATION",
            "SAFETY_COLLAPSE",
            "THREAT_OR_TRAUMA",
            "COMPOUND_HARM",
        }
    ),
}


def mapping_records(document: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    """객체 배열만 반환한다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_values(document: Mapping[str, object], field: str) -> list[str]:
    """문자열 배열만 반환한다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def ordered_unique(values: list[str]) -> list[str]:
    """첫 등장 순서를 보존한 고유 문자열 목록을 반환한다."""
    return list(dict.fromkeys(values))


def summaries_for_timings(
    harms: Sequence[Mapping[str, object]],
    timings: frozenset[str],
) -> list[str]:
    """지정 Timing에 해당하는 피해 요약을 순서대로 반환한다."""
    return [
        cast(str, harm["summary"])
        for harm in harms
        if harm.get("timing") in timings and isinstance(harm.get("summary"), str)
    ]


def derived_harm_fields(harms: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """구조화 피해에서 Legacy 호환 필드를 결정론적으로 파생한다."""
    harm_ids = [
        cast(str, harm["harm_id"])
        for harm in harms
        if isinstance(harm.get("harm_id"), str)
    ]
    classifications = ordered_unique(
        [
            cast(str, harm["classification"])
            for harm in harms
            if isinstance(harm.get("classification"), str)
        ]
    )
    immediate = summaries_for_timings(harms, frozenset({"IMMEDIATE"}))
    outcome = summaries_for_timings(harms, frozenset({"OUTCOME", "COMPOUND"}))
    lasting = summaries_for_timings(harms, frozenset({"LASTING"}))
    all_summaries = [
        cast(str, harm["summary"])
        for harm in harms
        if isinstance(harm.get("summary"), str)
    ]
    immediate_summary = " / ".join(immediate or outcome or all_summaries)
    lasting_summary = " / ".join(lasting or outcome or immediate or all_summaries)
    return {
        "harm_ids": harm_ids,
        "harm_classifications": classifications,
        "immediate_harm": immediate_summary,
        "lasting_harm": lasting_summary,
    }


def harm_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """구조화 피해 문제를 표준 Issue로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def structured_harm_issues(
    event: Mapping[str, object],
    artifact: str,
    victim_reference_field: str,
    declared_victims: set[str],
    required: bool,
) -> list[ValidationIssue]:
    """피해 ID·분류·피해자 결속·Legacy 파생 필드를 검증한다."""
    harms = mapping_records(event, "harms")
    if not harms:
        if required:
            return [
                harm_issue(
                    "MULTI_HARM_REQUIRED",
                    "새 범죄 계약 Version에는 구조화된 harms[]가 필요합니다.",
                    artifact,
                    {},
                )
            ]
        return []
    issues: list[ValidationIssue] = []
    harm_ids = [harm.get("harm_id") for harm in harms]
    duplicated_ids = sorted(
        {
            value
            for value in harm_ids
            if isinstance(value, str) and harm_ids.count(value) > 1
        }
    )
    if duplicated_ids:
        issues.append(
            harm_issue(
                "HARM_ID_DUPLICATED",
                "Harm ID는 사건 안에서 중복될 수 없습니다.",
                artifact,
                {"harm_ids": duplicated_ids},
            )
        )
    action_type = event.get("core_action_type")
    primary_crime = event.get("primary_crime")
    related_crimes = string_values(event, "related_crimes")
    applicable_crimes = [str(action_type), str(primary_crime), *related_crimes]
    allowed = frozenset().union(
        *(CRIME_ALLOWED_HARMS.get(crime, frozenset()) for crime in applicable_crimes)
    )
    required_any = DIRECT_ACTION_HARM_REQUIREMENTS.get(
        str(action_type),
        frozenset(),
    )
    classifications = {
        cast(str, harm["classification"])
        for harm in harms
        if isinstance(harm.get("classification"), str)
    }
    incompatible = sorted(classifications - allowed) if allowed else sorted(classifications)
    if incompatible or not classifications.intersection(required_any):
        issues.append(
            harm_issue(
                "HARM_CLASSIFICATION_ACTION_MISMATCH",
                "구조화 피해 분류가 실제 범죄 행동과 인과적으로 맞지 않습니다.",
                artifact,
                {
                    "core_action_type": action_type,
                    "primary_crime": primary_crime,
                    "related_crimes": related_crimes,
                    "incompatible_classifications": incompatible,
                    "required_any_of": sorted(required_any),
                },
            )
        )
    timings = {
        cast(str, harm["timing"])
        for harm in harms
        if isinstance(harm.get("timing"), str)
    }
    if not timings.intersection({"IMMEDIATE", "OUTCOME", "COMPOUND"}):
        issues.append(
            harm_issue(
                "HARM_OUTCOME_REQUIRED",
                "피해 집합에는 최소 한 개의 즉시·결과·복합 피해가 필요합니다.",
                artifact,
                {"timings": sorted(timings)},
            )
        )
    invalid_compound_harms = sorted(
        str(harm.get("harm_id"))
        for harm in harms
        if harm.get("classification") == "COMPOUND_HARM"
        and harm.get("timing") != "COMPOUND"
    )
    if invalid_compound_harms:
        issues.append(
            harm_issue(
                "HARM_COMPOUND_OUTCOME_INVALID",
                "COMPOUND_HARM은 복합 결과를 나타내는 COMPOUND timing이 필요합니다.",
                artifact,
                {"harm_ids": invalid_compound_harms},
            )
        )
    bound_victims: set[str] = set()
    invalid_bindings: list[dict[str, object]] = []
    for harm in harms:
        references = string_values(harm, victim_reference_field)
        bound_victims.update(references)
        if not references or not set(references).issubset(declared_victims):
            invalid_bindings.append(
                {
                    "harm_id": harm.get("harm_id"),
                    "victim_references": references,
                }
            )
    if invalid_bindings:
        issues.append(
            harm_issue(
                "HARM_VICTIM_BINDING_INVALID",
                "각 Harm은 선언된 피해자에 하나 이상 결속되어야 합니다.",
                artifact,
                {"invalid_bindings": invalid_bindings},
            )
        )
    missing_victims = sorted(declared_victims - bound_victims)
    if missing_victims:
        issues.append(
            harm_issue(
                "HARM_VICTIM_COVERAGE_MISSING",
                "모든 선언 피해자는 최소 한 개 Harm에 결속되어야 합니다.",
                artifact,
                {"victim_references": missing_victims},
            )
        )
    expected_fields = derived_harm_fields(harms)
    mismatches = {
        field: {"expected": expected, "actual": event.get(field)}
        for field, expected in expected_fields.items()
        if event.get(field) != expected
    }
    if mismatches:
        issues.append(
            harm_issue(
                "HARM_COMPATIBILITY_FIELDS_MISMATCH",
                "Legacy 피해 호환 필드는 harms[]에서 결정론적으로 파생되어야 합니다.",
                artifact,
                {"mismatches": mismatches},
            )
        )
    return issues


def bind_harm_records(
    harms: list[Mapping[str, object]],
    role_bindings: Mapping[str, str],
) -> list[dict[str, object]]:
    """Brief의 피해자 Role Slot을 Contract의 Character ID로 결속한다."""
    return [
        {
            "harm_id": harm.get("harm_id"),
            "classification": harm.get("classification"),
            "timing": harm.get("timing"),
            "victim_ids": [
                role_bindings[slot]
                for slot in string_values(harm, "victim_role_slots")
                if slot in role_bindings
            ],
            "summary": harm.get("summary"),
        }
        for harm in harms
    ]

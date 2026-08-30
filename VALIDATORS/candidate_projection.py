"""승인 Candidate Dimension의 하위 Story Artifact 투영을 검증한다."""

from collections.abc import Mapping

from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.models import ValidationIssue


def projection_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Candidate Projection 오류를 표준 형식으로 반환한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="STANDARD/candidate_projection_contract.json",
        context=context,
    )


def approved_selection(variations: Mapping[str, object]) -> Mapping[str, object] | None:
    """승인 Candidate의 Selection을 반환한다."""
    approved_id = variations.get("approved_candidate_id")
    candidates = variations.get("candidates")
    if not isinstance(approved_id, str) or not isinstance(candidates, list):
        return None
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or candidate.get("candidate_id") != approved_id:
            continue
        selection = candidate.get("selection")
        return selection if isinstance(selection, Mapping) else None
    return None


def path_value(document: Mapping[str, object], path: str) -> object:
    """점 표기 JSON Path의 값을 읽고 누락 시 None을 반환한다."""
    current: object = document
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def target_matches(expected: object, actual: object, match: object) -> bool:
    """Projection Target의 비교 방식을 적용한다."""
    if match == "EQUALS":
        return actual == expected
    if match == "CONTAINS":
        return isinstance(actual, list) and expected in actual
    return False


def derived_final_dimension(
    field: str,
    artifacts: Mapping[str, object],
) -> tuple[object, str] | None:
    """정규화된 Story Artifact에서 제작 수량 Dimension을 계산한다."""
    if field == "location_count":
        actual_timeline = artifacts.get("actual_timeline")
        events = actual_timeline.get("events") if isinstance(actual_timeline, Mapping) else None
        if not isinstance(events, list):
            return None
        locations = {
            event.get("location_id")
            for event in events
            if isinstance(event, Mapping) and isinstance(event.get("location_id"), str)
        }
        return f"LOCATIONS_{len(locations)}", "actual_timeline"
    if field == "major_character_count":
        characters = artifacts.get("characters")
        records = characters.get("characters") if isinstance(characters, Mapping) else None
        if not isinstance(records, list):
            return None
        return f"MAJOR_{len(records)}", "characters"
    return None


def final_production_limit_issues(
    constraints: Mapping[str, object],
    artifacts: Mapping[str, object],
) -> list[ValidationIssue]:
    """최종 Story의 장소와 주요 인물 수를 Production Limit에 다시 적용한다."""
    limits = constraints.get("production_limits")
    if not isinstance(limits, Mapping):
        return []
    issues: list[ValidationIssue] = []
    for field, limit_name in (
        ("location_count", "max_locations"),
        ("major_character_count", "max_major_characters"),
    ):
        derived = derived_final_dimension(field, artifacts)
        maximum = limits.get(limit_name)
        if derived is None or not isinstance(maximum, int):
            continue
        value, artifact_name = derived
        if not isinstance(value, str):
            continue
        count_text = value.rsplit("_", maxsplit=1)[-1]
        if count_text.isdigit() and int(count_text) <= maximum:
            continue
        issues.append(
            projection_issue(
                "PROJECT_CONSTRAINT_FINAL_ARTIFACT_MISMATCH",
                "최종 Story Artifact가 Production Limit을 초과했습니다.",
                {
                    "dimension": field,
                    "artifact": artifact_name,
                    "actual": value,
                    "maximum": maximum,
                },
            )
        )
    return issues


def validate_projection_contract_coverage(
    catalog: Mapping[str, object],
    contract: Mapping[str, object],
) -> list[ValidationIssue]:
    """Catalog의 모든 Dimension이 정확히 분류되었는지 검증한다."""
    catalog_dimensions = catalog.get("dimensions")
    contract_dimensions = contract.get("dimensions")
    if not isinstance(catalog_dimensions, Mapping) or not isinstance(contract_dimensions, Mapping):
        return [
            projection_issue(
                "CANDIDATE_DIMENSION_UNMAPPED",
                "Catalog 또는 Projection Dimension 객체가 없습니다.",
                {},
            )
        ]
    missing = sorted(set(catalog_dimensions) - set(contract_dimensions))
    if not missing:
        return []
    return [
        projection_issue(
            "CANDIDATE_DIMENSION_UNMAPPED",
            "Variation Dimension에 Projection 분류가 없습니다.",
            {"dimensions": missing},
        )
    ]


def validate_approved_candidate_projection(
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    contract: Mapping[str, object],
    artifacts: Mapping[str, object],
) -> list[ValidationIssue]:
    """승인 Selection이 현재 Gate까지 생성된 대상 Artifact에 유지되는지 검증한다."""
    selection = approved_selection(variations)
    dimensions = contract.get("dimensions")
    if selection is None or not isinstance(dimensions, Mapping):
        return [
            projection_issue(
                "CANDIDATE_DIMENSION_UNMAPPED",
                "승인 Candidate 또는 Projection Contract가 없습니다.",
                {},
            )
        ]
    issues: list[ValidationIssue] = []
    for field, expected in selection.items():
        definition = dimensions.get(field)
        if not isinstance(field, str) or not isinstance(definition, Mapping):
            issues.append(
                projection_issue(
                    "CANDIDATE_DIMENSION_UNMAPPED",
                    "승인 Candidate Dimension에 Mapping이 없습니다.",
                    {"dimension": field},
                )
            )
            continue
        classification = definition.get("classification")
        engine_version = production_config.get("variation_engine_version")
        if (
            field == "genre"
            and isinstance(engine_version, str)
            and parse_semantic_version(engine_version) >= (2, 0, 0)
        ):
            if expected != production_config.get("genre"):
                issues.append(
                    projection_issue(
                        "APPROVED_CANDIDATE_PROJECTION_MISMATCH",
                        "v2 Candidate Genre는 Production Config와 같아야 합니다.",
                        {
                            "dimension": field,
                            "expected": production_config.get("genre"),
                            "actual": expected,
                        },
                    )
                )
            continue
        if classification != "PROJECTED":
            continue
        targets = definition.get("targets")
        if not isinstance(targets, list):
            issues.append(
                projection_issue(
                    "CANDIDATE_DIMENSION_UNMAPPED",
                    "PROJECTED Dimension에 Target이 없습니다.",
                    {"dimension": field},
                )
            )
            continue
        for target in targets:
            if not isinstance(target, Mapping):
                continue
            artifact_name = target.get("artifact")
            json_path = target.get("json_path")
            if not isinstance(artifact_name, str) or artifact_name not in artifacts:
                continue
            artifact = artifacts[artifact_name]
            if not isinstance(artifact, Mapping) or not isinstance(json_path, str):
                continue
            actual = path_value(artifact, json_path)
            if target_matches(expected, actual, target.get("match")):
                continue
            issues.append(
                projection_issue(
                    "APPROVED_CANDIDATE_PROJECTION_MISMATCH",
                    "승인 Candidate 값이 하위 Artifact에서 변경되었습니다.",
                    {
                        "dimension": field,
                        "artifact": artifact_name,
                        "json_path": json_path,
                        "expected": expected,
                        "actual": actual,
                    },
                )
            )
    return issues


def validate_final_story_constraints(
    constraints: Mapping[str, object],
    variations: Mapping[str, object],
    contract: Mapping[str, object],
    artifacts: Mapping[str, object],
) -> list[ValidationIssue]:
    """Candidate 단계 Constraint가 최종 Story Artifact에서도 유지되는지 검증한다."""
    selection = approved_selection(variations)
    if selection is None:
        return []
    issues = final_production_limit_issues(constraints, artifacts)
    for list_name, should_match in (("must_use", True), ("must_not_use", False)):
        rules = constraints.get(list_name)
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            field = rule.get("field")
            values = rule.get("values")
            if not isinstance(field, str) or not isinstance(values, list):
                continue
            dimensions = contract.get("dimensions")
            definition = dimensions.get(field) if isinstance(dimensions, Mapping) else None
            targets = definition.get("targets") if isinstance(definition, Mapping) else None
            if not isinstance(targets, list):
                derived = derived_final_dimension(field, artifacts)
                if derived is None:
                    continue
                actual, derived_artifact_name = derived
                actual_matches = actual in values
                if actual_matches == should_match:
                    continue
                issues.append(
                    projection_issue(
                        "PROJECT_CONSTRAINT_FINAL_ARTIFACT_MISMATCH",
                        "최종 Story Artifact가 Project Constraint를 우회했습니다.",
                        {
                            "dimension": field,
                            "artifact": derived_artifact_name,
                            "actual": actual,
                        },
                    )
                )
                continue
            for target in targets:
                if not isinstance(target, Mapping):
                    continue
                artifact_name = target.get("artifact")
                json_path = target.get("json_path")
                artifact = artifacts.get(artifact_name) if isinstance(artifact_name, str) else None
                if not isinstance(artifact, Mapping) or not isinstance(json_path, str):
                    continue
                actual = path_value(artifact, json_path)
                actual_matches = (
                    actual in values
                    if target.get("match") == "EQUALS"
                    else isinstance(actual, list) and any(value in actual for value in values)
                )
                if actual_matches == should_match:
                    continue
                issues.append(
                    projection_issue(
                        "PROJECT_CONSTRAINT_FINAL_ARTIFACT_MISMATCH",
                        "최종 Story Artifact가 Project Constraint를 우회했습니다.",
                        {"dimension": field, "artifact": artifact_name, "actual": actual},
                    )
                )
    return issues

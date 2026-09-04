"""재연극 계획시간과 Editorial 측정 근거를 방송 Runtime과 분리해 검증한다."""

from collections.abc import Mapping, Sequence
from math import isfinite
from typing import TypedDict, cast

from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.models import Severity, ValidationIssue

REPORT_ARTIFACT = "08_QA/reenactment_export_report.json"
EDITORIAL_ARTIFACT = "08_QA/editorial_review.json"
MEASURED_METHODS = frozenset({"TABLE_READ", "RECORDED_AUDIO"})


class ReenactmentRuntimePlan(TypedDict):
    """Output Profile에 포함된 방송 Segment의 재연극 계획시간."""

    planning_basis: str
    included_segment_ids: list[str]
    excluded_segment_ids: list[str]
    planned_duration_sec: float


def runtime_issue(
    severity: Severity,
    code: str,
    message: str,
    artifact: str,
    context: Mapping[str, object],
) -> ValidationIssue:
    """재연극 Runtime 문제를 공통 Issue 형식으로 만든다."""
    return ValidationIssue(
        severity=severity,
        code=code,
        message=message,
        artifact=artifact,
        context=dict(context),
    )


def records(value: object) -> list[Mapping[str, object]]:
    """객체 배열에서 의미 검증 가능한 항목만 반환한다."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def strings(value: object) -> list[str]:
    """문자열 배열에서 문자열 항목만 반환한다."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]


def finite_number(value: object, allow_zero: bool) -> float | None:
    """Boolean과 비유한 값을 제외한 유효 숫자를 반환한다."""
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not isfinite(value)
        or value < 0
        or (not allow_zero and value == 0)
    ):
        return None
    return float(value)


def profile_filter_values(
    output_profile: Mapping[str, object],
    field: str,
) -> list[str]:
    """Output Profile의 Filter 문자열 목록을 반환한다."""
    filter_contract = output_profile.get("filter_contract")
    if not isinstance(filter_contract, Mapping):
        return []
    return strings(filter_contract.get(field))


def screenplay_unit_records(
    screenplay_units: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Screenplay Scene 순서대로 모든 Unit을 펼친다."""
    return [
        unit
        for scene in records(screenplay_units.get("scenes"))
        for unit in records(scene.get("units"))
    ]


def reenactment_runtime_plan(
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> tuple[ReenactmentRuntimePlan, list[ValidationIssue]]:
    """Profile에 포함된 Unit과 Layer의 고유 Segment만 계획시간에 산입한다."""
    included_types = set(profile_filter_values(output_profile, "included_unit_types"))
    excluded_types = set(profile_filter_values(output_profile, "excluded_unit_types"))
    included_layers = set(profile_filter_values(output_profile, "included_layers"))
    eligible_segment_ids = {
        cast(str, unit["segment_id"])
        for unit in screenplay_unit_records(screenplay_units)
        if unit.get("type") in included_types
        and unit.get("type") not in excluded_types
        and isinstance(unit.get("segment_id"), str)
    }
    segments = records(presentation_plan.get("segments"))
    known_segment_ids = {
        cast(str, segment["segment_id"])
        for segment in segments
        if isinstance(segment.get("segment_id"), str)
    }
    missing_segment_ids = sorted(eligible_segment_ids - known_segment_ids)
    included_segment_ids: list[str] = []
    excluded_segment_ids: list[str] = []
    planned_duration_sec = 0.0
    invalid_segment_ids: list[object] = []
    duplicate_segment_ids: list[str] = []
    seen_segment_ids: set[str] = set()
    for segment in segments:
        segment_id = segment.get("segment_id")
        duration_sec = finite_number(segment.get("duration_sec"), False)
        if not isinstance(segment_id, str) or duration_sec is None:
            invalid_segment_ids.append(segment_id)
            continue
        if segment_id in seen_segment_ids:
            duplicate_segment_ids.append(segment_id)
            continue
        seen_segment_ids.add(segment_id)
        is_included = (
            segment_id in eligible_segment_ids
            and segment.get("segment_type") in included_layers
        )
        if is_included:
            included_segment_ids.append(segment_id)
            planned_duration_sec += duration_sec
        else:
            excluded_segment_ids.append(segment_id)
    issues: list[ValidationIssue] = []
    if missing_segment_ids or invalid_segment_ids or duplicate_segment_ids:
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_SEGMENT_INVALID",
                "재연극 계획시간에 사용할 Presentation Segment 결속이 올바르지 않습니다.",
                REPORT_ARTIFACT,
                {
                    "missing_segment_ids": missing_segment_ids,
                    "invalid_segment_ids": invalid_segment_ids,
                    "duplicate_segment_ids": sorted(set(duplicate_segment_ids)),
                },
            )
        )
    return (
        ReenactmentRuntimePlan(
            planning_basis="PRESENTATION_PLAN_INCLUDED_SEGMENTS",
            included_segment_ids=included_segment_ids,
            excluded_segment_ids=excluded_segment_ids,
            planned_duration_sec=round(planned_duration_sec, 3),
        ),
        issues,
    )


def reenactment_runtime_configuration(
    production_config: Mapping[str, object],
) -> tuple[float | None, float | None, list[ValidationIssue]]:
    """선택적인 재연극 목표·허용치를 쌍으로 읽고 방송 목표와 교차 검증한다."""
    raw_target = production_config.get("target_reenactment_minutes")
    raw_tolerance = production_config.get("reenactment_runtime_tolerance_ratio")
    if raw_target is None and raw_tolerance is None:
        return None, None, []
    target = finite_number(raw_target, False)
    tolerance = finite_number(raw_tolerance, True)
    broadcast_target = finite_number(
        production_config.get("target_runtime_minutes"),
        False,
    )
    issues: list[ValidationIssue] = []
    if target is None or tolerance is None or tolerance >= 1:
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_CONFIGURATION_INVALID",
                "재연극 목표시간과 허용 비율은 유효한 값으로 함께 설정해야 합니다.",
                "00_PROJECT/production_config.json",
                {
                    "target_reenactment_minutes": raw_target,
                    "reenactment_runtime_tolerance_ratio": raw_tolerance,
                },
            )
        )
    if target is not None and broadcast_target is not None and target > broadcast_target:
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_TARGET_EXCEEDS_BROADCAST",
                "재연극 목표시간은 전체 방송 목표시간을 초과할 수 없습니다.",
                "00_PROJECT/production_config.json",
                {
                    "target_reenactment_minutes": target,
                    "target_runtime_minutes": broadcast_target,
                },
            )
        )
    return target, tolerance, issues


def reenactment_runtime_status(
    production_config: Mapping[str, object],
    screenplay_units: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    output_profile: Mapping[str, object],
) -> tuple[dict[str, object], list[ValidationIssue]]:
    """GATE-09용 재연극 계획시간 상태와 허용범위 Issue를 만든다."""
    plan, plan_issues = reenactment_runtime_plan(
        screenplay_units,
        presentation_plan,
        output_profile,
    )
    target, tolerance, configuration_issues = reenactment_runtime_configuration(
        production_config
    )
    estimated_minutes = round(plan["planned_duration_sec"] / 60.0, 6)
    status = "NOT_CONFIGURED" if target is None and tolerance is None else "MISSING"
    issues = [*plan_issues, *configuration_issues]
    if target is not None and tolerance is not None and not configuration_issues:
        minimum = target * (1 - tolerance)
        maximum = target * (1 + tolerance)
        status = "ESTIMATED"
        if not minimum <= estimated_minutes <= maximum:
            issues.append(
                runtime_issue(
                    "ERROR",
                    "REENACTMENT_RUNTIME_MISMATCH",
                    "Output Profile 포함 Segment의 계획시간이 재연극 허용범위를 벗어났습니다.",
                    REPORT_ARTIFACT,
                    {
                        "estimated_minutes": estimated_minutes,
                        "minimum_minutes": minimum,
                        "maximum_minutes": maximum,
                    },
                )
            )
    return (
        {
            "target_minutes": target,
            "tolerance_ratio": tolerance,
            **plan,
            "estimated_minutes": estimated_minutes,
            "measured_minutes": None,
            "status": status,
        },
        issues,
    )


def reenactment_runtime_evidence(
    report: Mapping[str, object],
    method: str,
    estimated_duration_sec: float | None,
    measured_duration_sec: float | None,
) -> dict[str, object]:
    """현재 Export Report에 결속된 Editorial 재연극 시간 근거를 만든다."""
    runtime_status = report.get("runtime_status")
    input_hashes = report.get("input_artifact_hashes")
    if not isinstance(runtime_status, Mapping) or not isinstance(input_hashes, Mapping):
        raise ValueError("유효한 재연극 Export Report Runtime 근거가 필요합니다.")
    return {
        "method": method,
        "input_artifact_hashes": dict(input_hashes),
        "reenactment_export_report_sha256": document_sha256(report),
        "included_segment_ids": strings(runtime_status.get("included_segment_ids")),
        "excluded_segment_ids": strings(runtime_status.get("excluded_segment_ids")),
        "planned_duration_sec": runtime_status.get("planned_duration_sec"),
        "estimated_duration_sec": estimated_duration_sec,
        "measured_duration_sec": measured_duration_sec,
    }


def reenactment_runtime_evidence_issues(
    production_config: Mapping[str, object],
    report: Mapping[str, object],
    review: Mapping[str, object],
) -> list[ValidationIssue]:
    """Editorial 시간 근거의 방법·신선도·Profile 포함범위·허용치를 검증한다."""
    target, tolerance, configuration_issues = reenactment_runtime_configuration(
        production_config
    )
    if target is None and tolerance is None and not configuration_issues:
        return []
    evidence = review.get("reenactment_runtime_evidence")
    if not isinstance(evidence, Mapping):
        return [
            *configuration_issues,
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_EVIDENCE_MISSING",
                "재연극 목표가 설정된 Editorial Review에는 별도 Runtime 근거가 필요합니다.",
                EDITORIAL_ARTIFACT,
                {},
            ),
        ]
    runtime_status = report.get("runtime_status")
    report_input_hashes = report.get("input_artifact_hashes")
    evidence_input_hashes = evidence.get("input_artifact_hashes")
    expected_report_hash = document_sha256(report)
    stale = (
        not isinstance(report_input_hashes, Mapping)
        or not isinstance(evidence_input_hashes, Mapping)
        or dict(evidence_input_hashes) != dict(report_input_hashes)
        or evidence.get("reenactment_export_report_sha256") != expected_report_hash
    )
    issues = list(configuration_issues)
    if stale:
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_MEASUREMENT_STALE",
                "재연극 Runtime 근거가 현재 Unit·Profile·Presentation Report와 다릅니다.",
                EDITORIAL_ARTIFACT,
                {"expected_report_sha256": expected_report_hash},
            )
        )
    if not isinstance(runtime_status, Mapping):
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_EVIDENCE_INVALID",
                "Export Report의 재연극 Runtime 상태가 없습니다.",
                EDITORIAL_ARTIFACT,
                {},
            )
        )
        return issues
    expected_included = strings(runtime_status.get("included_segment_ids"))
    expected_excluded = strings(runtime_status.get("excluded_segment_ids"))
    expected_planned = finite_number(runtime_status.get("planned_duration_sec"), True)
    actual_planned = finite_number(evidence.get("planned_duration_sec"), True)
    if (
        strings(evidence.get("included_segment_ids")) != expected_included
        or strings(evidence.get("excluded_segment_ids")) != expected_excluded
        or expected_planned is None
        or actual_planned is None
        or abs(expected_planned - actual_planned) > 0.001
    ):
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_PLAN_MISMATCH",
                "Editorial 재연극 Runtime 범위가 검증된 Output Profile 계획과 다릅니다.",
                EDITORIAL_ARTIFACT,
                {
                    "expected_included_segment_ids": expected_included,
                    "expected_excluded_segment_ids": expected_excluded,
                    "expected_planned_duration_sec": expected_planned,
                },
            )
        )
    method = evidence.get("method")
    estimated = finite_number(evidence.get("estimated_duration_sec"), False)
    measured = finite_number(evidence.get("measured_duration_sec"), False)
    selected_duration: float | None = None
    if method == "WORD_COUNT_ESTIMATE" and estimated is not None and measured is None:
        selected_duration = estimated
    elif method in MEASURED_METHODS and measured is not None and estimated is None:
        selected_duration = measured
    else:
        issues.append(
            runtime_issue(
                "ERROR",
                "REENACTMENT_RUNTIME_EVIDENCE_INVALID",
                "추정과 실측 시간은 선언한 측정 방법에 맞게 분리해야 합니다.",
                EDITORIAL_ARTIFACT,
                {
                    "method": method,
                    "estimated_duration_sec": evidence.get("estimated_duration_sec"),
                    "measured_duration_sec": evidence.get("measured_duration_sec"),
                },
            )
        )
    if selected_duration is not None and target is not None and tolerance is not None:
        selected_minutes = selected_duration / 60.0
        minimum = target * (1 - tolerance)
        maximum = target * (1 + tolerance)
        if not minimum <= selected_minutes <= maximum:
            issues.append(
                runtime_issue(
                    "ERROR",
                    "REENACTMENT_RUNTIME_MISMATCH",
                    "Editorial 재연극 시간 근거가 설정된 허용범위를 벗어났습니다.",
                    EDITORIAL_ARTIFACT,
                    {
                        "method": method,
                        "duration_minutes": selected_minutes,
                        "minimum_minutes": minimum,
                        "maximum_minutes": maximum,
                    },
                )
            )
    return issues

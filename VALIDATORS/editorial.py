"""최종 방송 대본과 Production Package의 Editorial Review 계약."""

from collections.abc import Mapping
from copy import deepcopy

from VALIDATORS.exceptions import StateTransitionError
from VALIDATORS.models import ProjectState, ValidationIssue

EDITORIAL_CHECKS = (
    "broadcast_format",
    "absolute_time",
    "dialogue_naturalness",
    "panel_reaction_function",
    "audience_belief",
    "shootability",
    "victim_dignity",
)


def validate_editorial_review(
    review: Mapping[str, object],
    project_id: str,
) -> list[ValidationIssue]:
    """완료된 Editorial Review의 판정과 Issue 정합성을 검사한다."""
    issues: list[ValidationIssue] = []
    if review.get("project_id") != project_id:
        issues.append(
            ValidationIssue(
                severity="ERROR",
                code="EDITORIAL_PROJECT_ID_MISMATCH",
                message="Editorial Review의 Project ID가 현재 Project와 다릅니다.",
                artifact="08_QA/editorial_review.json",
                context={"expected": project_id, "actual": review.get("project_id")},
            )
        )
    checks = review.get("checks")
    failed_checks = (
        list(EDITORIAL_CHECKS)
        if not isinstance(checks, Mapping)
        else [name for name in EDITORIAL_CHECKS if checks.get(name) != "PASS"]
    )
    raw_issues = review.get("issues")
    issue_count = len(raw_issues) if isinstance(raw_issues, list) else 1
    if review.get("result") != "PASS" or failed_checks or issue_count:
        issues.append(
            ValidationIssue(
                severity="ERROR",
                code="EDITORIAL_REVIEW_REQUIRED",
                message="Editorial Review의 모든 항목이 PASS이고 Issue가 없어야 합니다.",
                artifact="08_QA/editorial_review.json",
                context={
                    "result": review.get("result"),
                    "failed_checks": failed_checks,
                    "issue_count": issue_count,
                },
            )
        )
    return issues


def approve_editorial_review(
    state: ProjectState,
    review: Mapping[str, object],
    actor: str,
    reason: str,
    updated_at: str,
) -> ProjectState:
    """완료된 Review와 준비 조건을 확인한 뒤 Editorial 승인 상태를 반환한다."""
    if not actor.strip() or not reason.strip():
        raise StateTransitionError("Editorial 승인에는 actor와 reason이 필요합니다.")
    if state["state"] != "EDITORIAL_REVIEW_REQUIRED":
        raise StateTransitionError(
            "Editorial Review Required 상태에서만 승인할 수 있습니다: "
            f"state={state['state']}"
        )
    readiness = state["readiness"]
    readiness_values: Mapping[str, object] = readiness
    required = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
    }
    mismatches = {
        field: {"expected": expected, "actual": readiness_values[field]}
        for field, expected in required.items()
        if readiness_values[field] != expected
    }
    if mismatches:
        raise StateTransitionError(
            f"Editorial 승인 전 준비 상태가 완전하지 않습니다: mismatches={mismatches}"
        )
    issues = validate_editorial_review(review, state["project_id"])
    if issues:
        raise StateTransitionError(
            f"Editorial Review Issue를 먼저 해결해야 합니다: issues={issues}"
        )
    next_state = deepcopy(state)
    next_state["state"] = "EDITORIAL_APPROVED"
    next_state["readiness"]["editorial_status"] = "EDITORIAL_APPROVED"
    next_state["updated_at"] = updated_at
    return next_state


def finalize_production_ready(
    state: ProjectState,
    updated_at: str,
) -> ProjectState:
    """네 준비 조건이 모두 충족된 Project만 Production Ready로 전이한다."""
    if state["state"] != "EDITORIAL_APPROVED":
        raise StateTransitionError(
            "Editorial Approved 상태에서만 Production Ready로 전이할 수 있습니다: "
            f"state={state['state']}"
        )
    readiness = state["readiness"]
    readiness_values: Mapping[str, object] = readiness
    expected = {
        "artifact_status": "ARTIFACT_COMPLETE",
        "contract_status": "CONTRACT_VALIDATED",
        "process_status": "PROCESS_CONFORMANT",
        "editorial_status": "EDITORIAL_APPROVED",
    }
    mismatches = {
        field: {"expected": value, "actual": readiness_values[field]}
        for field, value in expected.items()
        if readiness_values[field] != value
    }
    if mismatches:
        raise StateTransitionError(
            f"Production Ready 조건이 충족되지 않았습니다: mismatches={mismatches}"
        )
    next_state = deepcopy(state)
    next_state["state"] = "PRODUCTION_READY"
    next_state["updated_at"] = updated_at
    return next_state

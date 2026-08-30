"""Runtime이 소유하는 Candidate 승인 기록 생성과 검증."""

from collections.abc import Mapping

from RUNTIME.models import RuntimeApproval
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.models import ValidationIssue
from VALIDATORS.novelty import variation_precheck_source_hash


def approval_input_hashes(
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
    candidate_evaluation: Mapping[str, object],
) -> dict[str, str]:
    """승인 입력 Hash를 계산한다."""
    return {
        "variation_candidates": variation_precheck_source_hash(variations),
        "novelty_precheck": document_sha256(novelty_precheck),
        "candidate_evaluation": document_sha256(candidate_evaluation),
    }


def build_candidate_approval(
    project_id: str,
    selected_candidate_id: str,
    recommended_candidate_id: str,
    actor: str,
    reason: str,
    approved_at: str,
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
    candidate_evaluation: Mapping[str, object],
    approval_policy: str,
    runtime_approval: RuntimeApproval | None,
) -> dict[str, object]:
    """자동 또는 명시적 Human Override 승인 기록을 만든다."""
    approval_type = (
        "HUMAN_OVERRIDE"
        if selected_candidate_id != recommended_candidate_id
        else "HUMAN_CONFIRMATION"
        if approval_policy == "HUMAN_REVIEW"
        else "AUTO_POLICY"
    )
    document: dict[str, object] = {
        "$schema": "../../../STANDARD/schemas/candidate_approval.schema.json",
        "schema_family": "candidate-approval",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "selected_candidate_id": selected_candidate_id,
        "recommended_candidate_id": recommended_candidate_id,
        "approval_type": approval_type,
        "actor": actor,
        "reason": reason,
        "input_hashes": approval_input_hashes(
            variations,
            novelty_precheck,
            candidate_evaluation,
        ),
        "approved_at": approved_at,
    }
    if runtime_approval is not None:
        document.update(
            {
                "approval_id": runtime_approval["approval_id"],
                "run_id": runtime_approval["run_id"],
                "task_id": runtime_approval["task_id"],
                "created_at": runtime_approval["created_at"],
                "bound_input_hashes": runtime_approval["bound_input_hashes"],
            }
        )
    return document


def validate_candidate_approval(
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
    candidate_eligibility: Mapping[str, object],
    candidate_evaluation: Mapping[str, object],
    candidate_approval: Mapping[str, object],
) -> list[ValidationIssue]:
    """승인 대상, 권한 유형과 입력 Hash의 정합성을 검증한다."""
    selected = candidate_approval.get("selected_candidate_id")
    recommended = candidate_evaluation.get("recommended_candidate_id")
    eligible = candidate_eligibility.get("eligible_candidate_ids")
    expected_hashes = approval_input_hashes(
        variations,
        novelty_precheck,
        candidate_evaluation,
    )
    problems: list[str] = []
    if selected != variations.get("approved_candidate_id"):
        problems.append("APPROVED_VARIATION_MISMATCH")
    if candidate_approval.get("recommended_candidate_id") != recommended:
        problems.append("RECOMMENDATION_MISMATCH")
    if not isinstance(eligible, list) or selected not in eligible:
        problems.append("CANDIDATE_INELIGIBLE")
    if candidate_approval.get("input_hashes") != expected_hashes:
        problems.append("APPROVAL_STALE")
    approval_type = candidate_approval.get("approval_type")
    if selected != recommended and approval_type != "HUMAN_OVERRIDE":
        problems.append("APPROVAL_TYPE_MISMATCH")
    if selected == recommended and approval_type not in {
        "AUTO_POLICY",
        "HUMAN_CONFIRMATION",
    }:
        problems.append("APPROVAL_TYPE_MISMATCH")
    if approval_type in {"HUMAN_CONFIRMATION", "HUMAN_OVERRIDE"}:
        provenance_fields = (
            "approval_id",
            "run_id",
            "task_id",
            "created_at",
            "bound_input_hashes",
        )
        present_count = sum(field in candidate_approval for field in provenance_fields)
        if present_count != len(provenance_fields):
            problems.append("HUMAN_APPROVAL_PROVENANCE_INCOMPLETE")
        if present_count == len(provenance_fields):
            if candidate_approval.get("task_id") != "variation.approve":
                problems.append("HUMAN_APPROVAL_TASK_MISMATCH")
            if candidate_approval.get("actor") in {None, "SYSTEM"}:
                problems.append("HUMAN_APPROVAL_ACTOR_INVALID")
            if candidate_approval.get("approved_at") != candidate_approval.get("created_at"):
                problems.append("HUMAN_APPROVAL_TIMESTAMP_MISMATCH")
    if not problems:
        return []
    return [
        ValidationIssue(
            severity="ERROR",
            code="CANDIDATE_APPROVAL_INVALID",
            message="Candidate 승인 기록이 Runtime 정책과 일치하지 않습니다.",
            artifact="00_PROJECT/candidate_approval.json",
            context={"problems": problems, "selected_candidate_id": selected},
        )
    ]

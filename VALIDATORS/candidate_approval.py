"""Runtime이 소유하는 Candidate 승인 기록 생성과 검증."""

from collections.abc import Mapping

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
) -> dict[str, object]:
    """자동 또는 명시적 Human Override 승인 기록을 만든다."""
    approval_type = (
        "AUTO_POLICY"
        if selected_candidate_id == recommended_candidate_id
        else "HUMAN_OVERRIDE"
    )
    return {
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
    expected_type = "AUTO_POLICY" if selected == recommended else "HUMAN_OVERRIDE"
    if candidate_approval.get("approval_type") != expected_type:
        problems.append("APPROVAL_TYPE_MISMATCH")
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

"""Runtime이 소유하는 Candidate 승인 기록 생성과 검증."""

from collections.abc import Mapping
from copy import deepcopy

from RUNTIME.models import RuntimeApproval
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.candidate_event_briefs import (
    candidate_event_brief_hashes,
    canonical_json_hash,
)
from VALIDATORS.models import ValidationIssue


def approval_input_hashes(
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    candidate_event_briefs: Mapping[str, object] | None,
    novelty_precheck: Mapping[str, object],
    candidate_eligibility: Mapping[str, object],
    candidate_evaluation: Mapping[str, object],
) -> dict[str, str]:
    """승인 입력 Hash를 계산한다."""
    variation_input = deepcopy(dict(variations))
    variation_input["approved_candidate_id"] = None
    candidates = variation_input.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate["selection_status"] = "PENDING"
    hashes = {
        "production_config": document_sha256(production_config),
        "variation_candidates": document_sha256(variation_input),
        "novelty_precheck": document_sha256(novelty_precheck),
        "candidate_eligibility": document_sha256(candidate_eligibility),
        "candidate_evaluation": document_sha256(candidate_evaluation),
    }
    if candidate_event_briefs is not None:
        hashes["candidate_event_briefs"] = canonical_json_hash(candidate_event_briefs)
        hashes.update(
            {
                f"candidate_event_brief_{candidate_id.lower().replace('-', '_')}": value
                for candidate_id, value in candidate_event_brief_hashes(
                    candidate_event_briefs
                ).items()
            }
        )
    return hashes


def build_candidate_approval(
    project_id: str,
    selected_candidate_id: str,
    recommended_candidate_id: str,
    actor: str,
    reason: str,
    approved_at: str,
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    candidate_event_briefs: Mapping[str, object] | None,
    novelty_precheck: Mapping[str, object],
    candidate_eligibility: Mapping[str, object],
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
        "schema_version": "1.1.0" if candidate_event_briefs is not None else "1.0.0",
        "project_id": project_id,
        "selected_candidate_id": selected_candidate_id,
        "recommended_candidate_id": recommended_candidate_id,
        "approval_type": approval_type,
        "actor": actor,
        "reason": reason,
        "input_hashes": approval_input_hashes(
            production_config,
            variations,
            candidate_event_briefs,
            novelty_precheck,
            candidate_eligibility,
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
                "approval_decision": runtime_approval["decision"],
                "human_approval_record_hash": document_sha256(runtime_approval),
            }
        )
    return document


def validate_candidate_approval(
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    candidate_event_briefs: Mapping[str, object] | None,
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
        production_config,
        variations,
        candidate_event_briefs,
        novelty_precheck,
        candidate_eligibility,
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
            "approval_decision",
            "human_approval_record_hash",
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
            bound = candidate_approval.get("bound_input_hashes")
            runtime_bound_hashes = {
                name: value
                for name, value in expected_hashes.items()
                if not name.startswith("candidate_event_brief_var_")
            }
            if not isinstance(bound, Mapping) or any(
                bound.get(name) != value
                for name, value in runtime_bound_hashes.items()
            ):
                problems.append("HUMAN_APPROVAL_INPUT_HASH_MISMATCH")
            reconstructed = {
                "schema_family": "runtime-approval",
                "schema_version": "1.0.0",
                "approval_id": candidate_approval.get("approval_id"),
                "run_id": candidate_approval.get("run_id"),
                "task_id": candidate_approval.get("task_id"),
                "decision": candidate_approval.get("approval_decision"),
                "actor": candidate_approval.get("actor"),
                "reason": candidate_approval.get("reason"),
                "bound_input_hashes": bound,
                "created_at": candidate_approval.get("created_at"),
            }
            if candidate_approval.get("human_approval_record_hash") != document_sha256(
                reconstructed
            ):
                problems.append("HUMAN_APPROVAL_RECORD_HASH_MISMATCH")
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

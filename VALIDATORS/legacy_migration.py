"""Legacy v1.1 Project의 내용 보존 Migration 계획을 만든다."""

from collections.abc import Mapping
from copy import deepcopy

from VALIDATORS.dependency import artifact_hash, build_initial_project_state, mark_artifact_clean
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ProjectState, RevisionTrigger
from VALIDATORS.variation import (
    legacy_candidate_signature,
    runtime_candidate_metadata,
    variation_document_metadata,
)
from VALIDATORS.variation_registry import VariationRuntime


def default_project_constraints(
    project_id: str,
    template: Mapping[str, object],
) -> dict[str, object]:
    """Legacy Project용 무제약 기본 Constraint를 생성한다."""
    constraints = deepcopy(dict(template))
    constraints["project_id"] = project_id
    constraints["must_use"] = []
    constraints["must_not_use"] = []
    return constraints


def migrated_legacy_variations(
    document: Mapping[str, object],
    runtime: VariationRuntime,
) -> tuple[dict[str, object], bool]:
    """Legacy Candidate 선택·상태·서명을 보존하며 Runtime Pin만 추가한다."""
    if runtime["engine_version"] != "1.0.0" or runtime["catalog_version"] != "1.0.0":
        raise ConfigurationError(
            "LEGACY_MIGRATION_RUNTIME_INVALID: Legacy Migration에는 v1 Runtime이 필요합니다."
        )
    next_document = deepcopy(dict(document))
    raw_candidates = next_document.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ConfigurationError("LEGACY_MIGRATION_CANDIDATES_INVALID: Candidate 배열이 없습니다.")
    reproduced = True
    for candidate_index, candidate in enumerate(raw_candidates):
        if not isinstance(candidate, dict):
            raise ConfigurationError(
                "LEGACY_MIGRATION_CANDIDATES_INVALID: Candidate 객체가 필요합니다."
            )
        selection = candidate.get("selection")
        if not isinstance(selection, Mapping) or not all(
            isinstance(field, str) and isinstance(value, str) for field, value in selection.items()
        ):
            raise ConfigurationError(
                "LEGACY_MIGRATION_CANDIDATES_INVALID: Selection 문자열 객체가 필요합니다."
            )
        expected_signature = legacy_candidate_signature(
            {str(field): str(value) for field, value in selection.items()}
        )
        reproduced = reproduced and candidate.get("signature") == expected_signature
        candidate.update(runtime_candidate_metadata(runtime, 0, candidate_index))
    next_document.update(variation_document_metadata(runtime))
    candidate_count = len(raw_candidates)
    next_document["candidate_count"] = candidate_count
    next_document["batch_trace"] = [
        {
            "batch_id": "BATCH-01",
            "batch_nonce": 0,
            "generated_count": candidate_count,
            "novelty_pass_count": 0,
            "eligible_count": 0,
            "accepted_count": 0,
            "rejections": [
                {
                    "code": "LEGACY_ELIGIBILITY_NOT_RECORDED",
                    "candidate_ids": [
                        candidate.get("candidate_id")
                        for candidate in raw_candidates
                        if isinstance(candidate, Mapping)
                    ],
                }
            ],
        }
    ]
    return next_document, reproduced


def migration_review_reasons(
    project_files: set[str],
    signature_reproduced: bool,
) -> list[str]:
    """Legacy Provenance에서 자동 복구할 수 없는 항목을 반환한다."""
    reasons: list[str] = []
    if not signature_reproduced:
        reasons.append("LEGACY_SIGNATURE_NOT_REPRODUCIBLE")
    required_provenance = {
        "00_PROJECT/candidate_evaluation.json",
        "00_PROJECT/candidate_eligibility.json",
        "00_PROJECT/candidate_approval.json",
    }
    missing = sorted(required_provenance - project_files)
    if missing:
        reasons.append("LEGACY_CANDIDATE_PROVENANCE_MISSING")
    return reasons


def migration_status(review_reasons: list[str]) -> str:
    """복구 불가능한 Provenance 유무를 Migration 상태로 반환한다."""
    return "MANUAL_REVIEW_REQUIRED" if review_reasons else "MIGRATED"


def normalized_legacy_state(
    current_state: ProjectState,
    dependency_graph: Mapping[str, object],
    project_id: str,
    updated_at: str,
    migrated_artifacts: Mapping[str, bytes],
) -> ProjectState:
    """새 Artifact State 항목을 추가하고 Migration 대상 Hash를 CLEAN으로 고정한다."""
    next_state = build_initial_project_state(dependency_graph, project_id, updated_at)
    next_state["state"] = current_state["state"]
    next_state["current_gate"] = current_state["current_gate"]
    next_state["readiness"] = deepcopy(current_state["readiness"])
    next_state["readiness"]["process_revision"] = current_state["readiness"]["process_revision"] + 1
    next_state["revision_trigger"] = RevisionTrigger(
        type="SEMANTIC_CORRECTION",
        source_id=f"LEGACY-MIGRATION:{updated_at}",
        target_owner_agent=None,
        target_gate=None,
        target_task_ids=[],
        actor=None,
        reason="Legacy Provenance Migration으로 의미 계약을 다시 검증합니다.",
        triggered_at=updated_at,
    )
    for artifact_name, artifact_state in current_state["artifacts"].items():
        if artifact_name in next_state["artifacts"]:
            next_state["artifacts"][artifact_name] = deepcopy(artifact_state)
    for artifact_name, content in migrated_artifacts.items():
        next_state = mark_artifact_clean(
            next_state,
            artifact_name,
            artifact_hash(content),
            updated_at,
        )
    return next_state

"""Versioned Variation Engine Dispatcher와 안정적인 Public API."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from importlib import import_module
from pathlib import Path

from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.variation_engines.common import (
    apply_compiled_required_values,
    apply_runtime_metadata,
    apply_user_case_constraints,
    candidate_policy_profile,
    candidate_signature,
    choose_dimension_value,
    legacy_candidate_signature,
    require_dimensions,
    require_user_case_constraints,
    runtime_candidate_metadata,
    selection_similarity,
    validate_generator_inputs,
    variation_document_metadata,
)
from VALIDATORS.variation_registry import (
    VariationRuntime,
    resolve_variation_runtime_for_channel,
)

__all__ = [
    "apply_compiled_required_values",
    "apply_runtime_metadata",
    "apply_user_case_constraints",
    "approve_variation_candidate",
    "candidate_policy_profile",
    "candidate_signature",
    "choose_dimension_value",
    "generate_eligible_candidate_pool",
    "generate_legacy_variation_batch",
    "generate_variation_candidates",
    "generate_variation_candidates_with_policy",
    "legacy_candidate_signature",
    "require_dimensions",
    "require_user_case_constraints",
    "runtime_candidate_metadata",
    "selection_similarity",
    "validate_generator_inputs",
    "variation_document_metadata",
]


def generate_eligible_candidate_pool(
    project_id: str,
    story_seed: str,
    eligible_candidate_count: int,
    runtime: VariationRuntime,
    source_truth_classification: str,
    production_config: Mapping[str, object],
    project_constraints: Mapping[str, object],
    channel: Mapping[str, object],
    story_history: Sequence[Mapping[str, object]],
    novelty_thresholds: Mapping[str, object],
    projection_contract: Mapping[str, object],
    source_truth_contract: Mapping[str, object] | None,
    max_batches: int,
) -> dict[str, object]:
    """Hash 검증 뒤 로드된 Version Entrypoint로 Candidate Pool 생성을 위임한다."""
    return runtime["entrypoint"](
        project_id,
        story_seed,
        eligible_candidate_count,
        runtime,
        source_truth_classification,
        production_config,
        project_constraints,
        channel,
        story_history,
        novelty_thresholds,
        projection_contract,
        source_truth_contract,
        max_batches,
    )


def generate_legacy_variation_batch(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    batch_nonce: int,
) -> dict[str, object]:
    """검증된 v1 Entrypoint Module의 Legacy Batch API를 호출한다."""
    if runtime["engine_version"] != "1.0.0":
        raise ConfigurationError(
            "VARIATION_ENTRYPOINT_INVALID: Legacy Batch에는 Engine 1.0.0이 필요합니다."
        )
    module_name = runtime["entrypoint_name"].partition(":")[0]
    module = import_module(module_name)
    generator = getattr(module, "generate_legacy_variation_batch", None)
    if not callable(generator):
        raise ConfigurationError(
            "VARIATION_ENTRYPOINT_INVALID: "
            f"module={module_name}, function=generate_legacy_variation_batch"
        )
    result = generator(project_id, story_seed, candidate_count, runtime, batch_nonce)
    if not isinstance(result, dict):
        raise ConfigurationError("VARIATION_ENTRYPOINT_INVALID: Legacy 결과가 객체가 아닙니다.")
    return result


def verified_v2_runtime(catalog: Mapping[str, object]) -> VariationRuntime:
    """직접 Public API도 Registry Hash를 통과한 v2 Runtime만 사용한다."""
    repository_root = Path(__file__).resolve().parents[1]
    production_config = {
        "channel_content_version": "2.0.0",
        "variation_engine_version": "2.0.0",
        "variation_catalog_version": "2.0.0",
    }
    channel = {
        "content_version": "2.0.0",
        "capabilities": {"CRIME_PSYCHOLOGY_POLICY": {"enabled": True}},
    }
    runtime = resolve_variation_runtime_for_channel(
        repository_root,
        production_config,
        channel,
    )
    if document_sha256(catalog) != document_sha256(runtime["catalog"]):
        raise ConfigurationError(
            "CATALOG_SNAPSHOT_HASH_MISMATCH: Public API Catalog가 등록 Snapshot과 다릅니다."
        )
    return runtime


def generate_variation_candidates(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    catalog: Mapping[str, object],
    source_truth_classification: str,
) -> dict[str, object]:
    """Channel Context가 없는 호출에서는 v2 정책 필터 없이 후보군을 생성한다."""
    return generate_variation_candidates_with_policy(
        project_id,
        story_seed,
        candidate_count,
        catalog,
        source_truth_classification,
        False,
    )


def generate_variation_candidates_with_policy(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    catalog: Mapping[str, object],
    source_truth_classification: str,
    apply_v2_policy: bool,
) -> dict[str, object]:
    """검증된 v2 Module의 직접 Candidate API를 호출한다."""
    runtime = verified_v2_runtime(catalog)
    module_name = runtime["entrypoint_name"].partition(":")[0]
    module = import_module(module_name)
    generator = getattr(module, "generate_candidates_with_policy", None)
    if not callable(generator):
        raise ConfigurationError(
            "VARIATION_ENTRYPOINT_INVALID: "
            f"module={module_name}, function=generate_candidates_with_policy"
        )
    result = generator(
        project_id,
        story_seed,
        candidate_count,
        runtime,
        source_truth_classification,
        apply_v2_policy,
    )
    if not isinstance(result, dict):
        raise ConfigurationError("VARIATION_ENTRYPOINT_INVALID: v2 결과가 객체가 아닙니다.")
    return result


def approve_variation_candidate(
    candidates_document: Mapping[str, object],
    candidate_id: str,
) -> dict[str, object]:
    """후보 하나만 APPROVED로 표시한 새 Variation 문서를 반환한다."""
    candidates = candidates_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ConfigurationError("variation_candidates.candidates 객체 배열이 필요합니다.")
    candidate_ids = {candidate.get("candidate_id") for candidate in candidates}
    if candidate_id not in candidate_ids:
        raise ConfigurationError(f"승인할 Variation 후보가 없습니다: candidate_id={candidate_id}")
    next_document = deepcopy(dict(candidates_document))
    next_candidates = next_document.get("candidates")
    if not isinstance(next_candidates, list):
        raise ConfigurationError("복사된 Variation 후보 배열이 올바르지 않습니다.")
    for candidate in next_candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("복사된 Variation 후보 객체가 올바르지 않습니다.")
        candidate["selection_status"] = (
            "APPROVED" if candidate.get("candidate_id") == candidate_id else "REJECTED"
        )
    next_document["approved_candidate_id"] = candidate_id
    return next_document

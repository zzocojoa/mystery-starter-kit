"""v2.1.0 심리 구조 우선 Eligible Pool Variation Engine."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.variation_engines.common import (
    apply_runtime_metadata,
    candidate_policy_profile,
    candidate_signature,
    choose_dimension_value,
    generate_eligible_pool_with_batch_generator,
    require_dimensions,
    runtime_candidate_metadata,
    validate_generator_inputs,
    variation_document_metadata,
)
from VALIDATORS.variation_engines.v2_0_0 import generation_choices
from VALIDATORS.variation_registry import VariationRuntime

PSYCHOLOGICAL_DIMENSION_ORDER = (
    "primary_psychological_architecture",
    "offender_access_strategy",
    "trust_formation_method",
    "control_escalation_pattern",
    "victim_vulnerability",
    "victim_dilemma",
    "exit_barrier",
    "psychological_consequence",
    "agency_recovery_mode",
)
SECONDARY_MYSTERY_DIMENSION = "secondary_mystery_engine"


def ordered_dimensions(
    dimensions: Mapping[str, list[str]],
) -> list[tuple[str, list[str]]]:
    """심리 구조를 먼저, 보조 Mystery를 마지막에 배치한다."""
    required = {*PSYCHOLOGICAL_DIMENSION_ORDER, SECONDARY_MYSTERY_DIMENSION}
    missing = sorted(required - set(dimensions))
    if missing:
        raise ConfigurationError(
            f"v2.1 Variation Catalog의 필수 Dimension이 없습니다: fields={missing}"
        )
    remaining = sorted(set(dimensions) - required)
    ordered_names = [*PSYCHOLOGICAL_DIMENSION_ORDER, *remaining, SECONDARY_MYSTERY_DIMENSION]
    return [(name, dimensions[name]) for name in ordered_names]


def generate_candidates(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    source_truth_classification: str,
) -> dict[str, object]:
    """심리 구조 우선 순서로 2.1 Candidate Batch를 생성한다."""
    validate_generator_inputs(project_id, story_seed, candidate_count)
    dimension_items = ordered_dimensions(require_dimensions(runtime["catalog"]))
    candidates: list[dict[str, object]] = []
    signatures: set[str] = set()
    for candidate_index in range(candidate_count):
        selection = {
            name: choose_dimension_value(
                generation_choices(name, choices, True),
                story_seed,
                name,
                candidate_index,
                dimension_index,
            )
            for dimension_index, (name, choices) in enumerate(dimension_items)
        }
        profile = candidate_policy_profile(selection, source_truth_classification)
        signature = candidate_signature(selection, profile)
        if signature in signatures:
            raise ConfigurationError(
                "v2.1 Variation Candidate 구조 서명이 충돌했습니다: "
                f"candidate_index={candidate_index}"
            )
        signatures.add(signature)
        candidates.append(
            {
                "candidate_id": f"VAR-{candidate_index + 1:02d}",
                **runtime_candidate_metadata(runtime, 0, candidate_index),
                "selection": selection,
                "policy_profile": profile,
                "signature": signature,
                "selection_status": "PENDING",
            }
        )
    return {
        "project_id": project_id,
        "story_seed_hash": sha256(story_seed.encode()).hexdigest(),
        **variation_document_metadata(runtime),
        "candidate_count": candidate_count,
        "candidates": candidates,
        "batch_trace": [
            {
                "batch_id": "BATCH-01",
                "batch_nonce": 0,
                "generated_count": candidate_count,
                "novelty_pass_count": candidate_count,
                "eligible_count": candidate_count,
                "accepted_count": candidate_count,
                "rejections": [],
            }
        ],
        "approved_candidate_id": None,
        "override": None,
    }


def generate_batch(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    source_truth_classification: str,
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    batch_nonce: int,
) -> dict[str, object]:
    """Nonce와 Production Genre를 결합한 2.1 Candidate Batch를 생성한다."""
    del channel
    generated = generate_candidates(
        project_id,
        f"{story_seed}:batch:{batch_nonce}",
        candidate_count,
        runtime,
        source_truth_classification,
    )
    document = apply_runtime_metadata(generated, runtime, batch_nonce)
    candidates = document.get("candidates")
    genre = production_config.get("genre")
    if not isinstance(candidates, list) or not isinstance(genre, str):
        raise ConfigurationError("v2.1 Candidate Genre 또는 Candidate 배열이 없습니다.")
    refreshed = deepcopy(candidates)
    signatures: set[str] = set()
    for candidate in refreshed:
        if not isinstance(candidate, dict):
            raise ConfigurationError("v2.1 Candidate 객체가 필요합니다.")
        selection = candidate.get("selection")
        if not isinstance(selection, dict):
            raise ConfigurationError("v2.1 Candidate Selection 객체가 필요합니다.")
        selection["genre"] = genre
        profile = candidate_policy_profile(selection, source_truth_classification)
        signature = candidate_signature(selection, profile)
        candidate["policy_profile"] = profile
        candidate["signature"] = signature
        if signature in signatures:
            candidate["batch_duplicate"] = True
        signatures.add(signature)
    document["candidates"] = refreshed
    return document


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
    """Novelty를 Hard Constraint로 유지한 v2.1 Eligible Pool을 만든다."""
    return generate_eligible_pool_with_batch_generator(
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
        generate_batch,
    )

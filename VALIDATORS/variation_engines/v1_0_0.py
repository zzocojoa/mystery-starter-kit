"""Legacy v1.0.0 Variation Engine의 불변 실행 구현."""

from collections.abc import Mapping, Sequence
from hashlib import sha256

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.variation_engines.common import (
    choose_dimension_value,
    generate_eligible_pool_with_batch_generator,
    legacy_candidate_signature,
    require_dimensions,
    runtime_candidate_metadata,
    validate_generator_inputs,
    variation_document_metadata,
)
from VALIDATORS.variation_registry import VariationRuntime


def generate_legacy_variation_batch(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    batch_nonce: int,
) -> dict[str, object]:
    """Base 이전 v1.0 Algorithm과 Signature로 후보 Batch를 생성한다."""
    validate_generator_inputs(project_id, story_seed, candidate_count)
    dimensions = require_dimensions(runtime["catalog"])
    dimension_items = sorted(dimensions.items())
    candidates: list[dict[str, object]] = []
    signatures: set[str] = set()
    for candidate_index in range(candidate_count):
        selection = {
            name: choose_dimension_value(
                choices,
                story_seed,
                name,
                candidate_index,
                dimension_index,
            )
            for dimension_index, (name, choices) in enumerate(dimension_items)
        }
        signature = legacy_candidate_signature(selection)
        if signature in signatures:
            raise ConfigurationError(
                "CANDIDATE_BATCH_DUPLICATED: v1 Catalog 조합이 Batch 내부에서 충돌했습니다."
            )
        signatures.add(signature)
        candidates.append(
            {
                "candidate_id": f"VAR-{candidate_index + 1:02d}",
                **runtime_candidate_metadata(runtime, batch_nonce, candidate_index),
                "selection": selection,
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
        "batch_trace": [],
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
    """Legacy 첫 Batch Seed를 보존하고 Retry에만 Nonce를 결합한다."""
    del source_truth_classification, production_config, channel
    batch_seed = story_seed if batch_nonce == 0 else f"{story_seed}:batch:{batch_nonce}"
    return generate_legacy_variation_batch(
        project_id,
        batch_seed,
        candidate_count,
        runtime,
        batch_nonce,
    )


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
    """Legacy 결과를 보존하면서 전체 적격 후보 Pool을 재생성한다."""
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

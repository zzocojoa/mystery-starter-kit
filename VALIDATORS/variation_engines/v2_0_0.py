"""v2.0.0 Eligible Pool Variation Engine의 불변 실행 구현."""

from collections.abc import Mapping, Sequence
from hashlib import sha256

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.requirements import crime_v2_candidate_policy_applies
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
from VALIDATORS.variation_registry import VariationRuntime

SAFE_GENERATION_VALUES: dict[str, frozenset[str]] = {
    "threat_type": frozenset({"CRIME", "PREDATORY"}),
    "safe_domain_betrayal": frozenset(
        {"TRUST_ABUSED", "AUTHORITY_ABUSED", "CARE_EXPECTATION_BETRAYED"}
    ),
    "responsible_agent_structure": frozenset({"SINGLE_AGENT", "DUAL_AGENTS", "COMPLICIT_GROUP"}),
    "information_mechanism": frozenset(
        {"TESTIMONIAL_CONTRADICTION", "RELATIONAL_DISCLOSURE", "OWNERSHIP_CHAIN"}
    ),
    "clue_mechanism": frozenset({"LINGUISTIC", "BEHAVIORAL", "RELATIONAL", "DOCUMENTARY"}),
    "reveal_mode": frozenset(
        {"RELATIONAL_REFRAME", "TESTIMONIAL_COLLAPSE", "OWNERSHIP_RECONSTRUCTION"}
    ),
    "final_proof_mechanism": frozenset(
        {"INDEPENDENT_NONTECHNICAL_GROUNDS", "CLAIM_EVIDENCE_CHAIN"}
    ),
    "victim_agency_mode": frozenset({"BOUNDARY_RESTORED", "EVIDENCE_PRESERVED", "INFORMED_EXIT"}),
    "technical_dependency_level": frozenset({"LOW", "MEDIUM"}),
    "production_complexity": frozenset({"LOW", "MEDIUM"}),
    "location_count": frozenset({"LOCATIONS_2", "LOCATIONS_3", "LOCATIONS_5"}),
    "major_character_count": frozenset({"MAJOR_4", "MAJOR_5", "MAJOR_7"}),
    "special_effect_level": frozenset({"NONE", "LOW"}),
    "child_actor_use": frozenset({"NONE", "SUPPORTING"}),
    "vehicle_scene": frozenset({"NONE", "STATIC"}),
    "graphic_violence": frozenset({"NONE", "IMPLIED"}),
    "incident_type": frozenset(
        {
            "DISAPPEARANCE",
            "MURDER",
            "BLACKMAIL",
            "FRAUD",
            "KIDNAPPING",
            "THEFT",
            "COVER_UP",
            "FALSE_ACCUSATION",
        }
    ),
    "culprit_structure": frozenset({"SINGLE", "DUAL"}),
    "primary_twist": frozenset(
        {
            "TW-03_FALSE_VICTIM",
            "TW-01_MISIDENTIFIED_OWNER",
            "TW-14_WITNESS_CAUSED_EVENT",
            "TW-10_RESOLUTION_CHANGES_INCIDENT",
        }
    ),
}


def generation_choices(
    dimension: str,
    choices: list[str],
    apply_v2_policy: bool,
) -> list[str]:
    """v2 범죄 심리 정책이 적용될 때만 안전 선택지를 반환한다."""
    if not apply_v2_policy:
        return choices
    allowed = SAFE_GENERATION_VALUES.get(dimension)
    if allowed is None:
        return choices
    filtered = [choice for choice in choices if choice in allowed]
    if not filtered:
        raise ConfigurationError(
            f"Variation Catalog에 안전 생성 선택지가 없습니다: dimension={dimension}"
        )
    return filtered


def generate_candidates_with_policy(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    source_truth_classification: str,
    apply_v2_policy: bool,
) -> dict[str, object]:
    """명시된 정책 적용 여부로 구조적으로 구분되는 후보군을 생성한다."""
    validate_generator_inputs(project_id, story_seed, candidate_count)
    dimensions = require_dimensions(runtime["catalog"])
    dimension_items = sorted(dimensions.items())
    candidates: list[dict[str, object]] = []
    signatures: set[str] = set()
    for candidate_index in range(candidate_count):
        selection = {
            name: choose_dimension_value(
                generation_choices(name, choices, apply_v2_policy),
                story_seed,
                name,
                candidate_index,
                dimension_index,
            )
            for dimension_index, (name, choices) in enumerate(dimension_items)
        }
        policy_profile = candidate_policy_profile(
            selection,
            source_truth_classification,
        )
        signature = candidate_signature(selection, policy_profile)
        if signature in signatures:
            raise ConfigurationError(
                "Variation Catalog의 조합 수가 부족해 후보가 충돌했습니다: "
                f"candidate_index={candidate_index}"
            )
        signatures.add(signature)
        candidates.append(
            {
                "candidate_id": f"VAR-{candidate_index + 1:02d}",
                **runtime_candidate_metadata(runtime, 0, candidate_index),
                "selection": selection,
                "policy_profile": policy_profile,
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
    """Nonce가 결합된 v2 후보 Batch와 고정 Genre를 생성한다."""
    batch_seed = f"{story_seed}:batch:{batch_nonce}"
    generated = generate_candidates_with_policy(
        project_id,
        batch_seed,
        candidate_count,
        runtime,
        source_truth_classification,
        crime_v2_candidate_policy_applies(production_config, channel),
    )
    next_document = apply_runtime_metadata(generated, runtime, batch_nonce)
    candidates = next_document.get("candidates")
    genre = production_config.get("genre")
    if not isinstance(candidates, list) or not isinstance(genre, str):
        raise ConfigurationError("v2 Candidate Genre 또는 Candidate 배열이 없습니다.")
    refreshed_signatures: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        selection = candidate.get("selection")
        if isinstance(selection, dict):
            selection["genre"] = genre
            profile = candidate_policy_profile(
                selection,
                source_truth_classification,
            )
            candidate["policy_profile"] = profile
            signature = candidate_signature(selection, profile)
            candidate["signature"] = signature
            if signature in refreshed_signatures:
                candidate["batch_duplicate"] = True
            refreshed_signatures.add(signature)
    return next_document


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
    """v2 전체 적격 후보 Pool을 재생성한다."""
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

"""v2.1.0 구체 대인범죄 구조 전용 Variation Engine."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from typing import cast

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.project_constraints import compile_project_constraints
from VALIDATORS.source_truth_contract import source_truth_project_constraints
from VALIDATORS.variation_engines.common import (
    apply_runtime_metadata,
    candidate_signature,
    choose_dimension_value,
    require_dimensions,
    runtime_candidate_metadata,
    validate_generator_inputs,
    variation_document_metadata,
)
from VALIDATORS.variation_registry import VariationRuntime

EVENT_DIMENSION_ORDER = (
    "primary_crime",
    "core_action_type",
    "responsible_agent_structure",
    "victim_structure",
    "relationship_context",
    "harm_classification",
    "motive_category",
    "protagonist_role",
    "protagonist_goal",
    "protagonist_risk",
    "depiction_mode",
    "reveal_structure",
)
DIRECT_ACTION_BY_CRIME: Mapping[str, str] = {
    "MURDER": "MURDER",
    "KIDNAPPING": "KIDNAPPING",
    "CONFINEMENT": "CONFINEMENT",
    "ASSAULT": "ASSAULT",
    "STALKING": "STALKING",
    "HOME_INVASION": "HOME_INVASION",
}
RELATIONAL_ACTIONS = ("ASSAULT", "CONFINEMENT", "STALKING")
HARM_BY_ACTION: Mapping[str, str] = {
    "MURDER": "FATALITY",
    "KIDNAPPING": "LIBERTY_DEPRIVATION",
    "CONFINEMENT": "LIBERTY_DEPRIVATION",
    "ASSAULT": "BODILY_INJURY",
    "STALKING": "SAFETY_COLLAPSE",
    "HOME_INVASION": "SAFETY_COLLAPSE",
}
ORDERED_PRODUCTION_LEVELS: Mapping[str, tuple[str, ...]] = {
    "production_complexity": ("LOW", "MEDIUM", "HIGH", "EXTREME"),
    "special_effect_level": ("NONE", "LOW", "MEDIUM", "HIGH"),
    "graphic_violence": ("NONE", "IMPLIED", "NON_GRAPHIC", "GRAPHIC"),
}


def ordered_dimensions(
    dimensions: Mapping[str, list[str]],
) -> list[tuple[str, list[str]]]:
    """중심 범죄와 인과 사건 Dimension을 다른 Story Dimension보다 먼저 배치한다."""
    missing = sorted(set(EVENT_DIMENSION_ORDER) - set(dimensions))
    if missing:
        raise ConfigurationError(
            f"v2.1 Variation Catalog의 사건 필수 Dimension이 없습니다: fields={missing}"
        )
    remaining = sorted(set(dimensions) - set(EVENT_DIMENSION_ORDER))
    ordered_names = [*EVENT_DIMENSION_ORDER, *remaining]
    return [(name, dimensions[name]) for name in ordered_names]


def normalized_event_selection(
    selection: Mapping[str, str],
    candidate_index: int,
) -> dict[str, str]:
    """관계 범죄와 실제 행위·피해를 분리하면서 인과적으로 맞춘다."""
    normalized = dict(selection)
    primary = normalized.get("primary_crime")
    if primary in DIRECT_ACTION_BY_CRIME:
        action = DIRECT_ACTION_BY_CRIME[cast(str, primary)]
    elif primary in {"DATING_VIOLENCE", "DOMESTIC_VIOLENCE"}:
        action = RELATIONAL_ACTIONS[candidate_index % len(RELATIONAL_ACTIONS)]
    else:
        raise ConfigurationError(
            f"v2.1 중심 범죄가 허용 범위를 벗어났습니다: primary_crime={primary!r}"
        )
    normalized["core_action_type"] = action
    normalized["harm_classification"] = HARM_BY_ACTION[action]
    if primary == "DATING_VIOLENCE":
        normalized["relationship_context"] = "DATING_PARTNER"
    elif primary == "DOMESTIC_VIOLENCE":
        normalized["relationship_context"] = "FAMILY_OR_HOUSEHOLD"
    return normalized


def derived_policy_profile(
    selection: Mapping[str, str],
    source_truth_classification: str,
) -> dict[str, str]:
    """2.1 구조 선택에서 정책 검사용 Read-only 값을 파생한다."""
    primary = selection["primary_crime"]
    responsible = selection["responsible_agent_structure"]
    relationship = selection["relationship_context"]
    trusted_domain = {
        "DATING_PARTNER": "ROMANTIC_PARTNER",
        "FAMILY_OR_HOUSEHOLD": "FAMILY",
        "WORKPLACE": "EMPLOYMENT",
        "NEIGHBOR": "NEIGHBOR",
    }.get(relationship, "PUBLIC_SPACE")
    derived = {
        "genre": selection["genre"],
        "threat_type": "CRIME",
        "incident_type": primary,
        "culprit_structure": {
            "SINGLE_AGENT": "SINGLE",
            "DUAL_AGENTS": "DUAL",
            "COMPLICIT_GROUP": "MULTIPLE",
        }[responsible],
        "trusted_domain": trusted_domain,
        "safe_domain_betrayal": "PHYSICAL_BOUNDARY_VIOLATED",
        "responsible_agent_structure": responsible,
        "information_mechanism": selection["information_mechanism"],
        "clue_mechanism": selection["clue_mechanism"],
        "reveal_mode": selection["reveal_mode"],
        "final_proof_mechanism": selection["final_proof_mechanism"],
        "victim_agency_mode": "SURVIVOR_DECISION",
        "primary_twist": selection["primary_twist"],
        "pressure_engine": selection["pressure_engine"],
        "technical_dependency_level": selection["technical_dependency_level"],
        "production_complexity": selection["production_complexity"],
        "location_count": selection["location_count"],
        "major_character_count": selection["major_character_count"],
        "special_effect_level": selection["special_effect_level"],
        "child_actor_use": selection["child_actor_use"],
        "vehicle_scene": selection["vehicle_scene"],
        "graphic_violence": selection["graphic_violence"],
        "episode_theme": "OFFENDER_RESPONSIBILITY",
        "source_truth_classification": source_truth_classification,
    }
    return derived


def candidate_index(candidate: Mapping[str, object]) -> int:
    """Batch Candidate ID의 1-base 번호를 0-base Index로 변환한다."""
    value = candidate.get("batch_candidate_id")
    if not isinstance(value, str):
        return 0
    suffix = value.rpartition("-")[2]
    return max(0, int(suffix) - 1) if suffix.isdigit() else 0


def refresh_candidate_structure(
    candidate: dict[str, object],
    source_truth_classification: str,
) -> None:
    """Constraint 적용 뒤 구조 선택과 서명을 다시 결속한다."""
    raw_selection = candidate.get("selection")
    if not isinstance(raw_selection, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_selection.items()
    ):
        raise ConfigurationError("v2.1 Candidate Selection 문자열 객체가 필요합니다.")
    selection = normalized_event_selection(
        cast(Mapping[str, str], raw_selection),
        candidate_index(candidate),
    )
    candidate["selection"] = selection
    profile = derived_policy_profile(selection, source_truth_classification)
    candidate["policy_profile"] = profile
    candidate.pop("crime_event", None)
    candidate["signature"] = candidate_signature(selection, profile)


def apply_structure_constraints(
    candidates_document: Mapping[str, object],
    production_config: Mapping[str, object],
    compiled_constraints: Mapping[str, object],
    source_truth_classification: str,
) -> dict[str, object]:
    """2.1 구조 Dimension에만 잠긴 사용자·Source Truth 값을 적용한다."""
    next_document = deepcopy(dict(candidates_document))
    candidates = next_document.get("candidates")
    if not isinstance(candidates, list):
        raise ConfigurationError("v2.1 Constraint 적용 Candidate 배열이 없습니다.")
    fixed_values: dict[str, str] = {}
    user_constraints = production_config.get("user_case_constraints")
    if isinstance(user_constraints, list):
        for constraint in user_constraints:
            if not isinstance(constraint, Mapping) or constraint.get("status") != "LOCKED":
                continue
            field = constraint.get("field")
            value = constraint.get("value")
            if not isinstance(field, str) or not isinstance(value, str):
                raise ConfigurationError("v2.1 LOCKED Constraint 형식이 올바르지 않습니다.")
            fixed_values[field] = value
    compiled_rules = compiled_constraints.get("must_use")
    if isinstance(compiled_rules, list):
        for rule in compiled_rules:
            values = rule.get("values") if isinstance(rule, Mapping) else None
            field = rule.get("field") if isinstance(rule, Mapping) else None
            if isinstance(field, str) and isinstance(values, list) and len(values) == 1:
                value = values[0]
                if isinstance(value, str):
                    fixed_values[field] = value
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("v2.1 Constraint 적용 Candidate가 객체가 아닙니다.")
        selection = candidate.get("selection")
        if not isinstance(selection, dict):
            raise ConfigurationError("v2.1 Constraint 적용 Selection이 객체가 아닙니다.")
        unknown_fields = sorted(set(fixed_values) - set(selection))
        if unknown_fields:
            raise ConfigurationError(
                f"v2.1 Constraint가 구조 Dimension에 없습니다: fields={unknown_fields}"
            )
        selection.update(fixed_values)
        refresh_candidate_structure(candidate, source_truth_classification)
    signatures = [
        candidate.get("signature") for candidate in candidates if isinstance(candidate, Mapping)
    ]
    if len(signatures) != len(set(signatures)):
        raise ConfigurationError("v2.1 Constraint 적용 후 Candidate 구조가 충돌했습니다.")
    return next_document


def bounded_dimension_value(
    current: str,
    maximum: object,
    allowed_order: tuple[str, ...],
) -> str:
    """순서형 제작 Dimension을 명시된 Project 상한으로 제한한다."""
    if not isinstance(maximum, str) or maximum not in allowed_order:
        raise ConfigurationError(f"제작 상한 값이 올바르지 않습니다: maximum={maximum!r}")
    if current not in allowed_order:
        raise ConfigurationError(f"제작 Dimension 값이 올바르지 않습니다: current={current!r}")
    return allowed_order[min(allowed_order.index(current), allowed_order.index(maximum))]


def apply_production_limits(
    candidates_document: Mapping[str, object],
    project_constraints: Mapping[str, object],
    source_truth_classification: str,
) -> dict[str, object]:
    """구조 후보의 제작 Dimension을 Project의 명시적 상한 안에 결속한다."""
    limits = project_constraints.get("production_limits")
    if not isinstance(limits, Mapping):
        raise ConfigurationError("v2.1 Project production_limits 객체가 필요합니다.")
    next_document = deepcopy(dict(candidates_document))
    candidates = next_document.get("candidates")
    if not isinstance(candidates, list):
        raise ConfigurationError("v2.1 제작 상한 적용 Candidate 배열이 없습니다.")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("v2.1 제작 상한 적용 Candidate가 객체가 아닙니다.")
        selection = candidate.get("selection")
        if not isinstance(selection, dict):
            raise ConfigurationError("v2.1 제작 상한 적용 Selection이 객체가 아닙니다.")
        for field, allowed_order in ORDERED_PRODUCTION_LEVELS.items():
            current = selection.get(field)
            if not isinstance(current, str):
                raise ConfigurationError(f"v2.1 제작 Dimension 문자열이 없습니다: field={field}")
            selection[field] = bounded_dimension_value(
                current,
                limits.get(f"max_{field}"),
                allowed_order,
            )
        max_locations = limits.get("max_locations")
        max_characters = limits.get("max_major_characters")
        if not isinstance(max_locations, int) or not isinstance(max_characters, int):
            raise ConfigurationError("v2.1 장소·인물 제작 상한 정수가 필요합니다.")
        location_count = selection.get("location_count")
        character_count = selection.get("major_character_count")
        if not isinstance(location_count, str) or not isinstance(character_count, str):
            raise ConfigurationError("v2.1 장소·인물 제작 Dimension 문자열이 필요합니다.")
        bounded_locations = min(
            int(location_count.rpartition("_")[2]),
            max_locations,
        )
        selection["location_count"] = f"LOCATIONS_{bounded_locations}"
        selection["major_character_count"] = (
            f"MAJOR_{min(int(character_count.rpartition('_')[2]), max_characters)}"
        )
        if limits.get("allow_child_actor") is False:
            selection["child_actor_use"] = "NONE"
        if limits.get("allow_moving_vehicle") is False:
            selection["vehicle_scene"] = "NONE"
        refresh_candidate_structure(candidate, source_truth_classification)
    return next_document


def generate_candidates(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    source_truth_classification: str,
) -> dict[str, object]:
    """자연어 사건을 만들지 않고 2.1 Candidate 구조만 생성한다."""
    validate_generator_inputs(project_id, story_seed, candidate_count)
    dimension_items = ordered_dimensions(require_dimensions(runtime["catalog"]))
    candidates: list[dict[str, object]] = []
    signatures: set[str] = set()
    for index in range(candidate_count):
        raw_selection = {
            name: choose_dimension_value(
                choices,
                story_seed,
                name,
                index,
                dimension_index,
            )
            for dimension_index, (name, choices) in enumerate(dimension_items)
        }
        selection = normalized_event_selection(raw_selection, index)
        profile = derived_policy_profile(selection, source_truth_classification)
        signature = candidate_signature(selection, profile)
        if signature in signatures:
            raise ConfigurationError(
                f"v2.1 Variation Candidate 구조 서명이 충돌했습니다: candidate_index={index}"
            )
        signatures.add(signature)
        candidates.append(
            {
                "candidate_id": f"VAR-{index + 1:02d}",
                **runtime_candidate_metadata(runtime, 0, index),
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
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("v2.1 Candidate 객체가 필요합니다.")
        selection = candidate.get("selection")
        if not isinstance(selection, dict):
            raise ConfigurationError("v2.1 Candidate Selection 객체가 필요합니다.")
        selection["genre"] = genre
        refresh_candidate_structure(candidate, source_truth_classification)
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
    """Constraint를 적용한 구조 후보를 Event Brief 생성 전 단계로 반환한다."""
    dimensions = require_dimensions(runtime["catalog"])
    truth_constraints = source_truth_project_constraints(
        project_constraints,
        source_truth_contract,
        set(dimensions),
    )
    compiled_constraints = compile_project_constraints(
        truth_constraints,
        runtime["catalog"],
        projection_contract,
    )

    del story_history, novelty_thresholds, max_batches
    result = generate_batch(
        project_id,
        story_seed,
        eligible_candidate_count,
        runtime,
        source_truth_classification,
        production_config,
        channel,
        0,
    )
    result = apply_structure_constraints(
        result,
        production_config,
        compiled_constraints,
        source_truth_classification,
    )
    result = apply_production_limits(
        result,
        truth_constraints,
        source_truth_classification,
    )
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        raise ConfigurationError("v2.1 최종 Candidate 배열이 없습니다.")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("v2.1 최종 Candidate가 객체가 아닙니다.")
        refresh_candidate_structure(candidate, source_truth_classification)
    return result

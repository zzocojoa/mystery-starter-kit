"""v2.1.0 구체 대인범죄 사건 우선 Eligible Pool Variation Engine."""

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from typing import cast

from VALIDATORS.crime_event import DEFAULT_DEVELOPMENT_FUNCTIONS, development_families
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.project_constraints import compile_project_constraints
from VALIDATORS.source_truth_contract import source_truth_project_constraints
from VALIDATORS.variation_engines.common import (
    apply_compiled_required_values,
    apply_runtime_metadata,
    apply_user_case_constraints,
    candidate_policy_profile,
    choose_dimension_value,
    generate_eligible_pool_with_batch_generator,
    require_dimensions,
    runtime_candidate_metadata,
    validate_generator_inputs,
    variation_document_metadata,
)
from VALIDATORS.variation_registry import VariationRuntime

EVENT_DIMENSION_ORDER = (
    "incident_type",
    "core_action_type",
    "relationship_context",
    "harm_classification",
    "motive_category",
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
    primary = normalized.get("incident_type")
    if primary in DIRECT_ACTION_BY_CRIME:
        action = DIRECT_ACTION_BY_CRIME[cast(str, primary)]
    elif primary in {"DATING_VIOLENCE", "DOMESTIC_VIOLENCE"}:
        action = RELATIONAL_ACTIONS[candidate_index % len(RELATIONAL_ACTIONS)]
    else:
        raise ConfigurationError(
            f"v2.1 중심 범죄가 허용 범위를 벗어났습니다: incident_type={primary!r}"
        )
    normalized["core_action_type"] = action
    normalized["harm_classification"] = HARM_BY_ACTION[action]
    if primary == "DATING_VIOLENCE":
        normalized["relationship_context"] = "DATING_PARTNER"
    elif primary == "DOMESTIC_VIOLENCE":
        normalized["relationship_context"] = "FAMILY_OR_HOUSEHOLD"
    return normalized


def crime_event_outline(
    selection: Mapping[str, str],
    source_truth_classification: str,
) -> dict[str, object]:
    """행위·관계·피해와 후반 Reveal을 분리한 Candidate 사건 개요를 만든다."""
    primary = selection["incident_type"]
    action = selection["core_action_type"]
    harm = selection["harm_classification"]
    related: list[str] = []
    if primary != action:
        related.append(action)
    if primary not in {"DATING_VIOLENCE", "DOMESTIC_VIOLENCE"}:
        relationship = selection["relationship_context"]
        if relationship == "DATING_PARTNER":
            related.append("DATING_VIOLENCE")
        elif relationship == "FAMILY_OR_HOUSEHOLD":
            related.append("DOMESTIC_VIOLENCE")
    functions = sorted(
        {
            function
            for family in development_families(primary, action)
            for function in DEFAULT_DEVELOPMENT_FUNCTIONS[family]
        }
    )
    truth_locked = source_truth_classification != "ORIGINAL_FICTION"
    motive = "UNKNOWN_UNLESS_EVIDENCED" if truth_locked else selection["motive_category"]
    act_summary = (
        "검증된 사건 원장 범위 안의 대인범죄 행위만 사건화한다."
        if truth_locked
        else f"CHAR-01의 {action} 행위가 HARM-01의 {harm} 피해를 낳는 중심 사건"
    )
    harm_result = "VERIFIED_HARM_ONLY" if truth_locked else f"{harm} 피해 결과"
    reveal_summaries = {
        "CULPRIT": "책임 행위자 공개",
        "MOTIVE": "검증되거나 창작 계약에 고정된 동기 공개",
        "METHOD": "비실행적 범행 방식 요약 공개",
        "HARM_RESULT": "피해 결과 공개",
    }
    return {
        "event_id": "EVENT-01",
        "primary_crime": primary,
        "related_crimes": sorted(set(related)),
        "core_action_type": action,
        "relationship_context": selection["relationship_context"],
        "actor_ids": ["CHAR-01"],
        "victim_ids": ["CHAR-02"],
        "motive": motive,
        "act_summary": act_summary,
        "harm_ids": ["HARM-01"],
        "harm_result": harm_result,
        "harm_classifications": [harm],
        "protagonist_goal": selection["protagonist_goal"],
        "protagonist_risk": selection["protagonist_risk"],
        "depiction_mode": selection["depiction_mode"],
        "development_functions": functions,
        "reveal_targets": [
            {
                "reveal_target_id": f"REVEAL-TARGET-{index:02d}",
                "target_type": target_type,
                "summary": reveal_summaries[target_type],
                "planned_phase": "LATE",
                "planned_segment_id": None,
            }
            for index, target_type in enumerate(
                ("CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"),
                1,
            )
        ],
        "method_detail_level": "NON_ACTIONABLE_SUMMARY_ONLY",
        "centrality": "CENTRAL",
        "truth_status": ("EVIDENCE_LOCK_REQUIRED" if truth_locked else "ORIGINAL_FICTION"),
    }


def event_candidate_signature(
    selection: Mapping[str, str],
    policy_profile: Mapping[str, str],
    event: Mapping[str, object],
) -> str:
    """Selection·Policy Profile·사건 개요를 함께 서명한다."""
    payload = {
        "selection": dict(selection),
        "policy_profile": dict(policy_profile),
        "crime_event": dict(event),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def candidate_index(candidate: Mapping[str, object]) -> int:
    """Batch Candidate ID의 1-base 번호를 0-base Index로 변환한다."""
    value = candidate.get("batch_candidate_id")
    if not isinstance(value, str):
        return 0
    suffix = value.rpartition("-")[2]
    return max(0, int(suffix) - 1) if suffix.isdigit() else 0


def refresh_candidate_event(
    candidate: dict[str, object],
    source_truth_classification: str,
) -> None:
    """Constraint 적용 뒤 Candidate 사건과 서명을 현재 Selection에 다시 결속한다."""
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
    profile = candidate_policy_profile(selection, source_truth_classification)
    event = crime_event_outline(selection, source_truth_classification)
    candidate["policy_profile"] = profile
    candidate["crime_event"] = event
    candidate["signature"] = event_candidate_signature(selection, profile, event)


def generate_candidates(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    runtime: VariationRuntime,
    source_truth_classification: str,
) -> dict[str, object]:
    """구체 대인범죄 사건 구조를 먼저 가진 2.1 Candidate Batch를 생성한다."""
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
        profile = candidate_policy_profile(selection, source_truth_classification)
        event = crime_event_outline(selection, source_truth_classification)
        signature = event_candidate_signature(selection, profile, event)
        if signature in signatures:
            raise ConfigurationError(
                f"v2.1 Variation Candidate 사건 서명이 충돌했습니다: candidate_index={index}"
            )
        signatures.add(signature)
        candidates.append(
            {
                "candidate_id": f"VAR-{index + 1:02d}",
                **runtime_candidate_metadata(runtime, 0, index),
                "selection": selection,
                "policy_profile": profile,
                "crime_event": event,
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
        refresh_candidate_event(candidate, source_truth_classification)
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
    """Constraint 적용 뒤에도 사건 개요를 다시 결속하는 2.1 Eligible Pool을 만든다."""
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

    def constraint_aware_batch(
        project_id: str,
        story_seed: str,
        candidate_count: int,
        runtime: VariationRuntime,
        source_truth_classification: str,
        production_config: Mapping[str, object],
        channel: Mapping[str, object],
        batch_nonce: int,
    ) -> dict[str, object]:
        """공통 Pool의 재적용 전에 같은 Constraint로 사건 개요를 동기화한다."""
        batch = generate_batch(
            project_id,
            story_seed,
            candidate_count,
            runtime,
            source_truth_classification,
            production_config,
            channel,
            batch_nonce,
        )
        batch = apply_user_case_constraints(batch, production_config)
        batch = apply_compiled_required_values(
            batch,
            compiled_constraints,
            source_truth_classification,
        )
        candidates = batch.get("candidates")
        if not isinstance(candidates, list):
            raise ConfigurationError("v2.1 Constraint 적용 Candidate 배열이 없습니다.")
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ConfigurationError("v2.1 Constraint 적용 Candidate가 객체가 아닙니다.")
            refresh_candidate_event(candidate, source_truth_classification)
        return batch

    result = generate_eligible_pool_with_batch_generator(
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
        constraint_aware_batch,
    )
    refreshed = deepcopy(result)
    candidates = refreshed.get("candidates")
    if not isinstance(candidates, list):
        raise ConfigurationError("v2.1 최종 Candidate 배열이 없습니다.")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("v2.1 최종 Candidate가 객체가 아닙니다.")
        refresh_candidate_event(candidate, source_truth_classification)
    return refreshed

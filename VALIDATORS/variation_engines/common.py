"""Versioned Variation Engine이 공유하는 결정론적 생성·Pool Helper."""

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
from math import gcd
from typing import Protocol

from VALIDATORS.candidate_eligibility import build_candidate_eligibility
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.novelty import evaluate_variation_precheck
from VALIDATORS.project_constraints import compile_project_constraints
from VALIDATORS.source_truth import SOURCE_TRUTH_CLASSIFICATIONS
from VALIDATORS.source_truth_contract import source_truth_project_constraints
from VALIDATORS.variation_registry import VariationRuntime

PROJECT_ID_PATTERN = re.compile(r"^PRJ-[0-9]{3,}$")
USER_CASE_STATUSES = {"LOCKED", "FLEXIBLE", "UNKNOWN"}
POLICY_DIMENSIONS = (
    "genre",
    "threat_type",
    "trusted_domain",
    "safe_domain_betrayal",
    "responsible_agent_structure",
    "information_mechanism",
    "clue_mechanism",
    "reveal_mode",
    "final_proof_mechanism",
    "victim_agency_mode",
    "technical_dependency_level",
    "production_complexity",
    "episode_theme",
    "location_count",
    "major_character_count",
    "special_effect_level",
    "child_actor_use",
    "vehicle_scene",
    "graphic_violence",
    "incident_type",
    "culprit_structure",
    "primary_twist",
    "pressure_engine",
)


class BatchGenerator(Protocol):
    """단일 Version Engine Batch Generator 계약."""

    def __call__(
        self,
        project_id: str,
        story_seed: str,
        candidate_count: int,
        runtime: VariationRuntime,
        source_truth_classification: str,
        production_config: Mapping[str, object],
        channel: Mapping[str, object],
        batch_nonce: int,
    ) -> dict[str, object]:
        """원본 Batch 식별자를 보존한 Candidate 문서를 반환한다."""


def require_dimensions(catalog: Mapping[str, object]) -> dict[str, list[str]]:
    """Variation Catalog의 문자열 선택지 사전을 엄격하게 읽는다."""
    value = catalog.get("dimensions")
    if not isinstance(value, Mapping):
        raise ConfigurationError("variation_catalog.dimensions 객체가 필요합니다.")
    dimensions: dict[str, list[str]] = {}
    for name, choices in value.items():
        if (
            not isinstance(name, str)
            or not isinstance(choices, list)
            or not choices
            or not all(isinstance(choice, str) for choice in choices)
        ):
            raise ConfigurationError(
                f"Variation Dimension 형식이 올바르지 않습니다: dimension={name!r}"
            )
        dimensions[name] = list(choices)
    if not dimensions:
        raise ConfigurationError("Variation Dimension이 하나 이상 필요합니다.")
    return dimensions


def seed_offset(seed: str, dimension: str, size: int) -> int:
    """Seed와 Dimension 이름으로 안정적인 선택 시작점을 계산한다."""
    digest = sha256(f"{seed}:{dimension}".encode()).hexdigest()
    return int(digest[:16], 16) % size


def coprime_step(preferred_step: int, size: int) -> int:
    """선택지 전체를 순회할 수 있는 가장 가까운 보폭을 반환한다."""
    if size < 1:
        raise ConfigurationError(f"Variation 선택지 개수가 올바르지 않습니다: size={size}")
    step = preferred_step
    while gcd(step, size) != 1:
        step += 1
    return step


def choose_dimension_value(
    choices: list[str],
    seed: str,
    dimension: str,
    candidate_index: int,
    dimension_index: int,
) -> str:
    """Seed, 후보와 차원마다 다른 보폭으로 선택지를 결정한다."""
    offset = seed_offset(seed, dimension, len(choices))
    step = coprime_step(dimension_index * 2 + 1, len(choices))
    return choices[(offset + candidate_index * step) % len(choices)]


def candidate_policy_profile(
    selection: Mapping[str, str],
    source_truth_classification: str,
) -> dict[str, str]:
    """Candidate 구조를 CORE 정책 비교용 최소 Profile로 변환한다."""
    if source_truth_classification not in SOURCE_TRUTH_CLASSIFICATIONS:
        raise ConfigurationError(
            "Source Truth Classification이 올바르지 않습니다: "
            f"value={source_truth_classification!r}"
        )
    required_values = {name: selection.get(name) for name in POLICY_DIMENSIONS}
    missing = sorted(key for key, value in required_values.items() if not isinstance(value, str))
    if missing:
        raise ConfigurationError(
            f"Candidate Policy Profile 입력 Dimension이 없습니다: fields={missing}"
        )
    return {
        **{name: str(required_values[name]) for name in POLICY_DIMENSIONS},
        "source_truth_classification": source_truth_classification,
    }


def candidate_signature(
    selection: Mapping[str, str],
    policy_profile: Mapping[str, str],
) -> str:
    """후보 Dimension과 정책 Profile을 결합한 구조 서명을 만든다."""
    values = {
        **{f"selection.{key}": value for key, value in selection.items()},
        **{f"profile.{key}": value for key, value in policy_profile.items()},
    }
    payload = "|".join(f"{key}={values[key]}" for key in sorted(values))
    return sha256(payload.encode()).hexdigest()


def legacy_candidate_signature(selection: Mapping[str, str]) -> str:
    """v1.0 Generator의 Selection-only Signature를 정확히 재현한다."""
    payload = "|".join(f"{key}={selection[key]}" for key in sorted(selection))
    return sha256(payload.encode()).hexdigest()


def runtime_candidate_metadata(
    runtime: VariationRuntime,
    batch_nonce: int,
    candidate_index: int,
) -> dict[str, object]:
    """Candidate에 고정할 Runtime과 원본 Batch 식별자를 반환한다."""
    return {
        "origin_batch_id": f"BATCH-{batch_nonce + 1:02d}",
        "batch_candidate_id": f"BVAR-{candidate_index + 1:02d}",
        "variation_engine_version": runtime["engine_version"],
        "variation_catalog_version": runtime["catalog_version"],
        "catalog_sha256": runtime["catalog_sha256"],
        "algorithm_sha256": runtime["algorithm_sha256"],
        "implementation_sha256": runtime["implementation_sha256"],
    }


def variation_document_metadata(runtime: VariationRuntime) -> dict[str, object]:
    """Variation 문서 최상위에 고정할 Runtime 식별자를 반환한다."""
    return {
        "variation_engine_version": runtime["engine_version"],
        "variation_catalog_version": runtime["catalog_version"],
        "catalog_sha256": runtime["catalog_sha256"],
        "algorithm_sha256": runtime["algorithm_sha256"],
        "implementation_sha256": runtime["implementation_sha256"],
    }


def validate_generator_inputs(
    project_id: str,
    story_seed: str,
    candidate_count: int,
) -> None:
    """모든 Variation Engine이 공유하는 입력 계약을 검증한다."""
    if PROJECT_ID_PATTERN.fullmatch(project_id) is None:
        raise ConfigurationError(f"Project ID 형식이 올바르지 않습니다: {project_id!r}")
    if not story_seed.strip():
        raise ConfigurationError("Story Variation Seed는 비어 있을 수 없습니다.")
    if candidate_count < 3:
        raise ConfigurationError(
            f"비교 가능한 Variation 후보는 3개 이상이어야 합니다: count={candidate_count}"
        )


def apply_compiled_required_values(
    candidates_document: Mapping[str, object],
    compiled_constraints: Mapping[str, object],
    source_truth_classification: str,
) -> dict[str, object]:
    """단일 IN Rule을 Candidate Selection에 고정하고 Signature를 갱신한다."""
    next_document = deepcopy(dict(candidates_document))
    candidates = next_document.get("candidates")
    rules = compiled_constraints.get("must_use")
    if not isinstance(candidates, list) or not isinstance(rules, list):
        raise ConfigurationError("Compiled Constraint 또는 Candidate 배열이 없습니다.")
    fixed_values = {
        str(rule["field"]): str(rule["values"][0])
        for rule in rules
        if isinstance(rule, Mapping)
        and isinstance(rule.get("field"), str)
        and isinstance(rule.get("values"), list)
        and len(rule["values"]) == 1
    }
    signatures: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ConfigurationError("Variation Candidate 객체가 필요합니다.")
        selection = candidate.get("selection")
        if not isinstance(selection, dict):
            raise ConfigurationError("Variation Candidate selection 객체가 필요합니다.")
        selection.update(fixed_values)
        policy_profile = candidate.get("policy_profile")
        if isinstance(policy_profile, Mapping):
            profile = candidate_policy_profile(selection, source_truth_classification)
            candidate["policy_profile"] = profile
            signature = candidate_signature(selection, profile)
        else:
            signature = legacy_candidate_signature(selection)
        candidate["signature"] = signature
        if signature in signatures:
            candidate["batch_duplicate"] = True
        signatures.add(signature)
    return next_document


def apply_runtime_metadata(
    candidates_document: Mapping[str, object],
    runtime: VariationRuntime,
    batch_nonce: int,
) -> dict[str, object]:
    """Generator 결과에 검증된 Runtime Metadata를 덮어쓴다."""
    next_document = deepcopy(dict(candidates_document))
    next_document.update(variation_document_metadata(runtime))
    candidates = next_document.get("candidates")
    if not isinstance(candidates, list):
        raise ConfigurationError("Variation Candidate 배열이 없습니다.")
    for candidate_index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ConfigurationError("Variation Candidate 객체가 필요합니다.")
        candidate.update(runtime_candidate_metadata(runtime, batch_nonce, candidate_index))
    return next_document


def selection_similarity(
    left: Mapping[str, object],
    right: Mapping[str, object],
) -> float:
    """두 Candidate Selection의 동일 Dimension 비율을 반환한다."""
    dimensions = sorted(set(left) | set(right))
    if not dimensions:
        return 1.0
    matches = sum(left.get(dimension) == right.get(dimension) for dimension in dimensions)
    return matches / len(dimensions)


def candidate_result_ids(
    document: Mapping[str, object],
    expected_result: str,
) -> set[str]:
    """판정 Artifact에서 지정 Result의 Candidate ID를 반환한다."""
    results = document.get("candidate_results")
    if not isinstance(results, list):
        return set()
    return {
        str(result["candidate_id"])
        for result in results
        if isinstance(result, Mapping)
        and isinstance(result.get("candidate_id"), str)
        and result.get("result") == expected_result
    }


def require_user_case_constraints(
    production_config: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """USER_CASE의 Field, Value, Status 계약을 엄격하게 읽는다."""
    source_mode = production_config.get("story_source_mode")
    constraints = production_config.get("user_case_constraints")
    if source_mode != "USER_CASE":
        if constraints is not None:
            raise ConfigurationError(
                "USER_CASE가 아닌 Production Config에는 user_case_constraints를 둘 수 없습니다."
            )
        return []
    if (
        not isinstance(constraints, list)
        or not constraints
        or not all(isinstance(constraint, Mapping) for constraint in constraints)
    ):
        raise ConfigurationError(
            "USER_CASE에는 하나 이상의 user_case_constraints 객체가 필요합니다."
        )
    fields: list[str] = []
    for constraint in constraints:
        field = constraint.get("field")
        status = constraint.get("status")
        value = constraint.get("value")
        if not isinstance(field, str) or not field:
            raise ConfigurationError("USER_CASE Constraint field 문자열이 필요합니다.")
        if status not in USER_CASE_STATUSES:
            raise ConfigurationError(
                f"USER_CASE Constraint status가 올바르지 않습니다: field={field}, status={status!r}"
            )
        if status == "UNKNOWN" and value is not None:
            raise ConfigurationError(f"UNKNOWN Constraint value는 null이어야 합니다: field={field}")
        if status != "UNKNOWN" and (not isinstance(value, str) or not value):
            raise ConfigurationError(
                f"LOCKED/FLEXIBLE Constraint value 문자열이 필요합니다: field={field}"
            )
        fields.append(field)
    duplicate_fields = sorted({field for field in fields if fields.count(field) > 1})
    if duplicate_fields:
        raise ConfigurationError(
            f"USER_CASE Constraint field가 중복됩니다: fields={duplicate_fields}"
        )
    return list(constraints)


def apply_user_case_constraints(
    candidates_document: Mapping[str, object],
    production_config: Mapping[str, object],
) -> dict[str, object]:
    """USER_CASE의 LOCKED 값을 모든 후보에 적용하고 Signature를 다시 계산한다."""
    constraints = require_user_case_constraints(production_config)
    if not constraints:
        return deepcopy(dict(candidates_document))
    next_document = deepcopy(dict(candidates_document))
    candidates = next_document.get("candidates")
    if not isinstance(candidates, list) or not all(
        isinstance(candidate, dict) for candidate in candidates
    ):
        raise ConfigurationError("Variation Candidate 객체 배열이 필요합니다.")
    signatures: set[str] = set()
    for candidate in candidates:
        selection = candidate.get("selection")
        if not isinstance(selection, dict) or not all(
            isinstance(field, str) and isinstance(value, str) for field, value in selection.items()
        ):
            raise ConfigurationError("Variation Candidate selection 문자열 객체가 필요합니다.")
        missing_fields = sorted(
            field
            for constraint in constraints
            if isinstance((field := constraint.get("field")), str) and field not in selection
        )
        if missing_fields:
            raise ConfigurationError(
                "USER_CASE Constraint가 Variation Catalog Dimension에 없습니다: "
                f"fields={missing_fields}"
            )
        for constraint in constraints:
            field = constraint.get("field")
            value = constraint.get("value")
            if constraint.get("status") == "LOCKED":
                if not isinstance(field, str) or not isinstance(value, str):
                    raise ConfigurationError("검증된 LOCKED Constraint 형식이 손상됐습니다.")
                selection[field] = value
        policy_profile = candidate.get("policy_profile")
        if isinstance(policy_profile, dict):
            source_truth = policy_profile.get("source_truth_classification")
            if not isinstance(source_truth, str):
                raise ConfigurationError(
                    "Variation Candidate source_truth_classification 문자열이 필요합니다."
                )
            refreshed_profile = candidate_policy_profile(selection, source_truth)
            candidate["policy_profile"] = refreshed_profile
            signature = candidate_signature(selection, refreshed_profile)
        else:
            signature = legacy_candidate_signature(selection)
        if signature in signatures:
            raise ConfigurationError(
                "USER_CASE LOCKED 값 적용 후 Variation 후보가 충돌했습니다: "
                f"candidate_id={candidate.get('candidate_id')!r}"
            )
        signatures.add(signature)
        candidate["signature"] = signature
    return next_document


def generate_eligible_pool_with_batch_generator(
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
    batch_generator: BatchGenerator,
) -> dict[str, object]:
    """Novelty와 전체 Eligibility를 통과한 Candidate Pool을 재생성한다."""
    validate_generator_inputs(project_id, story_seed, eligible_candidate_count)
    if max_batches < 1:
        raise ConfigurationError("ELIGIBLE_CANDIDATE_POOL_EXHAUSTED: max_batches가 1 미만입니다.")
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
    accepted: list[dict[str, object]] = []
    accepted_signatures: set[str] = set()
    traces: list[dict[str, object]] = []
    for batch_nonce in range(max_batches):
        batch = batch_generator(
            project_id,
            story_seed,
            eligible_candidate_count,
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
        novelty = evaluate_variation_precheck(
            batch,
            story_history,
            novelty_thresholds,
        )
        eligibility = build_candidate_eligibility(
            production_config,
            compiled_constraints,
            channel,
            batch,
            novelty,
        )
        novelty_pass_ids = candidate_result_ids(novelty, "PASS")
        eligible_ids = candidate_result_ids(eligibility, "PASS")
        raw_candidates = batch.get("candidates")
        rejections: list[dict[str, object]] = []
        accepted_this_batch = 0
        if not isinstance(raw_candidates, list):
            raise ConfigurationError("생성된 Candidate 배열이 없습니다.")
        for candidate in raw_candidates:
            if not isinstance(candidate, Mapping):
                continue
            candidate_id = candidate.get("candidate_id")
            batch_candidate_id = candidate.get("batch_candidate_id")
            reasons: list[str] = []
            if len(accepted) >= eligible_candidate_count:
                reasons.append("ELIGIBLE_POOL_TARGET_REACHED")
            if candidate.get("batch_duplicate") is True:
                reasons.append("CANDIDATE_BATCH_DUPLICATED")
            if candidate_id not in novelty_pass_ids:
                reasons.append("NOVELTY_PRECHECK_FAILED")
            if candidate_id not in eligible_ids:
                reasons.append("CORE_ELIGIBILITY_FAILED")
            signature = candidate.get("signature")
            if not isinstance(signature, str) or signature in accepted_signatures:
                reasons.append("CANDIDATE_BATCH_DUPLICATED")
            selection = candidate.get("selection")
            internal_collision = False
            if isinstance(selection, Mapping):
                for existing in accepted:
                    existing_selection = existing.get("selection")
                    if (
                        isinstance(existing_selection, Mapping)
                        and selection_similarity(selection, existing_selection) >= 0.85
                    ):
                        internal_collision = True
                        break
            if internal_collision:
                reasons.append("CANDIDATE_INTERNAL_COLLISION")
            if reasons:
                rejections.append(
                    {
                        "batch_candidate_id": batch_candidate_id,
                        "codes": sorted(set(reasons)),
                    }
                )
                continue
            accepted_candidate = deepcopy(dict(candidate))
            accepted_candidate.pop("batch_duplicate", None)
            accepted.append(accepted_candidate)
            accepted_signatures.add(str(signature))
            accepted_this_batch += 1
        traces.append(
            {
                "batch_id": f"BATCH-{batch_nonce + 1:02d}",
                "batch_nonce": batch_nonce,
                "generated_count": len(raw_candidates),
                "novelty_pass_count": len(novelty_pass_ids),
                "eligible_count": len(eligible_ids),
                "accepted_count": accepted_this_batch,
                "rejections": rejections,
            }
        )
        if len(accepted) == eligible_candidate_count:
            break
    if len(accepted) != eligible_candidate_count:
        raise ConfigurationError(
            "ELIGIBLE_CANDIDATE_POOL_EXHAUSTED: "
            f"required={eligible_candidate_count}, actual={len(accepted)}, "
            f"max_batches={max_batches}"
        )
    for index, candidate in enumerate(accepted, 1):
        candidate["candidate_id"] = f"VAR-{index:02d}"
    return {
        "project_id": project_id,
        "story_seed_hash": sha256(story_seed.encode()).hexdigest(),
        **variation_document_metadata(runtime),
        "candidate_count": eligible_candidate_count,
        "candidates": accepted,
        "batch_trace": traces,
        "approved_candidate_id": None,
        "override": None,
    }

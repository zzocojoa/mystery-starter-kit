"""재현 가능한 다축 Story Variation 후보 생성."""

import re
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from math import gcd

from VALIDATORS.candidate_eligibility import (
    production_feasibility_passes,
    project_constraints_pass,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.requirements import crime_v2_candidate_policy_applies
from VALIDATORS.source_truth import SOURCE_TRUTH_CLASSIFICATIONS

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
SAFE_GENERATION_VALUES: dict[str, frozenset[str]] = {
    "threat_type": frozenset({"CRIME", "PREDATORY"}),
    "safe_domain_betrayal": frozenset(
        {"TRUST_ABUSED", "AUTHORITY_ABUSED", "CARE_EXPECTATION_BETRAYED"}
    ),
    "responsible_agent_structure": frozenset(
        {"SINGLE_AGENT", "DUAL_AGENTS", "COMPLICIT_GROUP"}
    ),
    "information_mechanism": frozenset(
        {"TESTIMONIAL_CONTRADICTION", "RELATIONAL_DISCLOSURE", "OWNERSHIP_CHAIN"}
    ),
    "clue_mechanism": frozenset(
        {"LINGUISTIC", "BEHAVIORAL", "RELATIONAL", "DOCUMENTARY"}
    ),
    "reveal_mode": frozenset(
        {"RELATIONAL_REFRAME", "TESTIMONIAL_COLLAPSE", "OWNERSHIP_RECONSTRUCTION"}
    ),
    "final_proof_mechanism": frozenset(
        {"INDEPENDENT_NONTECHNICAL_GROUNDS", "CLAIM_EVIDENCE_CHAIN"}
    ),
    "victim_agency_mode": frozenset(
        {"BOUNDARY_RESTORED", "EVIDENCE_PRESERVED", "INFORMED_EXIT"}
    ),
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
    missing = sorted(
        key for key, value in required_values.items() if not isinstance(value, str)
    )
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


def generate_variation_candidates_for_project(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    catalog: Mapping[str, object],
    source_truth_classification: str,
    production_config: Mapping[str, object],
    project_constraints: Mapping[str, object],
    channel: Mapping[str, object],
) -> dict[str, object]:
    """Project Channel 정책에 맞는 구조 후보군을 생성한다."""
    apply_v2_policy = crime_v2_candidate_policy_applies(production_config, channel)
    selected: list[dict[str, object]] = []
    signatures: set[str] = set()
    max_batches = 64
    for batch_nonce in range(max_batches):
        batch = generate_variation_candidates_with_policy(
            project_id,
            f"{story_seed}:batch:{batch_nonce}",
            candidate_count,
            catalog,
            source_truth_classification,
            apply_v2_policy,
        )
        constrained = apply_user_case_constraints(batch, production_config)
        candidates = constrained.get("candidates")
        if not isinstance(candidates, list):
            raise ConfigurationError("생성된 Candidate 배열이 손상되었습니다.")
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            selection = candidate.get("selection")
            profile = candidate.get("policy_profile")
            signature = candidate.get("signature")
            if (
                isinstance(selection, Mapping)
                and isinstance(profile, Mapping)
                and isinstance(signature, str)
                and signature not in signatures
                and project_constraints_pass(project_constraints, selection)
                and production_feasibility_passes(profile, project_constraints)
            ):
                signatures.add(signature)
                selected.append(dict(candidate))
            if len(selected) == candidate_count:
                break
        if len(selected) == candidate_count:
            break
    if len(selected) != candidate_count:
        raise ConfigurationError(
            "Project Constraint를 통과하는 Variation 후보를 충분히 생성하지 못했습니다: "
            f"required={candidate_count}, actual={len(selected)}, max_batches={max_batches}"
        )
    for index, candidate in enumerate(selected, 1):
        candidate["candidate_id"] = f"VAR-{index:02d}"
    return {
        "project_id": project_id,
        "story_seed_hash": sha256(story_seed.encode()).hexdigest(),
        "candidate_count": candidate_count,
        "candidates": selected,
        "approved_candidate_id": None,
        "override": None,
    }


def generate_variation_candidates(
    project_id: str,
    story_seed: str,
    candidate_count: int,
    catalog: Mapping[str, object],
    source_truth_classification: str,
) -> dict[str, object]:
    """Channel Context가 없는 호출에서는 v2 전용 필터 없이 후보군을 생성한다."""
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
    """명시된 정책 적용 여부로 구조적으로 구분되는 후보군을 생성한다."""
    if PROJECT_ID_PATTERN.fullmatch(project_id) is None:
        raise ConfigurationError(f"Project ID 형식이 올바르지 않습니다: {project_id!r}")
    if not story_seed.strip():
        raise ConfigurationError("Story Variation Seed는 비어 있을 수 없습니다.")
    if candidate_count < 3:
        raise ConfigurationError(
            f"비교 가능한 Variation 후보는 3개 이상이어야 합니다: count={candidate_count}"
        )

    dimensions = require_dimensions(catalog)
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
                "selection": selection,
                "policy_profile": policy_profile,
                "signature": signature,
                "selection_status": "PENDING",
            }
        )

    return {
        "project_id": project_id,
        "story_seed_hash": sha256(story_seed.encode()).hexdigest(),
        "candidate_count": candidate_count,
        "candidates": candidates,
        "approved_candidate_id": None,
        "override": None,
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
    if not isinstance(constraints, list) or not constraints or not all(
        isinstance(constraint, Mapping) for constraint in constraints
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
            raise ConfigurationError(
                f"UNKNOWN Constraint value는 null이어야 합니다: field={field}"
            )
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
            isinstance(field, str) and isinstance(value, str)
            for field, value in selection.items()
        ):
            raise ConfigurationError("Variation Candidate selection 문자열 객체가 필요합니다.")
        missing_fields = sorted(
            field
            for constraint in constraints
            if isinstance((field := constraint.get("field")), str)
            and field not in selection
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
        if not isinstance(policy_profile, dict):
            raise ConfigurationError("Variation Candidate policy_profile 객체가 필요합니다.")
        source_truth = policy_profile.get("source_truth_classification")
        if not isinstance(source_truth, str):
            raise ConfigurationError(
                "Variation Candidate source_truth_classification 문자열이 필요합니다."
            )
        refreshed_profile = candidate_policy_profile(selection, source_truth)
        candidate["policy_profile"] = refreshed_profile
        signature = candidate_signature(selection, refreshed_profile)
        if signature in signatures:
            raise ConfigurationError(
                "USER_CASE LOCKED 값 적용 후 Variation 후보가 충돌했습니다: "
                f"candidate_id={candidate.get('candidate_id')!r}"
            )
        signatures.add(signature)
        candidate["signature"] = signature
    return next_document


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
        raise ConfigurationError(
            f"승인할 Variation 후보가 없습니다: candidate_id={candidate_id}"
        )

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

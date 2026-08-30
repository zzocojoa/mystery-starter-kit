"""Core가 소유하는 Variation Candidate 적격성 판정."""

from collections.abc import Mapping

from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.models import ValidationIssue
from VALIDATORS.novelty import variation_precheck_source_hash
from VALIDATORS.source_truth import require_source_truth_classification

TRUSTED_DOMAINS = {
    "SPOUSE",
    "ROMANTIC_PARTNER",
    "FAMILY",
    "FRIEND",
    "EMPLOYMENT",
    "RELIGIOUS_AUTHORITY",
    "EDUCATIONAL_AUTHORITY",
    "MEDICAL_CARE",
    "HOME_SAFETY",
    "NEIGHBOR",
    "ONLINE_COMMUNITY",
    "FINANCIAL_TRUST",
}
DEFAULT_REJECTED_STRUCTURES = {
    "NO_CRIME",
    "NO_CULPRIT",
    "VICTIM_SELF_ENGINEERED",
    "SELF_CREATED_TRAP",
    "TW-14_SELF_CREATED_TRAP",
    "SYSTEMIC_CAUSE",
}
TECHNICAL_REVEAL_VALUES = {
    "TIMESTAMP_CORRECTION",
    "MACHINE_RECORD_RESOLUTION",
}
TECHNICAL_FINAL_PROOF_VALUES = {
    "SINGLE_TECHNICAL_RECORD",
    "METADATA_ONLY",
    "CCTV_ONLY",
}
PROFILE_SELECTION_FIELDS = (
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
    "incident_type",
    "culprit_structure",
    "primary_twist",
    "pressure_engine",
    "technical_dependency_level",
    "production_complexity",
    "location_count",
    "major_character_count",
    "special_effect_level",
    "child_actor_use",
    "vehicle_scene",
    "graphic_violence",
    "episode_theme",
)


def eligibility_input_hashes(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
) -> dict[str, str]:
    """적격성 판정 입력의 정규 Hash를 반환한다."""
    return {
        "production_config": document_sha256(production_config),
        "channel_dna": document_sha256(channel),
        "variation_candidates": variation_precheck_source_hash(variations),
        "novelty_precheck": document_sha256(novelty_precheck),
    }


def novelty_result_map(document: Mapping[str, object]) -> dict[str, str]:
    """Novelty 결과를 Candidate ID로 색인한다."""
    values = document.get("candidate_results")
    if not isinstance(values, list):
        return {}
    return {
        str(item["candidate_id"]): str(item["result"])
        for item in values
        if isinstance(item, Mapping)
        and isinstance(item.get("candidate_id"), str)
        and isinstance(item.get("result"), str)
    }


def enabled_capability(
    channel: Mapping[str, object],
    capability_id: str,
) -> Mapping[str, object] | None:
    """활성 Capability 정책 객체를 반환한다."""
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return None
    value = capabilities.get(capability_id)
    if not isinstance(value, Mapping) or value.get("enabled") is False:
        return None
    return value


def locked_constraints_pass(
    production_config: Mapping[str, object],
    selection: Mapping[str, object],
) -> bool:
    """LOCKED 사용자 제약이 Candidate 선택값과 일치하는지 판정한다."""
    constraints = production_config.get("user_case_constraints")
    if not isinstance(constraints, list):
        return True
    for raw_constraint in constraints:
        if not isinstance(raw_constraint, Mapping):
            continue
        if raw_constraint.get("status") != "LOCKED":
            continue
        field = raw_constraint.get("field")
        if not isinstance(field, str) or selection.get(field) != raw_constraint.get("value"):
            return False
    return True


def channel_episode_overrides(channel: Mapping[str, object]) -> set[str]:
    """Channel이 명시한 예외 구조 ID만 반환한다."""
    capabilities = channel.get("capabilities")
    policy = (
        capabilities.get("STORY_VARIATION_POLICY")
        if isinstance(capabilities, Mapping)
        else None
    )
    values = policy.get("episode_overrides") if isinstance(policy, Mapping) else None
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}


def profile_matches_selection(
    selection: Mapping[str, object],
    profile: Mapping[str, object],
) -> bool:
    """정책 Profile이 명시 Dimension을 그대로 보존하는지 판정한다."""
    return all(
        isinstance(selection.get(field), str)
        and profile.get(field) == selection.get(field)
        for field in PROFILE_SELECTION_FIELDS
    )


def technical_final_proof_absent(profile: Mapping[str, object]) -> bool:
    """단일 기술 기록이 최종 진실을 확정하는 Candidate를 차단한다."""
    final_proof = profile.get("final_proof_mechanism")
    reveal_mode = profile.get("reveal_mode")
    return (
        profile.get("technical_dependency_level") != "FINAL_PROOF"
        and final_proof not in TECHNICAL_FINAL_PROOF_VALUES
        and reveal_mode not in TECHNICAL_REVEAL_VALUES
    )


def numeric_suffix(value: object, prefix: str) -> int | None:
    """고정 Prefix 뒤의 양의 정수를 읽는다."""
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    suffix = value.removeprefix(prefix)
    return int(suffix) if suffix.isdigit() else None


def production_feasibility_passes(profile: Mapping[str, object]) -> bool:
    """기본 방송 제작 범위를 벗어나는 구조를 결정론적으로 차단한다."""
    locations = numeric_suffix(profile.get("location_count"), "LOCATIONS_")
    characters = numeric_suffix(profile.get("major_character_count"), "MAJOR_")
    return (
        locations is not None
        and locations <= 5
        and characters is not None
        and characters <= 7
        and profile.get("special_effect_level") != "HIGH"
        and profile.get("child_actor_use") != "PRIMARY"
        and profile.get("vehicle_scene") != "MOVING"
        and profile.get("graphic_violence") != "GRAPHIC"
        and profile.get("production_complexity") not in {"HIGH", "EXTREME"}
    )


def candidate_checks(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    candidate: Mapping[str, object],
    novelty_results: Mapping[str, str],
) -> tuple[dict[str, str], list[str]]:
    """Candidate의 정책 Profile을 신뢰하지 않고 정책과 직접 비교한다."""
    selection = candidate.get("selection")
    profile = candidate.get("policy_profile")
    if not isinstance(selection, Mapping) or not isinstance(profile, Mapping):
        failed = {
            name: "FAIL"
            for name in (
                "policy_profile",
                "channel_genre",
                "crime_threat",
                "trusted_domain",
                "safe_domain_betrayal",
                "responsible_agent",
                "structure_policy",
                "technical_final_proof",
                "required_theme",
                "locked_constraints",
                "source_truth",
                "production_feasibility",
                "novelty",
            )
        }
        return failed, ["CANDIDATE_POLICY_PROFILE_INVALID"]

    capabilities = channel.get("capabilities")
    genre_policy = (
        capabilities.get("GENRE_POLICY")
        if isinstance(capabilities, Mapping)
        else None
    )
    allowed_genres: set[str] = set()
    if isinstance(genre_policy, Mapping):
        for field in ("allowed_genres", "adjacent_genres"):
            values = genre_policy.get(field)
            if isinstance(values, list):
                allowed_genres.update(str(value) for value in values)
    genre = profile.get("genre")
    channel_genre = not allowed_genres or genre in allowed_genres

    crime_policy = enabled_capability(channel, "CRIME_PSYCHOLOGY_POLICY")
    allowed_threats = crime_policy.get("threat_types") if crime_policy else None
    threat = profile.get("threat_type")
    crime_threat = threat in {"CRIME", "PREDATORY"} and (
        crime_policy is None
        or (
            isinstance(allowed_threats, list)
            and threat in allowed_threats
        )
    )

    overrides = channel_episode_overrides(channel)
    structure_values = {
        profile.get("incident_type"),
        profile.get("culprit_structure"),
        profile.get("responsible_agent_structure"),
        profile.get("primary_twist"),
    }
    structure_policy = all(
        not isinstance(value, str)
        or value not in DEFAULT_REJECTED_STRUCTURES
        or value in overrides
        for value in structure_values
    )

    theme_policy = enabled_capability(channel, "EPISODE_THEME_POLICY")
    allowed_themes = theme_policy.get("allowed_themes") if theme_policy else None
    required_theme = (
        True
        if theme_policy is None or theme_policy.get("require_episode_theme") is not True
        else isinstance(allowed_themes, list)
        and profile.get("episode_theme") in allowed_themes
    )
    source_truth = (
        profile.get("source_truth_classification")
        == require_source_truth_classification(production_config)
    )
    candidate_id = candidate.get("candidate_id")
    checks_bool = {
        "policy_profile": profile_matches_selection(selection, profile),
        "channel_genre": channel_genre,
        "crime_threat": crime_threat,
        "trusted_domain": profile.get("trusted_domain") in TRUSTED_DOMAINS,
        "safe_domain_betrayal": profile.get("safe_domain_betrayal") != "ABSENT",
        "responsible_agent": profile.get("responsible_agent_structure")
        not in {"NO_CULPRIT", "SYSTEMIC_CAUSE"},
        "structure_policy": structure_policy,
        "technical_final_proof": technical_final_proof_absent(profile),
        "required_theme": required_theme,
        "locked_constraints": locked_constraints_pass(production_config, selection),
        "source_truth": source_truth,
        "production_feasibility": production_feasibility_passes(profile),
        "novelty": isinstance(candidate_id, str)
        and novelty_results.get(candidate_id) == "PASS",
    }
    checks = {name: "PASS" if passed else "FAIL" for name, passed in checks_bool.items()}
    reasons = [name.upper() for name, passed in checks_bool.items() if not passed]
    return checks, reasons


def build_candidate_eligibility(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
) -> dict[str, object]:
    """현재 입력에서 결정론적 Candidate 적격성 Artifact를 생성한다."""
    raw_candidates = variations.get("candidates")
    candidates = (
        [item for item in raw_candidates if isinstance(item, Mapping)]
        if isinstance(raw_candidates, list)
        else []
    )
    novelty_results = novelty_result_map(novelty_precheck)
    results: list[dict[str, object]] = []
    eligible_ids: list[str] = []
    for candidate in candidates:
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        checks, reasons = candidate_checks(
            production_config,
            channel,
            candidate,
            novelty_results,
        )
        result = "PASS" if all(value == "PASS" for value in checks.values()) else "FAIL"
        if result == "PASS":
            eligible_ids.append(candidate_id)
        results.append(
            {
                "candidate_id": candidate_id,
                "result": result,
                "checks": checks,
                "reasons": reasons,
            }
        )
    project_id = production_config.get("project_id")
    return {
        "$schema": "../../../STANDARD/schemas/candidate_eligibility.schema.json",
        "schema_family": "candidate-eligibility",
        "schema_version": "1.0.0",
        "project_id": project_id,
        "input_hashes": eligibility_input_hashes(
            production_config,
            channel,
            variations,
            novelty_precheck,
        ),
        "result": "PASS" if eligible_ids else "FAIL",
        "eligible_candidate_ids": eligible_ids,
        "candidate_results": results,
    }


def validate_candidate_eligibility(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
    eligibility: Mapping[str, object],
) -> list[ValidationIssue]:
    """저장된 적격성 Artifact가 Core 재계산 결과와 같은지 검증한다."""
    expected = build_candidate_eligibility(
        production_config,
        channel,
        variations,
        novelty_precheck,
    )
    if dict(eligibility) == expected:
        return []
    return [
        ValidationIssue(
            severity="ERROR",
            code="CANDIDATE_ELIGIBILITY_MISMATCH",
            message="Candidate 적격성 Artifact가 현재 Core 판정과 다릅니다.",
            artifact="08_QA/candidate_eligibility.json",
            context={
                "expected_input_hashes": expected["input_hashes"],
                "actual_input_hashes": eligibility.get("input_hashes"),
            },
        )
    ]

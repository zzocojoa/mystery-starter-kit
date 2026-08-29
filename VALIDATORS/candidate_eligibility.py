"""Core가 소유하는 Variation Candidate 적격성 판정."""

from collections.abc import Mapping

from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.models import ValidationIssue
from VALIDATORS.novelty import variation_precheck_source_hash
from VALIDATORS.source_truth import require_source_truth_classification


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
                "channel_genre",
                "crime_threat",
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
    genre = selection.get("genre", "MYSTERY")
    channel_genre = not allowed_genres or genre in allowed_genres

    crime_policy = enabled_capability(channel, "CRIME_PSYCHOLOGY_POLICY")
    allowed_threats = crime_policy.get("threat_types") if crime_policy else None
    crime_threat = (
        True
        if crime_policy is None
        else isinstance(allowed_threats, list)
        and profile.get("threat_type") in allowed_threats
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
    feasibility = profile.get("technical_dependency_level") != "FINAL_PROOF"
    candidate_id = candidate.get("candidate_id")
    checks_bool = {
        "channel_genre": channel_genre,
        "crime_threat": crime_threat,
        "required_theme": required_theme,
        "locked_constraints": locked_constraints_pass(production_config, selection),
        "source_truth": source_truth,
        "production_feasibility": feasibility,
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

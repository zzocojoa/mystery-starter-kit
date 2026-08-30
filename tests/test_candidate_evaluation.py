"""Candidate 적격성, Soft 평가와 Runtime 승인 경계 검증."""

from copy import deepcopy
from pathlib import Path

import pytest

from RUNTIME.models import RuntimeApproval
from RUNTIME.providers.fake import fake_candidate_evaluation
from VALIDATORS.candidate_approval import build_candidate_approval, validate_candidate_approval
from VALIDATORS.candidate_eligibility import (
    build_candidate_eligibility,
    validate_candidate_eligibility,
)
from VALIDATORS.candidate_evaluation import validate_candidate_evaluation
from VALIDATORS.io import load_json_object
from VALIDATORS.novelty import evaluate_variation_precheck
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation import approve_variation_candidate, generate_variation_candidates

ROOT = Path(__file__).resolve().parents[1]


def candidate_inputs() -> tuple[dict[str, object], ...]:
    """후보부터 승인 직전까지의 결정론적 입력을 만든다."""
    config: dict[str, object] = {
        "project_id": "PRJ-910",
        "story_source_mode": "ORIGINAL",
        "source_truth_classification": "ORIGINAL_FICTION",
        "channel_content_version": "1.1.0",
    }
    channel = load_json_object(ROOT / "CHANNELS/mystery_main/channel_dna.json")
    variations = generate_variation_candidates(
        "PRJ-910", "candidate-evaluation", 5,
        load_json_object(ROOT / "STANDARD/variation_catalog.json"),
        "ORIGINAL_FICTION",
    )
    precheck = evaluate_variation_precheck(
        variations, [], load_json_object(ROOT / "STANDARD/novelty_thresholds.json")
    )
    eligibility = build_candidate_eligibility(config, channel, variations, precheck)
    evaluation = fake_candidate_evaluation(
        "PRJ-910", variations, precheck, eligibility
    )
    return config, channel, variations, precheck, eligibility, evaluation


def test_candidate_documents_pass_schema_and_semantics() -> None:
    """Core 적격성과 Soft 평가가 각 소유권 경계를 지키면 통과한다."""
    config, channel, variations, precheck, eligibility, evaluation = candidate_inputs()
    assert collect_schema_errors(
        eligibility,
        load_json_object(ROOT / "STANDARD/schemas/candidate_eligibility.schema.json"),
        "candidate_eligibility",
    ) == []
    assert collect_schema_errors(
        evaluation,
        load_json_object(ROOT / "STANDARD/schemas/candidate_evaluation.schema.json"),
        "candidate_evaluation",
    ) == []
    assert validate_candidate_eligibility(
        config, channel, variations, precheck, eligibility
    ) == []
    assert validate_candidate_evaluation(
        variations, evaluation, precheck, eligibility
    ) == []


def test_soft_evaluation_cannot_declare_authority_fields() -> None:
    """LLM 평가에는 Hard Filter, Novelty 결과나 Human Override를 둘 수 없다."""
    _config, _channel, _variations, _precheck, _eligibility, original = candidate_inputs()
    for field in ("hard_filter_result", "novelty_result", "human_override"):
        evaluation = deepcopy(original)
        evaluation[field] = "PASS"
        assert collect_schema_errors(
            evaluation,
            load_json_object(ROOT / "STANDARD/schemas/candidate_evaluation.schema.json"),
            "candidate_evaluation",
        )


def test_tampered_eligibility_fails_core_recalculation() -> None:
    """LLM이 적격 Candidate를 바꾸어도 Core 재계산에서 실패한다."""
    config, channel, variations, precheck, original, _evaluation = candidate_inputs()
    eligibility = deepcopy(original)
    eligibility["eligible_candidate_ids"] = []
    assert validate_candidate_eligibility(
        config, channel, variations, precheck, eligibility
    )[0]["code"] == "CANDIDATE_ELIGIBILITY_MISMATCH"


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("trusted_domain", "APARTMENT_COMPLEX", "TRUSTED_DOMAIN"),
        ("culprit_structure", "NO_CULPRIT", "STRUCTURE_POLICY"),
        ("culprit_structure", "VICTIM_SELF_ENGINEERED", "STRUCTURE_POLICY"),
        ("primary_twist", "SELF_CREATED_TRAP", "STRUCTURE_POLICY"),
        ("final_proof_mechanism", "SINGLE_TECHNICAL_RECORD", "TECHNICAL_FINAL_PROOF"),
        ("location_count", "LOCATIONS_8", "PRODUCTION_FEASIBILITY"),
    ],
)
def test_explicit_candidate_policy_dimensions_fail_closed(
    field: str,
    value: str,
    expected_reason: str,
) -> None:
    """장소 추론, 금지 구조, 기술 단독 증명과 제작 초과를 직접 차단한다."""
    config, channel, variations, precheck, _eligibility, _evaluation = candidate_inputs()
    changed = deepcopy(variations)
    candidates = changed["candidates"]
    assert isinstance(candidates, list)
    candidate = candidates[0]
    assert isinstance(candidate, dict)
    selection = candidate["selection"]
    profile = candidate["policy_profile"]
    assert isinstance(selection, dict)
    assert isinstance(profile, dict)
    selection[field] = value
    profile[field] = value

    eligibility = build_candidate_eligibility(config, channel, changed, precheck)
    results = eligibility["candidate_results"]
    assert isinstance(results, list)
    result = results[0]
    assert isinstance(result, dict)
    reasons = result["reasons"]
    assert isinstance(reasons, list)
    assert result["result"] == "FAIL"
    assert expected_reason in reasons


def test_missing_genre_is_not_inferred_as_mystery() -> None:
    """Genre 누락을 기본 MYSTERY로 보정하지 않고 적격성 실패로 유지한다."""
    config, channel, variations, precheck, _eligibility, _evaluation = candidate_inputs()
    changed = deepcopy(variations)
    candidates = changed["candidates"]
    assert isinstance(candidates, list)
    candidate = candidates[0]
    assert isinstance(candidate, dict)
    selection = candidate["selection"]
    profile = candidate["policy_profile"]
    assert isinstance(selection, dict)
    assert isinstance(profile, dict)
    selection.pop("genre")
    profile.pop("genre")

    eligibility = build_candidate_eligibility(config, channel, changed, precheck)
    results = eligibility["candidate_results"]
    assert isinstance(results, list)
    result = results[0]
    assert isinstance(result, dict)
    assert result["result"] == "FAIL"
    assert "POLICY_PROFILE" in result["reasons"]


def test_approval_is_separate_and_hash_bound() -> None:
    """승인은 별도 Runtime Artifact로 현재 입력 Hash에 결속된다."""
    _config, _channel, variations, precheck, eligibility, evaluation = candidate_inputs()
    selected = evaluation["recommended_candidate_id"]
    assert isinstance(selected, str)
    approved = approve_variation_candidate(variations, selected)
    approval = build_candidate_approval(
        "PRJ-910", selected, selected, "SYSTEM", "자동 승인",
        "2025-01-01T00:00:00Z", approved, precheck, evaluation,
        "AUTO_CONTINUE", None,
    )
    assert validate_candidate_approval(
        approved, precheck, eligibility, evaluation, approval
    ) == []
    changed = deepcopy(evaluation)
    changed["recommended_candidate_id"] = "VAR-99"
    assert validate_candidate_approval(
        approved, precheck, eligibility, changed, approval
    )


def test_human_override_preserves_runtime_approval_provenance() -> None:
    """비추천 적격 후보 승인에는 Human Override와 실제 승인 출처를 보존한다."""
    _config, _channel, variations, precheck, eligibility, evaluation = candidate_inputs()
    recommended = evaluation["recommended_candidate_id"]
    eligible = eligibility["eligible_candidate_ids"]
    assert isinstance(recommended, str)
    assert isinstance(eligible, list)
    selected = next(
        candidate_id
        for candidate_id in eligible
        if isinstance(candidate_id, str) and candidate_id != recommended
    )
    approved = approve_variation_candidate(variations, selected)
    runtime_approval = RuntimeApproval(
        schema_family="runtime-approval",
        schema_version="1.0.0",
        approval_id="APR-ABCDEF123456",
        run_id="RUN-TEST-OVERRIDE",
        task_id="variation.approve",
        decision="APPROVED",
        actor="human-reviewer",
        reason="추천 외 적격 후보의 구조적 장점을 검토함",
        bound_input_hashes={"variation_candidates": "a" * 64},
        created_at="2026-08-30T01:00:00Z",
    )
    approval = build_candidate_approval(
        "PRJ-910",
        selected,
        recommended,
        runtime_approval["actor"],
        runtime_approval["reason"],
        runtime_approval["created_at"],
        approved,
        precheck,
        evaluation,
        "HUMAN_REVIEW",
        runtime_approval,
    )

    assert approval["approval_type"] == "HUMAN_OVERRIDE"
    assert approval["approval_id"] == "APR-ABCDEF123456"
    assert approval["actor"] == "human-reviewer"
    assert approval["reason"] == "추천 외 적격 후보의 구조적 장점을 검토함"
    assert validate_candidate_approval(
        approved,
        precheck,
        eligibility,
        evaluation,
        approval,
    ) == []

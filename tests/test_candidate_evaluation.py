"""Candidate 평가 Artifact의 Schema와 승인 정합성 검증."""

from copy import deepcopy
from pathlib import Path

from RUNTIME.providers.fake import fake_candidate_evaluation
from VALIDATORS.candidate_evaluation import validate_candidate_evaluation
from VALIDATORS.io import load_json_object
from VALIDATORS.novelty import evaluate_variation_precheck
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation import (
    approve_variation_candidate,
    generate_variation_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


def evaluation_inputs() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    """승인 전 Variation, 전체 Novelty Precheck, 평가를 순서대로 만든다."""
    variations = generate_variation_candidates(
        "PRJ-910",
        "candidate-evaluation",
        5,
        load_json_object(ROOT / "STANDARD" / "variation_catalog.json"),
    )
    precheck = evaluate_variation_precheck(
        variations,
        [],
        load_json_object(ROOT / "STANDARD" / "novelty_thresholds.json"),
    )
    evaluation = fake_candidate_evaluation("PRJ-910", variations, precheck)
    return variations, precheck, evaluation


def approved_recommendation(
    variations: dict[str, object],
    evaluation: dict[str, object],
) -> dict[str, object]:
    """평가가 추천한 Candidate를 승인한다."""
    candidate_id = evaluation["recommended_candidate_id"]
    assert isinstance(candidate_id, str)
    return approve_variation_candidate(variations, candidate_id)


def issue_codes(
    variations: dict[str, object],
    evaluation: dict[str, object],
    precheck: dict[str, object],
) -> set[str]:
    """Candidate 평가 Issue Code 집합을 반환한다."""
    return {
        issue["code"]
        for issue in validate_candidate_evaluation(
            variations,
            evaluation,
            precheck,
        )
    }


def test_candidate_evaluation_passes_schema_and_semantics() -> None:
    """전체 후보 평가 후 최고점 추천 후보를 승인하면 통과한다."""
    variations, precheck, evaluation = evaluation_inputs()
    approved = approved_recommendation(variations, evaluation)
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "candidate_evaluation.schema.json"
    )

    assert collect_schema_errors(evaluation, schema, "candidate_evaluation") == []
    assert validate_candidate_evaluation(approved, evaluation, precheck) == []


def test_candidate_evaluation_rejects_missing_candidate_reason() -> None:
    """후보 하나의 평가가 빠지면 평가 근거가 불완전해야 한다."""
    variations, precheck, original = evaluation_inputs()
    evaluation = deepcopy(original)
    records = evaluation["evaluations"]
    assert isinstance(records, list)
    records.pop()

    assert "CANDIDATE_EVALUATION_INCOMPLETE" in issue_codes(
        variations,
        evaluation,
        precheck,
    )


def test_wrong_weighted_total_fails() -> None:
    """선언된 종합 점수가 재계산값과 다르면 실패한다."""
    variations, precheck, original = evaluation_inputs()
    evaluation = deepcopy(original)
    records = evaluation["evaluations"]
    assert isinstance(records, list)
    selected = records[0]
    assert isinstance(selected, dict)
    selected["total_score"] = 0

    assert "CANDIDATE_WEIGHTED_TOTAL_MISMATCH" in issue_codes(
        variations,
        evaluation,
        precheck,
    )


def test_hard_filter_failure_cannot_be_approved() -> None:
    """Hard Filter FAIL 후보는 점수와 관계없이 승인할 수 없다."""
    variations, precheck, original = evaluation_inputs()
    evaluation = deepcopy(original)
    records = evaluation["evaluations"]
    assert isinstance(records, list)
    selected = records[0]
    assert isinstance(selected, dict)
    selected["hard_filter_result"] = "FAIL"
    approved = approve_variation_candidate(variations, "VAR-01")

    assert {
        "CANDIDATE_HARD_FILTER_FAILED",
        "CANDIDATE_APPROVAL_INELIGIBLE",
    } & issue_codes(approved, evaluation, precheck)


def test_novelty_failure_candidate_cannot_be_approved() -> None:
    """Novelty FAIL 후보는 Human Override로도 승인할 수 없다."""
    variations, precheck, _evaluation = evaluation_inputs()
    results = precheck["candidate_results"]
    assert isinstance(results, list)
    first = results[0]
    assert isinstance(first, dict)
    first["result"] = "FAIL"
    evaluation = fake_candidate_evaluation("PRJ-910", variations, precheck)
    approved = approve_variation_candidate(variations, "VAR-01")

    assert "CANDIDATE_APPROVAL_INELIGIBLE" in issue_codes(
        approved,
        evaluation,
        precheck,
    )

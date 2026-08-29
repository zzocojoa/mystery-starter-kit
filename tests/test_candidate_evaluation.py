"""Candidate 평가 Artifact의 Schema와 승인 정합성 검증."""

from copy import deepcopy
from pathlib import Path

from RUNTIME.providers.fake import fake_candidate_evaluation
from VALIDATORS.candidate_evaluation import validate_candidate_evaluation
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation import (
    approve_variation_candidate,
    generate_variation_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


def approved_variations() -> dict[str, object]:
    """평가 테스트용 승인 Variation 다섯 개를 만든다."""
    generated = generate_variation_candidates(
        "PRJ-910",
        "candidate-evaluation",
        5,
        load_json_object(ROOT / "STANDARD" / "variation_catalog.json"),
    )
    return approve_variation_candidate(generated, "VAR-01")


def test_candidate_evaluation_passes_schema_and_semantics() -> None:
    """모든 후보의 점수와 근거가 있으면 GATE-01 평가가 통과해야 한다."""
    variations = approved_variations()
    evaluation = fake_candidate_evaluation("PRJ-910", variations)
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "candidate_evaluation.schema.json"
    )

    assert collect_schema_errors(evaluation, schema, "candidate_evaluation") == []
    assert validate_candidate_evaluation(variations, evaluation) == []


def test_candidate_evaluation_rejects_missing_candidate_reason() -> None:
    """후보 하나의 평가가 빠지면 평가 근거가 불완전해야 한다."""
    variations = approved_variations()
    evaluation = deepcopy(fake_candidate_evaluation("PRJ-910", variations))
    records = evaluation["evaluations"]
    assert isinstance(records, list)
    records.pop()

    assert {
        issue["code"] for issue in validate_candidate_evaluation(variations, evaluation)
    } == {"CANDIDATE_EVALUATION_INCOMPLETE"}


def test_hard_filter_failure_cannot_be_approved() -> None:
    """Hard Filter FAIL 후보는 높은 점수와 관계없이 승인할 수 없다."""
    variations = approved_variations()
    evaluation = fake_candidate_evaluation("PRJ-910", variations)
    records = evaluation["evaluations"]
    assert isinstance(records, list)
    selected = records[0]
    assert isinstance(selected, dict)
    selected["hard_filter_result"] = "FAIL"

    assert {
        issue["code"] for issue in validate_candidate_evaluation(variations, evaluation)
    } == {"CANDIDATE_HARD_FILTER_FAILED"}

"""Candidate 적격성, Soft 평가와 Runtime 승인 경계 검증."""

from copy import deepcopy
from pathlib import Path

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


def test_approval_is_separate_and_hash_bound() -> None:
    """승인은 별도 Runtime Artifact로 현재 입력 Hash에 결속된다."""
    _config, _channel, variations, precheck, eligibility, evaluation = candidate_inputs()
    selected = evaluation["recommended_candidate_id"]
    assert isinstance(selected, str)
    approved = approve_variation_candidate(variations, selected)
    approval = build_candidate_approval(
        "PRJ-910", selected, selected, "SYSTEM", "자동 승인",
        "2025-01-01T00:00:00Z", approved, precheck, evaluation,
    )
    assert validate_candidate_approval(
        approved, precheck, eligibility, evaluation, approval
    ) == []
    changed = deepcopy(evaluation)
    changed["recommended_candidate_id"] = "VAR-99"
    assert validate_candidate_approval(
        approved, precheck, eligibility, changed, approval
    )

"""Variation Candidate 평가 근거와 승인 결과의 의미 검증."""

import hashlib
import json
from collections.abc import Mapping

from VALIDATORS.models import ValidationIssue
from VALIDATORS.novelty import variation_precheck_source_hash

SCORE_FIELDS: tuple[str, ...] = (
    "crime_threat_score",
    "psychological_immersion_score",
    "trust_betrayal_score",
    "victim_integrity_score",
    "character_score",
    "twist_score",
    "novelty_score",
    "production_score",
)
SCORE_TOLERANCE = 0.01


def make_candidate_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Candidate 평가 문제를 표준 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="00_PROJECT/candidate_evaluation.json",
        context=context,
    )


def document_sha256(document: Mapping[str, object]) -> str:
    """JSON 객체의 정규 표현에 대한 SHA-256을 계산한다."""
    encoded = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_evaluation_input_hashes(
    variations: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
) -> dict[str, str]:
    """승인 상태와 무관한 평가 입력 Hash를 계산한다."""
    return {
        "variation_candidates": variation_precheck_source_hash(variations),
        "novelty_precheck": document_sha256(novelty_precheck),
    }


def candidate_ids(document: Mapping[str, object]) -> set[str]:
    """Variation 문서에서 Candidate ID 집합을 읽는다."""
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        return set()
    return {
        candidate_id
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and isinstance((candidate_id := candidate.get("candidate_id")), str)
    }


def evaluation_records(
    document: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Candidate Evaluation 객체 배열을 읽는다."""
    evaluations = document.get("evaluations")
    if not isinstance(evaluations, list):
        return []
    return [item for item in evaluations if isinstance(item, Mapping)]


def number_value(value: object) -> float | None:
    """Boolean을 제외한 숫자를 부동소수점으로 정규화한다."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value)


def novelty_results(
    novelty_precheck: Mapping[str, object],
) -> dict[str, str]:
    """Novelty Precheck의 Candidate별 결과를 색인한다."""
    raw_results = novelty_precheck.get("candidate_results")
    if not isinstance(raw_results, list):
        return {}
    results: dict[str, str] = {}
    for raw_result in raw_results:
        if not isinstance(raw_result, Mapping):
            continue
        candidate_id = raw_result.get("candidate_id")
        result = raw_result.get("result")
        if isinstance(candidate_id, str) and isinstance(result, str):
            results[candidate_id] = result
    return results


def validate_evaluation_completeness(
    variations: Mapping[str, object],
    records: list[Mapping[str, object]],
) -> list[ValidationIssue]:
    """후보 전체가 정확히 한 번 평가되었는지 검증한다."""
    expected_ids = candidate_ids(variations)
    record_ids = [
        candidate_id
        for record in records
        if isinstance((candidate_id := record.get("candidate_id")), str)
    ]
    if set(record_ids) == expected_ids and len(record_ids) == len(expected_ids):
        return []
    return [
        make_candidate_issue(
            "CANDIDATE_EVALUATION_INCOMPLETE",
            "Variation 후보 전체에 대한 중복 없는 평가 근거가 필요합니다.",
            {
                "expected_candidate_ids": sorted(expected_ids),
                "evaluated_candidate_ids": sorted(record_ids),
                "evaluation_count": len(records),
            },
        )
    ]


def validate_weighted_scores(
    evaluation: Mapping[str, object],
    records: list[Mapping[str, object]],
) -> list[ValidationIssue]:
    """가중치 합계, Dimension 근거, 재계산 종합 점수를 검증한다."""
    weights = evaluation.get("weights")
    if not isinstance(weights, Mapping):
        return [
            make_candidate_issue(
                "CANDIDATE_WEIGHTS_INVALID",
                "Candidate 평가 가중치 객체가 필요합니다.",
                {},
            )
        ]
    normalized_weights: dict[str, float] = {}
    for field in SCORE_FIELDS:
        value = number_value(weights.get(field))
        if value is None:
            return [
                make_candidate_issue(
                    "CANDIDATE_WEIGHTS_INVALID",
                    "모든 Candidate 평가 Dimension에 숫자 가중치가 필요합니다.",
                    {"fields": list(SCORE_FIELDS)},
                )
            ]
        normalized_weights[field] = value
    total_weight = sum(normalized_weights.values())
    issues: list[ValidationIssue] = []
    if abs(total_weight - 100.0) > SCORE_TOLERANCE:
        issues.append(
            make_candidate_issue(
                "CANDIDATE_WEIGHT_SUM_INVALID",
                "Candidate 평가 가중치 합계는 100이어야 합니다.",
                {"weight_sum": round(total_weight, 4)},
            )
        )
    for record in records:
        candidate_id = record.get("candidate_id")
        evidence = record.get("dimension_evidence")
        missing_evidence = [
            field
            for field in SCORE_FIELDS
            if not isinstance(evidence, Mapping)
            or not isinstance(evidence.get(field), list)
            or not evidence.get(field)
        ]
        if missing_evidence:
            issues.append(
                make_candidate_issue(
                    "CANDIDATE_DIMENSION_EVIDENCE_MISSING",
                    "각 평가 점수에는 하나 이상의 구체적 근거가 필요합니다.",
                    {
                        "candidate_id": candidate_id,
                        "fields": missing_evidence,
                    },
                )
            )
        normalized_scores: dict[str, float] = {}
        for field in SCORE_FIELDS:
            score = number_value(record.get(field))
            if score is not None:
                normalized_scores[field] = score
        if len(normalized_scores) != len(SCORE_FIELDS):
            continue
        recomputed = round(
            sum(
                normalized_scores[field] * normalized_weights[field] / 100.0
                for field in SCORE_FIELDS
            ),
            2,
        )
        declared = number_value(record.get("total_score"))
        if declared is None or abs(declared - recomputed) > SCORE_TOLERANCE:
            issues.append(
                make_candidate_issue(
                    "CANDIDATE_WEIGHTED_TOTAL_MISMATCH",
                    "종합 점수가 선언된 가중치로 재계산한 값과 다릅니다.",
                    {
                        "candidate_id": candidate_id,
                        "declared_total": declared,
                        "recomputed_total": recomputed,
                    },
                )
            )
    return issues


def validate_hashes_and_novelty(
    variations: Mapping[str, object],
    evaluation: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
    records: list[Mapping[str, object]],
) -> list[ValidationIssue]:
    """평가 입력 Hash와 Candidate별 Novelty 결과를 검증한다."""
    expected_hashes = candidate_evaluation_input_hashes(
        variations,
        novelty_precheck,
    )
    actual_hashes = evaluation.get("input_hashes")
    issues: list[ValidationIssue] = []
    if not isinstance(actual_hashes, Mapping) or any(
        actual_hashes.get(name) != expected
        for name, expected in expected_hashes.items()
    ):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_EVALUATION_STALE",
                "Candidate 평가가 현재 Variation과 Novelty Precheck에서 생성되지 않았습니다.",
                {
                    "expected_input_hashes": expected_hashes,
                    "actual_input_hashes": (
                        dict(actual_hashes) if isinstance(actual_hashes, Mapping) else {}
                    ),
                },
            )
        )
    if evaluation.get("novelty_report_hash") != expected_hashes["novelty_precheck"]:
        issues.append(
            make_candidate_issue(
                "CANDIDATE_NOVELTY_REPORT_HASH_MISMATCH",
                "Candidate 평가의 Novelty Report Hash가 현재 보고서와 다릅니다.",
                {
                    "expected": expected_hashes["novelty_precheck"],
                    "actual": evaluation.get("novelty_report_hash"),
                },
            )
        )
    precheck_results = novelty_results(novelty_precheck)
    for record in records:
        candidate_id = record.get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        declared = record.get("novelty_result")
        actual = precheck_results.get(candidate_id)
        if declared != actual:
            issues.append(
                make_candidate_issue(
                    "CANDIDATE_NOVELTY_RESULT_MISMATCH",
                    "Candidate 평가의 Novelty 결과가 Precheck와 다릅니다.",
                    {
                        "candidate_id": candidate_id,
                        "declared": declared,
                        "actual": actual,
                    },
                )
            )
    return issues


def eligible_record(record: Mapping[str, object]) -> bool:
    """Hard Filter와 Novelty를 모두 통과한 평가인지 판정한다."""
    return (
        record.get("hard_filter_result") == "PASS"
        and record.get("novelty_result") == "PASS"
        and number_value(record.get("total_score")) is not None
    )


def validate_recommendation(
    variations: Mapping[str, object],
    evaluation: Mapping[str, object],
    records: list[Mapping[str, object]],
) -> list[ValidationIssue]:
    """추천 후보가 적격 최고점이며 승인 후보와 일치하는지 검증한다."""
    recommended_id = evaluation.get("recommended_candidate_id")
    recommended_records = [
        record for record in records if record.get("decision") == "RECOMMENDED"
    ]
    issues: list[ValidationIssue] = []
    if (
        not isinstance(recommended_id, str)
        or len(recommended_records) != 1
        or recommended_records[0].get("candidate_id") != recommended_id
    ):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_RECOMMENDATION_MISMATCH",
                "정확히 한 평가가 top-level 추천 Candidate와 일치해야 합니다.",
                {
                    "recommended_candidate_id": recommended_id,
                    "recommended_record_count": len(recommended_records),
                },
            )
        )
        return issues
    selected_record = recommended_records[0]
    if selected_record.get("hard_filter_result") != "PASS":
        issues.append(
            make_candidate_issue(
                "CANDIDATE_HARD_FILTER_FAILED",
                "Hard Filter를 통과하지 못한 후보를 추천하거나 승인할 수 없습니다.",
                {"candidate_id": recommended_id},
            )
        )
    if selected_record.get("novelty_result") != "PASS":
        issues.append(
            make_candidate_issue(
                "CANDIDATE_NOVELTY_FAILED",
                "Novelty Precheck를 통과하지 못한 후보를 추천하거나 승인할 수 없습니다.",
                {"candidate_id": recommended_id},
            )
        )
    eligible = [record for record in records if eligible_record(record)]
    highest_score = max(
        (number_value(record.get("total_score")) or 0.0 for record in eligible),
        default=-1.0,
    )
    selected_score = number_value(selected_record.get("total_score"))
    if (
        selected_score is None
        or highest_score < 0
        or selected_score + SCORE_TOLERANCE < highest_score
    ):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_NOT_HIGHEST_WEIGHTED_SCORE",
                "Hard Filter와 Novelty를 통과한 후보 중 최고 가중 점수를 추천해야 합니다.",
                {
                    "candidate_id": recommended_id,
                    "selected_score": selected_score,
                    "highest_score": highest_score,
                },
            )
        )
    approved_id = variations.get("approved_candidate_id")
    if not isinstance(approved_id, str):
        return issues
    approved_record = next(
        (record for record in records if record.get("candidate_id") == approved_id),
        None,
    )
    if approved_record is None or not eligible_record(approved_record):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_APPROVAL_INELIGIBLE",
                "승인 후보는 Hard Filter와 Novelty를 모두 통과해야 합니다.",
                {"candidate_id": approved_id},
            )
        )
    if (
        approved_record is not None
        and approved_record.get("hard_filter_result") != "PASS"
    ):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_HARD_FILTER_FAILED",
                "Hard Filter를 통과하지 못한 후보를 승인할 수 없습니다.",
                {"candidate_id": approved_id},
            )
        )
    if approved_record is not None and approved_record.get("novelty_result") != "PASS":
        issues.append(
            make_candidate_issue(
                "CANDIDATE_NOVELTY_FAILED",
                "Novelty Precheck를 통과하지 못한 후보를 승인할 수 없습니다.",
                {"candidate_id": approved_id},
            )
        )
    if approved_id == recommended_id:
        return issues
    override = evaluation.get("human_override")
    if (
        not isinstance(override, Mapping)
        or override.get("candidate_id") != approved_id
        or not isinstance(override.get("actor"), str)
        or not override.get("actor")
        or not isinstance(override.get("reason"), str)
        or not override.get("reason")
    ):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_HUMAN_OVERRIDE_REQUIRED",
                "추천 후보가 아닌 후보의 승인에는 Hash에 포함된 Human Override가 필요합니다.",
                {
                    "approved_candidate_id": approved_id,
                    "recommended_candidate_id": recommended_id,
                },
            )
        )
    return issues


def validate_candidate_evaluation(
    variations: Mapping[str, object],
    evaluation: Mapping[str, object],
    novelty_precheck: Mapping[str, object],
) -> list[ValidationIssue]:
    """Candidate 평가의 완전성, 근거, 신규성, 승인 정합성을 검증한다."""
    records = evaluation_records(evaluation)
    return [
        *validate_evaluation_completeness(variations, records),
        *validate_weighted_scores(evaluation, records),
        *validate_hashes_and_novelty(
            variations,
            evaluation,
            novelty_precheck,
            records,
        ),
        *validate_recommendation(variations, evaluation, records),
    ]

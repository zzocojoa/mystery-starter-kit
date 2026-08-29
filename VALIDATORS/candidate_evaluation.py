"""Variation Candidate 평가 근거와 승인 결과의 의미 검증."""

from collections.abc import Mapping

from VALIDATORS.models import ValidationIssue


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


def validate_candidate_evaluation(
    variations: Mapping[str, object],
    evaluation: Mapping[str, object],
) -> list[ValidationIssue]:
    """모든 후보의 평가, Hard Filter, 최종 승인 정합성을 검증한다."""
    expected_ids = candidate_ids(variations)
    records = evaluation_records(evaluation)
    evaluated_ids = {
        candidate_id
        for record in records
        if isinstance((candidate_id := record.get("candidate_id")), str)
    }
    issues: list[ValidationIssue] = []
    if evaluated_ids != expected_ids or len(records) != len(expected_ids):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_EVALUATION_INCOMPLETE",
                "Variation 후보 전체에 대한 평가 근거가 필요합니다.",
                {
                    "expected_candidate_ids": sorted(expected_ids),
                    "evaluated_candidate_ids": sorted(evaluated_ids),
                    "evaluation_count": len(records),
                },
            )
        )

    approved_records = [
        record for record in records if record.get("decision") == "APPROVED"
    ]
    selected_id = evaluation.get("selected_candidate_id")
    approved_id = variations.get("approved_candidate_id")
    if (
        len(approved_records) != 1
        or approved_records[0].get("candidate_id") != selected_id
        or selected_id != approved_id
    ):
        issues.append(
            make_candidate_issue(
                "CANDIDATE_EVALUATION_SELECTION_MISMATCH",
                "평가 승인 후보와 Variation 승인 후보가 정확히 일치해야 합니다.",
                {
                    "selected_candidate_id": selected_id,
                    "approved_candidate_id": approved_id,
                    "approved_evaluation_count": len(approved_records),
                },
            )
        )
    elif approved_records[0].get("hard_filter_result") != "PASS":
        issues.append(
            make_candidate_issue(
                "CANDIDATE_HARD_FILTER_FAILED",
                "Hard Filter를 통과하지 못한 후보를 승인할 수 없습니다.",
                {"candidate_id": selected_id},
            )
        )
    else:
        selected_score = approved_records[0].get("total_score")
        eligible_scores = [
            score
            for record in records
            if record.get("hard_filter_result") == "PASS"
            and isinstance((score := record.get("total_score")), int | float)
            and not isinstance(score, bool)
        ]
        if (
            isinstance(selected_score, int | float)
            and not isinstance(selected_score, bool)
            and eligible_scores
            and float(selected_score) < max(float(score) for score in eligible_scores)
        ):
            issues.append(
                make_candidate_issue(
                    "CANDIDATE_EVALUATION_SELECTION_MISMATCH",
                    "Hard Filter PASS 후보 중 최고 종합 점수 후보를 승인해야 합니다.",
                    {
                        "candidate_id": selected_id,
                        "selected_score": selected_score,
                        "highest_score": max(float(score) for score in eligible_scores),
                    },
                )
            )
    return issues

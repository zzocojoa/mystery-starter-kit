"""Story 입력 경로와 Audience 사실성 분류의 독립 계약 검증."""

from VALIDATORS.source_truth import source_truth_configuration_issues


def issue_codes(config: dict[str, object]) -> set[str]:
    """Source Truth 구성 Issue Code를 반환한다."""
    return {issue["code"] for issue in source_truth_configuration_issues(config)}


def test_fixed_source_modes_require_exact_truth_classification() -> None:
    """고정 Source Mode는 정확한 Audience 사실성 분류만 허용한다."""
    assert issue_codes(
        {
            "story_source_mode": "ORIGINAL",
            "source_truth_classification": "ORIGINAL_FICTION",
        }
    ) == set()
    assert "SOURCE_TRUTH_CLASSIFICATION_MISMATCH" in issue_codes(
        {
            "story_source_mode": "TRUE_STORY",
            "source_truth_classification": "ORIGINAL_FICTION",
        }
    )


def test_user_and_reference_routes_require_explicit_truth_without_inference() -> None:
    """USER_CASE와 REFERENCE_INSPIRED는 명시값을 받되 자동 추론하지 않는다."""
    for source_mode in ("USER_CASE", "REFERENCE_INSPIRED"):
        assert "SOURCE_TRUTH_CLASSIFICATION_MISSING" in issue_codes(
            {"story_source_mode": source_mode}
        )
        assert issue_codes(
            {
                "story_source_mode": source_mode,
                "source_truth_classification": "INSPIRED_BY_TRUE_EVENTS",
            }
        ) == set()

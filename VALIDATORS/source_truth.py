"""Story 입력 경로와 Audience 사실성 분류의 독립 계약."""

from collections.abc import Mapping

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

SOURCE_TRUTH_CLASSIFICATIONS = frozenset(
    {
        "ORIGINAL_FICTION",
        "VERIFIED_TRUE_CASE",
        "INSPIRED_BY_TRUE_EVENTS",
    }
)
FIXED_SOURCE_TRUTH_BY_MODE: Mapping[str, str] = {
    "ORIGINAL": "ORIGINAL_FICTION",
    "TRUE_STORY": "VERIFIED_TRUE_CASE",
    "INSPIRED_BY_TRUE_EVENTS": "INSPIRED_BY_TRUE_EVENTS",
}
FACT_BASED_SOURCE_TRUTHS = frozenset(
    {"VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"}
)


def make_source_truth_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Source Truth 구성 문제를 표준 Issue로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="00_PROJECT/production_config.json",
        context=context,
    )


def source_truth_configuration_issues(
    production_config: Mapping[str, object],
) -> list[ValidationIssue]:
    """입력 경로와 명시적 사실성 분류가 독립 계약을 지키는지 검증한다."""
    source_mode = production_config.get("story_source_mode")
    classification = production_config.get("source_truth_classification")
    if classification not in SOURCE_TRUTH_CLASSIFICATIONS:
        return [
            make_source_truth_issue(
                "SOURCE_TRUTH_CLASSIFICATION_MISSING",
                "Production Config에 명시적 Source Truth Classification이 필요합니다.",
                {
                    "story_source_mode": source_mode,
                    "source_truth_classification": classification,
                },
            )
        ]
    expected = FIXED_SOURCE_TRUTH_BY_MODE.get(str(source_mode))
    if expected is not None and classification != expected:
        return [
            make_source_truth_issue(
                "SOURCE_TRUTH_CLASSIFICATION_MISMATCH",
                "Story Source Mode와 고정 사실성 분류가 일치하지 않습니다.",
                {
                    "story_source_mode": source_mode,
                    "expected": expected,
                    "actual": classification,
                },
            )
        ]
    return []


def require_source_truth_classification(
    production_config: Mapping[str, object],
) -> str:
    """검증된 Source Truth Classification을 반환하거나 구성 오류를 발생시킨다."""
    issues = source_truth_configuration_issues(production_config)
    if issues:
        issue = issues[0]
        raise ConfigurationError(
            f"{issue['code']}: {issue['message']} context={issue['context']}"
        )
    classification = production_config.get("source_truth_classification")
    if not isinstance(classification, str):
        raise ConfigurationError(
            "SOURCE_TRUTH_CLASSIFICATION_MISSING: 문자열 분류가 필요합니다."
        )
    return classification


def source_truth_requires_evidence(classification: object) -> bool:
    """검증 Source와 Claim-Evidence가 필요한 사실성 분류인지 판정한다."""
    return classification in FACT_BASED_SOURCE_TRUTHS

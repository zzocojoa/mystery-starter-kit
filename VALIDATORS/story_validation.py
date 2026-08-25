"""Story DNA v1.3 의미 규칙과 Reference Firewall 검증."""

from collections.abc import Mapping

from VALIDATORS.models import ValidationIssue

CAUSAL_STRUCTURES = {"NO_CULPRIT", "SYSTEMIC_CAUSE", "ACCIDENTAL"}
USER_CASE_STATUSES = {"LOCKED", "FLEXIBLE", "UNKNOWN"}


def make_story_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Story DNA 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="00_PROJECT/story_dna.json",
        context=context,
    )


def make_reference_profile_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """별도 Reference Profile 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="00_PROJECT/reference_profile.json",
        context=context,
    )


def make_production_config_issue(
    code: str,
    message: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Production Config의 USER_CASE 계약 문제를 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact="00_PROJECT/production_config.json",
        context=context,
    )


def string_set(value: object) -> set[str]:
    """문자열 배열을 집합으로 변환하고 다른 형식은 빈 집합으로 처리한다."""
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def story_constraint_value(story_dna: Mapping[str, object], field: str) -> object:
    """USER_CASE Constraint가 비교하는 Story DNA 값을 읽는다."""
    value = story_dna.get(field)
    if not isinstance(value, Mapping):
        return value
    if field == "pressure_engine":
        return value.get("source")
    return value.get("primary")


def validate_user_case_constraints(
    production_config: Mapping[str, object],
    story_document: Mapping[str, object],
) -> list[ValidationIssue]:
    """USER_CASE 입력 상태와 LOCKED Story Dimension을 검증한다."""
    source_mode = production_config.get("story_source_mode")
    constraints = production_config.get("user_case_constraints")
    if source_mode != "USER_CASE":
        if constraints is None:
            return []
        return [
            make_production_config_issue(
                "USER_CASE_CONSTRAINTS_NOT_ALLOWED",
                "USER_CASE가 아닌 Project에는 사용자 Case Constraint를 둘 수 없습니다.",
                {"story_source_mode": source_mode},
            )
        ]
    if not isinstance(constraints, list) or not constraints or not all(
        isinstance(constraint, Mapping) for constraint in constraints
    ):
        return [
            make_production_config_issue(
                "USER_CASE_CONSTRAINTS_REQUIRED",
                "USER_CASE에는 하나 이상의 사용자 입력 Constraint가 필요합니다.",
                {},
            )
        ]

    fields = [
        constraint.get("field")
        for constraint in constraints
        if isinstance(constraint.get("field"), str)
    ]
    duplicate_fields = sorted({field for field in fields if fields.count(field) > 1})
    issues: list[ValidationIssue] = []
    if duplicate_fields:
        issues.append(
            make_production_config_issue(
                "USER_CASE_CONSTRAINT_DUPLICATED",
                "USER_CASE Constraint Field는 한 번만 선언해야 합니다.",
                {"fields": duplicate_fields},
            )
        )

    story_dna = story_document.get("story_dna")
    if not isinstance(story_dna, Mapping):
        return issues
    locked_mismatches = sorted(
        field
        for constraint in constraints
        if constraint.get("status") == "LOCKED"
        and isinstance((field := constraint.get("field")), str)
        and story_constraint_value(story_dna, field) != constraint.get("value")
    )
    if locked_mismatches:
        issues.append(
            make_story_issue(
                "USER_CASE_LOCKED_VALUE_CHANGED",
                "LOCKED 사용자 입력은 Story DNA에서 변경할 수 없습니다.",
                {"fields": locked_mismatches},
            )
        )
    invalid_status_fields = sorted(
        field
        for constraint in constraints
        if isinstance((field := constraint.get("field")), str)
        and constraint.get("status") not in USER_CASE_STATUSES
    )
    if invalid_status_fields:
        issues.append(
            make_production_config_issue(
                "USER_CASE_CONSTRAINT_STATUS_INVALID",
                "USER_CASE Constraint Status가 올바르지 않습니다.",
                {"fields": invalid_status_fields},
            )
        )
    return issues


def validate_story_dna_semantics(
    document: Mapping[str, object],
    reference_policy: Mapping[str, object],
) -> list[ValidationIssue]:
    """범인 구조, Source Mode, Reference 분리 규칙을 의미적으로 검사한다."""
    story_dna = document.get("story_dna")
    if not isinstance(story_dna, Mapping):
        return [
            make_story_issue(
                "STORY_DNA_MISSING",
                "story_dna 객체가 없습니다.",
                {},
            )
        ]

    issues: list[ValidationIssue] = []
    culprit_structure = story_dna.get("culprit_structure")
    causal_truth = story_dna.get("causal_truth")
    motive_class = story_dna.get("motive_class")
    if culprit_structure in CAUSAL_STRUCTURES and (
        not isinstance(causal_truth, str) or not causal_truth.strip()
    ):
        issues.append(
            make_story_issue(
                "CAUSAL_TRUTH_REQUIRED",
                "범인이 없는 인과 구조에는 causal_truth가 필요합니다.",
                {"culprit_structure": culprit_structure},
            )
        )
    if culprit_structure not in CAUSAL_STRUCTURES and (
        not isinstance(motive_class, str) or not motive_class
    ):
        issues.append(
            make_story_issue(
                "MOTIVE_CLASS_REQUIRED",
                "범인이 존재하는 구조에는 motive_class가 필요합니다.",
                {"culprit_structure": culprit_structure},
            )
        )

    source_mode = document.get("story_source_mode")
    reference_profile = document.get("reference_profile")
    if source_mode != "REFERENCE_INSPIRED":
        if reference_profile is not None:
            issues.append(
                make_story_issue(
                    "REFERENCE_PROFILE_NOT_ALLOWED",
                    "REFERENCE_INSPIRED가 아닌 프로젝트는 reference_profile을 포함할 수 없습니다.",
                    {"story_source_mode": source_mode},
                )
            )
        return issues

    if not isinstance(reference_profile, Mapping):
        issues.append(
            make_story_issue(
                "REFERENCE_PROFILE_REQUIRED",
                "REFERENCE_INSPIRED 프로젝트에는 sanitized reference_profile이 필요합니다.",
                {},
            )
        )
        return issues

    allowed_by_policy = string_set(reference_policy.get("allowed_style_features"))
    prohibited_by_policy = string_set(reference_policy.get("prohibited_story_content"))
    selected_features = string_set(reference_profile.get("allowed_style_features"))
    declared_prohibited = string_set(reference_profile.get("prohibited_story_content"))
    unsupported_features = sorted(selected_features - allowed_by_policy)
    missing_firewall_fields = sorted(prohibited_by_policy - declared_prohibited)
    if unsupported_features:
        issues.append(
            make_story_issue(
                "REFERENCE_STYLE_FEATURE_NOT_ALLOWED",
                "Reference Profile에 허용되지 않은 Style Feature가 있습니다.",
                {"unsupported_features": unsupported_features},
            )
        )
    if missing_firewall_fields:
        issues.append(
            make_story_issue(
                "REFERENCE_FIREWALL_INCOMPLETE",
                "Reference Profile이 금지 Story Content를 모두 차단하지 않습니다.",
                {"missing_fields": missing_firewall_fields},
            )
        )
    return issues


def validate_reference_profile_alignment(
    story_document: Mapping[str, object],
    profile_document: Mapping[str, object],
) -> list[ValidationIssue]:
    """별도 Reference Artifact와 Story DNA의 Source Mode/Profile 일치를 검사한다."""
    source_mode = story_document.get("story_source_mode")
    profile_mode = profile_document.get("mode")
    embedded_profile = story_document.get("reference_profile")
    issues: list[ValidationIssue] = []
    if source_mode != "REFERENCE_INSPIRED":
        profile_has_content = bool(
            string_set(profile_document.get("allowed_style_features"))
            or string_set(profile_document.get("prohibited_story_content"))
        )
        if (
            profile_mode != "NONE"
            or profile_document.get("reference_id") is not None
            or profile_has_content
        ):
            issues.append(
                make_reference_profile_issue(
                    "REFERENCE_ARTIFACT_NOT_EMPTY",
                    "Reference를 사용하지 않는 Project의 별도 Profile은 NONE이어야 합니다.",
                    {"profile_mode": profile_mode},
                )
            )
        return issues

    if profile_mode != "REFERENCE_INSPIRED" or not isinstance(embedded_profile, Mapping):
        issues.append(
            make_reference_profile_issue(
                "REFERENCE_ARTIFACT_MODE_MISMATCH",
                "Story DNA와 별도 Reference Profile의 Mode가 일치하지 않습니다.",
                {"profile_mode": profile_mode},
            )
        )
        return issues

    comparable_fields = (
        "reference_id",
        "allowed_style_features",
        "prohibited_story_content",
        "separation_attestation",
    )
    mismatches = [
        field
        for field in comparable_fields
        if profile_document.get(field) != embedded_profile.get(field)
    ]
    if mismatches:
        issues.append(
            make_reference_profile_issue(
                "REFERENCE_ARTIFACT_CONTENT_MISMATCH",
                "Story DNA와 별도 Reference Profile의 정제 내용이 다릅니다.",
                {"fields": mismatches},
            )
        )
    return issues

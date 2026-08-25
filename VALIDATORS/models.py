"""호환성 판정 데이터 형식."""

from typing import Literal, TypedDict

CompatibilityResult = Literal["PASS", "FAIL"]
RequiredCapabilityStatus = Literal["SUPPORTED", "MISSING"]
OptionalCapabilityStatus = Literal["SUPPORTED", "MISSING_USE_DEFAULT", "MISSING_DEFAULT"]
CapabilitySource = Literal["CHANNEL", "STANDARD_DEFAULT"]
Severity = Literal["ERROR", "WARN", "INFO"]
GateStatus = Literal["PASS", "FAIL", "NOT_RUN"]
ArtifactStatus = Literal["CLEAN", "DIRTY", "INVALID", "MISSING"]
ProjectStatus = Literal[
    "INITIALIZED",
    "COMPATIBILITY_VALIDATED",
    "VARIATION_APPROVED",
    "STORY_DESIGNED",
    "CASE_DEFINED",
    "CHARACTERS_DESIGNED",
    "MYSTERY_DESIGNED",
    "STORY_STRUCTURED",
    "SCENES_DESIGNED",
    "SCRIPT_WRITTEN",
    "QA_PASSED",
    "PRODUCTION_READY",
    "BLOCKED",
]


class CompatibilityError(TypedDict):
    """호환성 오류 한 건."""

    code: str
    message: str
    context: dict[str, object]


class ChannelSummary(TypedDict):
    """판정 대상 Channel DNA 식별 정보."""

    channel_id: str
    schema_family: str
    schema_version: str
    content_version: str


class ResolvedCapability(TypedDict):
    """선택 Capability의 최종 출처와 값."""

    source: CapabilitySource
    value: object


class CompatibilityReport(TypedDict):
    """Story 생성 전에 소비하는 호환성 보고서."""

    contract_family: str
    contract_version: str
    channel: ChannelSummary
    compatibility: CompatibilityResult
    required_capabilities: dict[str, RequiredCapabilityStatus]
    optional_capabilities: dict[str, OptionalCapabilityStatus]
    resolved_optional_capabilities: dict[str, ResolvedCapability]
    ignored_unknown_fields: list[str]
    ignored_unknown_capabilities: list[str]
    errors: list[CompatibilityError]


class ValidationIssue(TypedDict):
    """Production Gate가 소비하는 공통 검증 문제."""

    severity: Severity
    code: str
    message: str
    artifact: str
    context: dict[str, object]


class ArtifactState(TypedDict):
    """Artifact의 유효성과 변경 전파 상태."""

    status: ArtifactStatus
    content_hash: str | None
    invalidated_by: list[str]


class ProjectState(TypedDict):
    """프로젝트 전체 상태와 Artifact 상태 집합."""

    schema_family: str
    schema_version: str
    project_id: str
    state: ProjectStatus
    current_gate: str
    updated_at: str
    artifacts: dict[str, ArtifactState]


class ProductionValidationReport(TypedDict):
    """전체 Production Gate 판정 결과."""

    schema_family: str
    schema_version: str
    project_id: str
    result: CompatibilityResult
    gate_results: dict[str, GateStatus]
    issues: list[ValidationIssue]

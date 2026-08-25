"""호환성 판정 데이터 형식."""

from typing import Literal, TypedDict

CompatibilityResult = Literal["PASS", "FAIL"]
RequiredCapabilityStatus = Literal["SUPPORTED", "MISSING"]
OptionalCapabilityStatus = Literal["SUPPORTED", "MISSING_USE_DEFAULT", "MISSING_DEFAULT"]
CapabilitySource = Literal["CHANNEL", "STANDARD_DEFAULT"]


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

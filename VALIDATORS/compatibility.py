"""Production Standard와 Channel DNA의 Capability Negotiation."""

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import cast

from VALIDATORS.exceptions import ConfigurationError, InvalidSemanticVersionError
from VALIDATORS.models import (
    CapabilitySource,
    ChannelSummary,
    CompatibilityError,
    CompatibilityReport,
    CompatibilityResult,
    OptionalCapabilityStatus,
    ProjectCompatibilityReport,
    RequiredCapabilityStatus,
    ResolvedCapability,
)

SEMANTIC_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
KNOWN_CHANNEL_FIELDS = {
    "$schema",
    "schema_family",
    "schema_version",
    "content_version",
    "channel_id",
    "identity",
    "capabilities",
}


def require_mapping(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> dict[str, object]:
    """구성 문서에서 필수 객체 필드를 읽는다."""
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise ConfigurationError(
            f"필수 객체 필드가 없거나 형식이 잘못되었습니다: source={source}, field={key}"
        )
    return cast(dict[str, object], dict(value))


def require_string(document: Mapping[str, object], key: str, source: str) -> str:
    """구성 문서에서 비어 있지 않은 문자열 필드를 읽는다."""
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(
            f"필수 문자열 필드가 없거나 형식이 잘못되었습니다: source={source}, field={key}"
        )
    return value


def require_string_list(
    document: Mapping[str, object],
    key: str,
    source: str,
) -> list[str]:
    """구성 문서에서 문자열 배열 필드를 읽는다."""
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"필수 문자열 배열이 없거나 형식이 잘못되었습니다: source={source}, field={key}"
        )
    return cast(list[str], value.copy())


def optional_string(document: Mapping[str, object], key: str) -> str:
    """Channel 문서의 문자열 값을 읽고 잘못된 값은 빈 문자열로 표시한다."""
    value = document.get(key)
    return value if isinstance(value, str) else ""


def mapping_or_empty(document: Mapping[str, object], key: str) -> dict[str, object]:
    """Channel 문서의 객체 값을 읽고 구조 오류는 빈 객체로 유지한다."""
    value = document.get(key)
    if not isinstance(value, Mapping):
        return {}
    return cast(dict[str, object], dict(value))


def parse_semantic_version(value: str) -> tuple[int, int, int]:
    """엄격한 Major.Minor.Patch 버전을 비교 가능한 튜플로 변환한다."""
    match = SEMANTIC_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise InvalidSemanticVersionError(
            f"Semantic Version은 Major.Minor.Patch 형식이어야 합니다: value={value!r}"
        )
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def channel_dna_sha256(channel: Mapping[str, object]) -> str:
    """Channel DNA의 정규 JSON 표현에 대한 SHA-256을 계산한다."""
    encoded = json.dumps(
        dict(channel),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_error(code: str, message: str, context: dict[str, object]) -> CompatibilityError:
    """호환성 오류를 표준 형식으로 생성한다."""
    return CompatibilityError(code=code, message=message, context=context)


def evaluate_version(
    channel_version: str,
    minimum_version: str,
    maximum_version: str,
) -> list[CompatibilityError]:
    """Channel Schema Version이 반개구간 호환 범위에 있는지 판정한다."""
    try:
        parsed_channel_version = parse_semantic_version(channel_version)
    except InvalidSemanticVersionError as error:
        return [
            make_error(
                "INVALID_SCHEMA_VERSION",
                str(error),
                {"schema_version": channel_version},
            )
        ]

    parsed_minimum_version = parse_semantic_version(minimum_version)
    parsed_maximum_version = parse_semantic_version(maximum_version)
    if parsed_minimum_version >= parsed_maximum_version:
        raise ConfigurationError(
            "지원 Schema Version 범위가 올바르지 않습니다: "
            f"min_inclusive={minimum_version}, max_exclusive={maximum_version}"
        )

    if parsed_minimum_version <= parsed_channel_version < parsed_maximum_version:
        return []

    return [
        make_error(
            "UNSUPPORTED_SCHEMA_VERSION",
            "Channel DNA Schema Version이 계약 지원 범위를 벗어났습니다.",
            {
                "schema_version": channel_version,
                "min_inclusive": minimum_version,
                "max_exclusive": maximum_version,
            },
        )
    ]


def evaluate_required_capabilities(
    required_capabilities: list[str],
    channel_capabilities: Mapping[str, object],
) -> tuple[dict[str, RequiredCapabilityStatus], list[CompatibilityError]]:
    """필수 Capability 존재 여부를 판정한다."""
    statuses: dict[str, RequiredCapabilityStatus] = {
        capability: "SUPPORTED" if capability in channel_capabilities else "MISSING"
        for capability in required_capabilities
    }
    errors = [
        make_error(
            "MISSING_REQUIRED_CAPABILITY",
            "필수 Capability가 없습니다.",
            {"capability": capability},
        )
        for capability, status in statuses.items()
        if status == "MISSING"
    ]
    return statuses, errors


def evaluate_optional_capabilities(
    optional_capabilities: list[str],
    channel_capabilities: Mapping[str, object],
    default_capabilities: Mapping[str, object],
) -> tuple[
    dict[str, OptionalCapabilityStatus],
    dict[str, ResolvedCapability],
    list[CompatibilityError],
]:
    """선택 Capability를 Channel 우선으로 해석하고 누락값만 기본값으로 채운다."""
    statuses: dict[str, OptionalCapabilityStatus] = {}
    resolved: dict[str, ResolvedCapability] = {}
    errors: list[CompatibilityError] = []

    for capability in optional_capabilities:
        if capability in channel_capabilities:
            source: CapabilitySource = "CHANNEL"
            statuses[capability] = "SUPPORTED"
            resolved[capability] = ResolvedCapability(
                source=source,
                value=deepcopy(channel_capabilities[capability]),
            )
            continue

        if capability in default_capabilities:
            source = "STANDARD_DEFAULT"
            statuses[capability] = "MISSING_USE_DEFAULT"
            resolved[capability] = ResolvedCapability(
                source=source,
                value=deepcopy(default_capabilities[capability]),
            )
            continue

        statuses[capability] = "MISSING_DEFAULT"
        errors.append(
            make_error(
                "MISSING_OPTIONAL_DEFAULT",
                "누락된 선택 Capability에 사용할 Standard Default가 없습니다.",
                {"capability": capability},
            )
        )

    return statuses, resolved, errors


def evaluate_compatibility(
    contract: Mapping[str, object],
    defaults: Mapping[str, object],
    channel: Mapping[str, object],
) -> CompatibilityReport:
    """계약과 기본값을 사용해 Channel DNA 호환성을 순수 판정한다."""
    interface = require_mapping(contract, "channel_dna_interface", "compatibility_contract")
    supported_versions = require_mapping(
        interface,
        "supported_schema_versions",
        "compatibility_contract.channel_dna_interface",
    )
    required_capabilities = require_string_list(
        interface,
        "required_capabilities",
        "compatibility_contract.channel_dna_interface",
    )
    optional_capabilities = require_string_list(
        interface,
        "optional_capabilities",
        "compatibility_contract.channel_dna_interface",
    )
    overlap = sorted(set(required_capabilities) & set(optional_capabilities))
    if overlap:
        raise ConfigurationError(
            f"Required와 Optional Capability가 중복됩니다: capabilities={overlap}"
        )

    default_capabilities = require_mapping(
        defaults,
        "optional_capability_defaults",
        "standard_defaults",
    )
    channel_capabilities = mapping_or_empty(channel, "capabilities")
    required_statuses, required_errors = evaluate_required_capabilities(
        required_capabilities,
        channel_capabilities,
    )
    optional_statuses, resolved_capabilities, optional_errors = (
        evaluate_optional_capabilities(
            optional_capabilities,
            channel_capabilities,
            default_capabilities,
        )
    )

    expected_schema_family = require_string(
        interface,
        "schema_family",
        "compatibility_contract.channel_dna_interface",
    )
    actual_schema_family = optional_string(channel, "schema_family")
    family_errors = (
        []
        if actual_schema_family == expected_schema_family
        else [
            make_error(
                "UNSUPPORTED_SCHEMA_FAMILY",
                "Channel DNA Schema Family가 계약과 다릅니다.",
                {
                    "expected": expected_schema_family,
                    "actual": actual_schema_family,
                },
            )
        ]
    )
    version_errors = evaluate_version(
        optional_string(channel, "schema_version"),
        require_string(supported_versions, "min_inclusive", "supported_schema_versions"),
        require_string(supported_versions, "max_exclusive", "supported_schema_versions"),
    )
    errors = family_errors + version_errors + required_errors + optional_errors
    compatibility: CompatibilityResult = "FAIL" if errors else "PASS"
    known_capabilities = set(required_capabilities) | set(optional_capabilities)

    channel_summary = ChannelSummary(
        channel_id=optional_string(channel, "channel_id"),
        schema_family=actual_schema_family,
        schema_version=optional_string(channel, "schema_version"),
        content_version=optional_string(channel, "content_version"),
        channel_dna_sha256=channel_dna_sha256(channel),
    )
    return CompatibilityReport(
        contract_family=require_string(contract, "contract_family", "compatibility_contract"),
        contract_version=require_string(contract, "contract_version", "compatibility_contract"),
        channel=channel_summary,
        compatibility=compatibility,
        required_capabilities=required_statuses,
        optional_capabilities=optional_statuses,
        resolved_optional_capabilities=resolved_capabilities,
        ignored_unknown_fields=sorted(set(channel) - KNOWN_CHANNEL_FIELDS),
        ignored_unknown_capabilities=sorted(set(channel_capabilities) - known_capabilities),
        errors=errors,
    )


def append_errors(
    report: CompatibilityReport,
    additional_errors: list[CompatibilityError],
) -> CompatibilityReport:
    """기존 보고서를 변경하지 않고 추가 오류를 반영한 새 보고서를 반환한다."""
    combined_errors = deepcopy(report["errors"]) + deepcopy(additional_errors)
    compatibility: CompatibilityResult = "FAIL" if combined_errors else "PASS"
    return CompatibilityReport(
        contract_family=report["contract_family"],
        contract_version=report["contract_version"],
        channel=deepcopy(report["channel"]),
        compatibility=compatibility,
        required_capabilities=deepcopy(report["required_capabilities"]),
        optional_capabilities=deepcopy(report["optional_capabilities"]),
        resolved_optional_capabilities=deepcopy(report["resolved_optional_capabilities"]),
        ignored_unknown_fields=report["ignored_unknown_fields"].copy(),
        ignored_unknown_capabilities=report["ignored_unknown_capabilities"].copy(),
        errors=combined_errors,
    )


def manifest_version_entry(
    manifest: Mapping[str, object],
    content_version: str,
) -> Mapping[str, object] | None:
    """Manifest에서 Semantic Version이 같은 Channel 항목을 찾는다."""
    try:
        requested = parse_semantic_version(content_version)
    except InvalidSemanticVersionError:
        return None
    entries = manifest.get("available_versions")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        candidate = entry.get("content_version")
        if not isinstance(candidate, str):
            continue
        try:
            if parse_semantic_version(candidate) == requested:
                return entry
        except InvalidSemanticVersionError:
            continue
    return None


def evaluate_channel_binding(
    report: CompatibilityReport,
    production_config: Mapping[str, object],
    channel_manifest: Mapping[str, object],
    channel: Mapping[str, object],
) -> CompatibilityReport:
    """Project 핀, Manifest 등록 정보, 실제 DNA의 동일성을 판정한다."""
    pinned_version = optional_string(production_config, "channel_content_version")
    actual_version = optional_string(channel, "content_version")
    entry = manifest_version_entry(channel_manifest, pinned_version)
    errors: list[CompatibilityError] = []

    if entry is None:
        errors.append(
            make_error(
                "CHANNEL_CONTENT_VERSION_NOT_FOUND",
                "Project가 고정한 Channel Content Version이 Manifest에 없습니다.",
                {
                    "channel_id": production_config.get("channel_id"),
                    "channel_content_version": pinned_version,
                },
            )
        )

    versions_match = False
    try:
        versions_match = parse_semantic_version(pinned_version) == parse_semantic_version(
            actual_version
        )
    except InvalidSemanticVersionError:
        versions_match = False
    if not versions_match:
        errors.append(
            make_error(
                "CHANNEL_CONTENT_VERSION_MISMATCH",
                "Project가 고정한 Content Version과 실제 Channel DNA가 다릅니다.",
                {
                    "expected": pinned_version,
                    "actual": actual_version,
                },
            )
        )

    if entry is not None:
        expected_hash = entry.get("channel_dna_sha256")
        actual_hash = channel_dna_sha256(channel)
        if not isinstance(expected_hash, str) or expected_hash != actual_hash:
            errors.append(
                make_error(
                    "CHANNEL_DNA_HASH_MISMATCH",
                    "Manifest에 고정된 SHA-256과 실제 Channel DNA가 다릅니다.",
                    {
                        "content_version": pinned_version,
                        "expected": expected_hash,
                        "actual": actual_hash,
                    },
                )
            )

    return append_errors(report, errors)


def make_project_compatibility_report(
    project_id: str,
    report: CompatibilityReport,
    relative_path: str,
) -> ProjectCompatibilityReport:
    """Project ID와 호환성 판정 결과를 새 Project Report로 결합한다."""
    channel = deepcopy(report["channel"])
    channel["relative_path"] = relative_path
    return ProjectCompatibilityReport(
        project_id=project_id,
        contract_family=report["contract_family"],
        contract_version=report["contract_version"],
        channel=channel,
        compatibility=report["compatibility"],
        required_capabilities=deepcopy(report["required_capabilities"]),
        optional_capabilities=deepcopy(report["optional_capabilities"]),
        resolved_optional_capabilities=deepcopy(
            report["resolved_optional_capabilities"]
        ),
        ignored_unknown_fields=report["ignored_unknown_fields"].copy(),
        ignored_unknown_capabilities=report["ignored_unknown_capabilities"].copy(),
        errors=deepcopy(report["errors"]),
    )

"""Project별 Channel 정책과 Artifact 필수 조건을 단일하게 판정한다."""

from collections.abc import Mapping

from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError


def enabled_capability(
    channel: Mapping[str, object],
    capability_id: str,
) -> bool:
    """명시적으로 활성화된 Channel Capability인지 반환한다."""
    capabilities = channel.get("capabilities")
    capability = (
        capabilities.get(capability_id)
        if isinstance(capabilities, Mapping)
        else None
    )
    return isinstance(capability, Mapping) and capability.get("enabled") is True


def crime_v2_candidate_policy_applies(
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
) -> bool:
    """Project가 고정한 v2 범죄 심리 후보 정책의 적용 여부를 반환한다."""
    version = production_config.get("channel_content_version")
    if not isinstance(version, str):
        raise ConfigurationError("channel_content_version 문자열이 필요합니다.")
    return (
        parse_semantic_version(version) >= parse_semantic_version("2.0.0")
        and enabled_capability(channel, "CRIME_PSYCHOLOGY_POLICY")
    )


def requirement_matches(
    predicate: object,
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
    artifacts: Mapping[str, object],
) -> bool:
    """구조화된 조건식을 재귀적으로 평가한다."""
    if predicate == "ALWAYS" or predicate == {"always": True}:
        return True
    if not isinstance(predicate, Mapping) or len(predicate) != 1:
        raise ConfigurationError(f"Requirement Predicate 형식이 올바르지 않습니다: {predicate!r}")
    operator, value = next(iter(predicate.items()))
    if operator == "all":
        if not isinstance(value, list):
            raise ConfigurationError("Requirement all은 배열이어야 합니다.")
        return all(
            requirement_matches(item, production_config, channel, artifacts)
            for item in value
        )
    if operator == "any":
        if not isinstance(value, list):
            raise ConfigurationError("Requirement any는 배열이어야 합니다.")
        return any(
            requirement_matches(item, production_config, channel, artifacts)
            for item in value
        )
    if operator == "not":
        return not requirement_matches(value, production_config, channel, artifacts)
    if operator == "capability_enabled":
        if not isinstance(value, str):
            raise ConfigurationError("capability_enabled는 문자열이어야 합니다.")
        return enabled_capability(channel, value)
    if operator == "source_truth_in":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ConfigurationError("source_truth_in은 문자열 배열이어야 합니다.")
        return production_config.get("source_truth_classification") in value
    if operator == "story_source_mode_in":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ConfigurationError("story_source_mode_in은 문자열 배열이어야 합니다.")
        return production_config.get("story_source_mode") in value
    if operator == "channel_version_at_least":
        version = production_config.get("channel_content_version")
        if not isinstance(value, str) or not isinstance(version, str):
            raise ConfigurationError("Channel Version Requirement 문자열이 필요합니다.")
        return parse_semantic_version(version) >= parse_semantic_version(value)
    if operator == "artifact_status":
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise ConfigurationError("artifact_status는 [artifact, status]여야 합니다.")
        artifact = artifacts.get(value[0])
        return isinstance(artifact, Mapping) and artifact.get("status") == value[1]
    if operator == "artifact_exists":
        if not isinstance(value, str):
            raise ConfigurationError("artifact_exists는 문자열이어야 합니다.")
        return value in artifacts
    raise ConfigurationError(f"알 수 없는 Requirement Operator입니다: operator={operator!r}")

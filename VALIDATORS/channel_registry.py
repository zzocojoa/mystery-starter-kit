"""Project별 Channel Content Version을 Manifest에서 해석한다."""

from collections.abc import Mapping
from pathlib import Path

from VALIDATORS.compatibility import (
    channel_dna_sha256,
    manifest_version_entry,
    parse_semantic_version,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors


def channel_directory(repository_root: Path, channel_id: str) -> Path:
    """Channel ID를 저장소의 Channel 디렉터리로 변환한다."""
    return repository_root / "CHANNELS" / channel_id.lower()


def load_validated_channel_manifest(
    repository_root: Path,
    channel_id: str,
) -> tuple[dict[str, object], Path]:
    """Channel Manifest를 읽고 Schema 및 활성 버전 등록을 검증한다."""
    directory = channel_directory(repository_root, channel_id)
    manifest_path = directory / "channel_manifest.json"
    schema_path = repository_root / "STANDARD" / "schemas" / "channel_manifest.schema.json"
    manifest = load_json_object(manifest_path)
    schema = load_json_object(schema_path)
    errors = collect_schema_errors(manifest, schema, str(manifest_path))
    if errors:
        raise ConfigurationError(
            "Channel Manifest가 Schema를 통과하지 못했습니다: "
            f"path={manifest_path}, errors={errors}"
        )
    if manifest.get("channel_id") != channel_id:
        raise ConfigurationError(
            "Channel Manifest ID가 요청 Channel과 다릅니다: "
            f"expected={channel_id}, actual={manifest.get('channel_id')!r}"
        )
    entries = manifest.get("available_versions")
    if not isinstance(entries, list):
        raise ConfigurationError("Channel Manifest available_versions 배열이 필요합니다.")
    parsed_versions: list[tuple[int, int, int]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ConfigurationError("Channel Manifest Version 항목은 객체여야 합니다.")
        content_version = entry.get("content_version")
        if not isinstance(content_version, str):
            raise ConfigurationError(
                "Channel Manifest Version 항목에 content_version이 필요합니다."
            )
        parsed_versions.append(parse_semantic_version(content_version))
    duplicate_versions = sorted(
        {
            version
            for version in parsed_versions
            if parsed_versions.count(version) > 1
        }
    )
    if duplicate_versions:
        raise ConfigurationError(
            "Channel Manifest Content Version이 중복되었습니다: "
            f"versions={duplicate_versions}"
        )
    active_version = manifest.get("active_content_version")
    if not isinstance(active_version, str) or manifest_version_entry(
        manifest, active_version
    ) is None:
        raise ConfigurationError(
            "Channel Manifest 활성 버전이 available_versions에 없습니다: "
            f"channel_id={channel_id}, active_content_version={active_version!r}"
        )
    return manifest, manifest_path


def entry_channel_path(
    channel_directory_path: Path,
    entry: Mapping[str, object],
) -> Path:
    """Manifest 항목의 DNA 경로를 Channel 디렉터리 내부로 제한한다."""
    relative_path = entry.get("channel_dna")
    if not isinstance(relative_path, str):
        raise ConfigurationError("Channel Manifest channel_dna 문자열이 필요합니다.")
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ConfigurationError(
            "Channel DNA 상대 경로가 안전하지 않습니다: "
            f"relative_path={relative_path!r}"
        )
    resolved_directory = channel_directory_path.resolve()
    resolved_path = (channel_directory_path / path).resolve()
    if not resolved_path.is_relative_to(resolved_directory):
        raise ConfigurationError(
            "Channel DNA 경로가 Channel 디렉터리 밖을 가리킵니다: "
            f"path={resolved_path}"
        )
    return resolved_path


def registered_channel_relative_path(
    manifest: Mapping[str, object],
    content_version: str,
) -> str:
    """등록된 Content Version의 Channel 상대 경로를 반환한다."""
    entry = manifest_version_entry(manifest, content_version)
    if entry is None:
        raise ConfigurationError(
            "CHANNEL_CONTENT_VERSION_NOT_FOUND: Project가 고정한 Channel Content "
            f"Version이 Manifest에 없습니다: content_version={content_version}"
        )
    relative_path = entry.get("channel_dna")
    if not isinstance(relative_path, str):
        raise ConfigurationError(
            "Channel Manifest Version 항목에 channel_dna 문자열이 필요합니다: "
            f"content_version={content_version}"
        )
    return relative_path


def resolve_project_channel(
    repository_root: Path,
    production_config: Mapping[str, object],
    channel_override: Path | None,
) -> tuple[dict[str, object], dict[str, object], Path]:
    """Project 핀에 맞는 DNA를 읽고 Manifest와 실제 입력 경로를 반환한다."""
    channel_id = production_config.get("channel_id")
    pinned_version = production_config.get("channel_content_version")
    if not isinstance(channel_id, str) or not isinstance(pinned_version, str):
        raise ConfigurationError(
            "production_config.channel_id와 channel_content_version 문자열이 필요합니다."
        )
    parse_semantic_version(pinned_version)
    manifest, manifest_path = load_validated_channel_manifest(repository_root, channel_id)
    entry = manifest_version_entry(manifest, pinned_version)
    if entry is None:
        raise ConfigurationError(
            "CHANNEL_CONTENT_VERSION_NOT_FOUND: Project가 고정한 Channel Content "
            "Version이 Manifest에 없습니다: "
            f"channel_id={channel_id}, content_version={pinned_version}"
        )
    selected_path = (
        channel_override
        if channel_override is not None
        else entry_channel_path(manifest_path.parent, entry)
    )
    channel = load_json_object(selected_path)
    channel_schema_path = (
        repository_root / "STANDARD" / "schemas" / "channel_dna.schema.json"
    )
    channel_errors = collect_schema_errors(
        channel,
        load_json_object(channel_schema_path),
        str(selected_path),
    )
    if channel_errors:
        raise ConfigurationError(
            "CHANNEL_DNA_SCHEMA_INVALID: Channel DNA가 Schema를 통과하지 못했습니다: "
            f"path={selected_path}, errors={channel_errors}"
        )
    if channel.get("channel_id") != channel_id:
        raise ConfigurationError(
            "CHANNEL_ID_MISMATCH: Channel DNA ID가 Project Pin과 다릅니다: "
            f"expected={channel_id}, actual={channel.get('channel_id')!r}"
        )
    if channel.get("content_version") != pinned_version:
        raise ConfigurationError(
            "CHANNEL_CONTENT_VERSION_MISMATCH: Channel DNA Content Version이 Project Pin과 "
            f"다릅니다: expected={pinned_version}, actual={channel.get('content_version')!r}"
        )
    expected_hash = entry.get("channel_dna_sha256")
    actual_hash = channel_dna_sha256(channel)
    if not isinstance(expected_hash, str) or actual_hash != expected_hash:
        raise ConfigurationError(
            "CHANNEL_DNA_HASH_MISMATCH: Channel DNA가 Manifest의 Canonical Hash와 다릅니다: "
            f"expected={expected_hash!r}, actual={actual_hash}"
        )
    return channel, manifest, selected_path

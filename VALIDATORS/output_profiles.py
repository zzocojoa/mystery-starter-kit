"""Versioned Output Profile Pin, Registry와 파일 무결성을 검증한다."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Literal, TypedDict, cast

from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ScriptSourceMode = Literal["LEGACY_MARKDOWN", "SCREENPLAY_UNITS"]


class ResolvedOutputProfile(TypedDict):
    """검증된 Output Profile과 고정 식별 정보."""

    profile_id: str
    profile_version: str
    sha256: str
    relative_path: str
    document: dict[str, object]


def script_source_mode(production_config: Mapping[str, object]) -> ScriptSourceMode:
    """필드가 없는 기존 Project를 Legacy Markdown으로 해석한다."""
    value = production_config.get("script_source_mode", "LEGACY_MARKDOWN")
    if value not in {"LEGACY_MARKDOWN", "SCREENPLAY_UNITS"}:
        raise ConfigurationError(
            "SCRIPT_SOURCE_MODE_INVALID: production_config.script_source_mode는 "
            "LEGACY_MARKDOWN 또는 SCREENPLAY_UNITS여야 합니다."
        )
    return cast(ScriptSourceMode, value)


def repository_profile_path(
    repository_root: Path,
    relative_path: str,
    error_prefix: str,
) -> Path:
    """Registry 경로를 Repository 내부 JSON 파일로 제한한다."""
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix != ".json":
        raise ConfigurationError(
            f"{error_prefix}_PATH_INVALID: path={relative_path}"
        )
    root = repository_root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ConfigurationError(
            f"{error_prefix}_PATH_INVALID: path={relative_path}"
        )
    return resolved


def schema_valid_document(
    document_path: Path,
    schema_path: Path,
    code: str,
) -> dict[str, object]:
    """문서를 읽어 대응 JSON Schema 위반을 계약 오류로 변환한다."""
    document = load_json_object(document_path)
    schema = load_json_object(schema_path)
    errors = collect_schema_errors(document, schema, str(document_path))
    if errors:
        raise ConfigurationError(f"{code}: errors={errors}")
    return document


def required_profile_pin(
    production_config: Mapping[str, object],
    field: str,
    error_prefix: str,
) -> str:
    """SCREENPLAY_UNITS mode에서 필수 Profile Pin 문자열을 읽는다."""
    value = production_config.get(field)
    if not isinstance(value, str):
        raise ConfigurationError(
            f"{error_prefix}_PIN_MISSING: production_config.{field}가 없습니다."
        )
    return value


def resolve_registered_output_profile(
    repository_root: Path,
    production_config: Mapping[str, object],
    profile_id_field: str,
    profile_version_field: str,
    profile_schema_name: str,
    error_prefix: str,
) -> ResolvedOutputProfile | None:
    """공용 Registry에서 명시적으로 고정한 Output Profile을 해석한다."""
    if script_source_mode(production_config) == "LEGACY_MARKDOWN":
        return None
    profile_id = required_profile_pin(
        production_config,
        profile_id_field,
        error_prefix,
    )
    profile_version = required_profile_pin(
        production_config,
        profile_version_field,
        error_prefix,
    )
    parse_semantic_version(profile_version)
    registry = schema_valid_document(
        repository_root / "CHANNELS/mystery_main/output_profiles/registry.json",
        repository_root
        / "STANDARD/schemas/reenactment_output_profile_registry.schema.json",
        f"{error_prefix}_REGISTRY_INVALID",
    )
    profiles = registry.get("profiles")
    profile_entry = profiles.get(profile_id) if isinstance(profiles, Mapping) else None
    versions = profile_entry.get("versions") if isinstance(profile_entry, Mapping) else None
    version_entry = versions.get(profile_version) if isinstance(versions, Mapping) else None
    if not isinstance(version_entry, Mapping):
        raise ConfigurationError(
            f"{error_prefix}_PIN_INVALID: "
            f"profile_id={profile_id}, profile_version={profile_version}"
        )
    relative_path = version_entry.get("path")
    expected_hash = version_entry.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
        raise ConfigurationError(
            f"{error_prefix}_REGISTRY_INVALID: "
            f"profile_id={profile_id}, profile_version={profile_version}"
        )
    profile_path = repository_profile_path(
        repository_root,
        relative_path,
        error_prefix,
    )
    try:
        actual_hash = sha256(profile_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ConfigurationError(
            f"{error_prefix}_MISSING: path={relative_path}"
        ) from error
    if actual_hash != expected_hash:
        raise ConfigurationError(
            f"{error_prefix}_HASH_MISMATCH: "
            f"path={relative_path}, expected={expected_hash}, actual={actual_hash}"
        )
    document = schema_valid_document(
        profile_path,
        repository_root / "STANDARD/schemas" / profile_schema_name,
        f"{error_prefix}_INVALID",
    )
    identity_matches = (
        document.get("profile_id") == profile_id
        and document.get("profile_version") == profile_version
    )
    if not identity_matches:
        raise ConfigurationError(
            f"{error_prefix}_IDENTITY_MISMATCH: "
            f"profile_id={profile_id}, profile_version={profile_version}, "
            f"path={relative_path}"
        )
    return ResolvedOutputProfile(
        profile_id=profile_id,
        profile_version=profile_version,
        sha256=actual_hash,
        relative_path=relative_path,
        document=document,
    )


def resolve_reenactment_output_profile(
    repository_root: Path,
    production_config: Mapping[str, object],
) -> ResolvedOutputProfile | None:
    """Production Config Pin으로 Hash 검증된 Output Profile을 해석한다."""
    return resolve_registered_output_profile(
        repository_root,
        production_config,
        "reenactment_output_profile_id",
        "reenactment_output_profile_version",
        "reenactment_output_profile.schema.json",
        "REENACTMENT_OUTPUT_PROFILE",
    )


def resolve_broadcast_readable_output_profile(
    repository_root: Path,
    production_config: Mapping[str, object],
) -> ResolvedOutputProfile | None:
    """Production Config Pin으로 사람용 Broadcast Profile을 해석한다."""
    return resolve_registered_output_profile(
        repository_root,
        production_config,
        "broadcast_readable_output_profile_id",
        "broadcast_readable_output_profile_version",
        "broadcast_readable_output_profile.schema.json",
        "BROADCAST_READABLE_OUTPUT_PROFILE",
    )

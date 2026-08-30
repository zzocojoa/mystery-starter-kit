"""Project Pin과 호환 범위로 Variation Engine·Catalog를 안전하게 해석한다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Protocol, TypedDict, cast

from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue


class VariationEntrypoint(Protocol):
    """검증된 Version Engine의 Eligible Pool Entrypoint 계약."""

    def __call__(
        self,
        project_id: str,
        story_seed: str,
        eligible_candidate_count: int,
        runtime: VariationRuntime,
        source_truth_classification: str,
        production_config: Mapping[str, object],
        project_constraints: Mapping[str, object],
        channel: Mapping[str, object],
        story_history: Sequence[Mapping[str, object]],
        novelty_thresholds: Mapping[str, object],
        projection_contract: Mapping[str, object],
        source_truth_contract: Mapping[str, object] | None,
        max_batches: int,
    ) -> dict[str, object]:
        """적격 Candidate Pool 문서를 반환한다."""


class VariationRuntime(TypedDict):
    """검증된 Variation Runtime 식별자, 구현과 Catalog."""

    engine_version: str
    catalog_version: str
    algorithm_sha256: str
    implementation_sha256: str
    catalog_sha256: str
    catalog_path: str
    entrypoint_name: str
    entrypoint: VariationEntrypoint
    catalog: dict[str, object]


def registry_entries(
    registry: Mapping[str, object],
    registry_name: str,
    field: str,
) -> Mapping[str, object]:
    """Version Registry의 Entry 객체를 반환한다."""
    entries = registry.get(field)
    if not isinstance(entries, Mapping):
        raise ConfigurationError(
            f"VARIATION_REGISTRY_INVALID: {registry_name}.{field} 객체가 없습니다."
        )
    return entries


def pinned_version(config: Mapping[str, object], field: str) -> str:
    """Project Config의 명시적 Semantic Version Pin을 반환한다."""
    value = config.get(field)
    if not isinstance(value, str):
        raise ConfigurationError(
            f"VARIATION_VERSION_PIN_MISSING: production_config.{field}가 없습니다."
        )
    parse_semantic_version(value)
    return value


def version_range(
    document: Mapping[str, object],
    field: str,
    source: str,
) -> tuple[tuple[int, int, int], tuple[int, int, int], str, str]:
    """Registry의 Semantic Version 반개구간을 엄격하게 읽는다."""
    raw_range = document.get(field)
    if not isinstance(raw_range, Mapping):
        raise ConfigurationError(f"VARIATION_REGISTRY_INVALID: {source}.{field} 객체가 없습니다.")
    minimum = raw_range.get("min_inclusive")
    maximum = raw_range.get("max_exclusive")
    if not isinstance(minimum, str) or not isinstance(maximum, str):
        raise ConfigurationError(
            f"VARIATION_REGISTRY_INVALID: {source}.{field} Version 문자열이 없습니다."
        )
    parsed_minimum = parse_semantic_version(minimum)
    parsed_maximum = parse_semantic_version(maximum)
    if parsed_minimum >= parsed_maximum:
        raise ConfigurationError(
            f"VARIATION_REGISTRY_INVALID: {source}.{field} 범위가 비어 있습니다."
        )
    return parsed_minimum, parsed_maximum, minimum, maximum


def ensure_version_supported(
    version: str,
    supported_range: tuple[tuple[int, int, int], tuple[int, int, int], str, str],
    code: str,
    context: str,
) -> None:
    """Version이 반개구간 밖이면 안정적인 오류 코드로 실패한다."""
    minimum, maximum, minimum_text, maximum_text = supported_range
    parsed = parse_semantic_version(version)
    if minimum <= parsed < maximum:
        return
    raise ConfigurationError(
        f"{code}: {context}, version={version}, "
        f"min_inclusive={minimum_text}, max_exclusive={maximum_text}"
    )


def required_capabilities(document: Mapping[str, object], source: str) -> set[str]:
    """Registry 또는 Engine Specification의 필수 Capability를 반환한다."""
    raw_capabilities = document.get("required_capabilities")
    if not isinstance(raw_capabilities, list) or not all(
        isinstance(capability, str) for capability in raw_capabilities
    ):
        raise ConfigurationError(
            f"VARIATION_REGISTRY_INVALID: {source}.required_capabilities 배열이 없습니다."
        )
    return set(raw_capabilities)


def capability_is_available(channel: Mapping[str, object], capability_id: str) -> bool:
    """Channel Capability가 존재하고 명시적 비활성 상태가 아닌지 반환한다."""
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping) or capability_id not in capabilities:
        return False
    capability = capabilities[capability_id]
    if isinstance(capability, Mapping) and "enabled" in capability:
        return capability.get("enabled") is True
    return True


def repository_file(repository_root: Path, relative_path: str, code: str) -> Path:
    """Registry 상대 경로를 Repository 내부의 실제 파일로 제한한다."""
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise ConfigurationError(f"{code}: 안전하지 않은 경로입니다: path={relative_path}")
    root = repository_root.resolve()
    resolved = (repository_root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ConfigurationError(f"{code}: Repository 밖 경로입니다: path={relative_path}")
    return resolved


def file_sha256(path: Path, code: str) -> str:
    """파일 SHA-256을 계산하고 누락을 지정 오류 코드로 변환한다."""
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ConfigurationError(f"{code}: path={path}") from error


def implementation_sha256(
    repository_root: Path,
    relative_paths: Sequence[str],
) -> str:
    """경로명과 파일 Bytes를 결합한 Version 구현 Aggregate Hash를 계산한다."""
    digest = sha256()
    for relative_path in sorted(relative_paths):
        path = repository_file(
            repository_root,
            relative_path,
            "VARIATION_IMPLEMENTATION_FILE_MISSING",
        )
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ConfigurationError(
                f"VARIATION_IMPLEMENTATION_FILE_MISSING: path={relative_path}"
            ) from error
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def implementation_contract(
    engine_entry: Mapping[str, object],
    engine_version: str,
) -> tuple[str, list[str], str]:
    """Engine Registry의 Entrypoint, 파일 목록과 Hash를 읽는다."""
    implementation = engine_entry.get("implementation")
    if not isinstance(implementation, Mapping):
        raise ConfigurationError(f"VARIATION_ENGINE_REGISTRY_INVALID: version={engine_version}")
    entrypoint = implementation.get("entrypoint")
    files = implementation.get("files")
    expected_hash = implementation.get("implementation_sha256")
    if (
        not isinstance(entrypoint, str)
        or not isinstance(files, list)
        or not files
        or not all(isinstance(path, str) for path in files)
        or not isinstance(expected_hash, str)
    ):
        raise ConfigurationError(f"VARIATION_ENGINE_REGISTRY_INVALID: version={engine_version}")
    return entrypoint, list(files), expected_hash


def load_entrypoint(
    entrypoint_name: str,
    implementation_files: Sequence[str],
) -> VariationEntrypoint:
    """Hash 검증 뒤 Versioned Python Entrypoint를 Import한다."""
    module_name, separator, attribute_name = entrypoint_name.partition(":")
    module_path = f"{module_name.replace('.', '/')}.py"
    if not separator or module_path not in implementation_files:
        raise ConfigurationError(f"VARIATION_ENTRYPOINT_INVALID: entrypoint={entrypoint_name}")
    try:
        module = import_module(module_name)
        entrypoint = getattr(module, attribute_name)
    except (ImportError, AttributeError) as error:
        raise ConfigurationError(
            f"VARIATION_ENTRYPOINT_INVALID: entrypoint={entrypoint_name}"
        ) from error
    if not callable(entrypoint):
        raise ConfigurationError(f"VARIATION_ENTRYPOINT_INVALID: entrypoint={entrypoint_name}")
    return cast(VariationEntrypoint, entrypoint)


def resolve_variation_runtime_for_channel(
    repository_root: Path,
    production_config: Mapping[str, object],
    channel: Mapping[str, object],
) -> VariationRuntime:
    """해석된 Channel과 Project Pin으로 Versioned Runtime을 검증한다."""
    engine_version = pinned_version(production_config, "variation_engine_version")
    catalog_version = pinned_version(production_config, "variation_catalog_version")
    channel_content_version = pinned_version(production_config, "channel_content_version")
    if channel.get("content_version") != channel_content_version:
        raise ConfigurationError(
            "CHANNEL_CONTENT_VERSION_MISMATCH: Variation Runtime Channel이 Project Pin과 "
            f"다릅니다: expected={channel_content_version}, "
            f"actual={channel.get('content_version')!r}"
        )
    engine_registry = load_json_object(
        repository_root / "STANDARD" / "variation_engines" / "registry.json"
    )
    catalog_registry = load_json_object(
        repository_root / "STANDARD" / "variation_catalogs" / "registry.json"
    )
    engine_entry = registry_entries(engine_registry, "variation_engines", "engines").get(
        engine_version
    )
    catalog_entry = registry_entries(catalog_registry, "variation_catalogs", "catalogs").get(
        catalog_version
    )
    if not isinstance(engine_entry, Mapping):
        raise ConfigurationError(f"VARIATION_ENGINE_VERSION_NOT_FOUND: version={engine_version}")
    if not isinstance(catalog_entry, Mapping):
        raise ConfigurationError(f"VARIATION_CATALOG_VERSION_NOT_FOUND: version={catalog_version}")
    algorithm_id = engine_entry.get("algorithm_id")
    algorithm_relative_path = engine_entry.get("path")
    algorithm_hash = engine_entry.get("algorithm_sha256")
    if (
        not isinstance(algorithm_id, str)
        or not isinstance(algorithm_relative_path, str)
        or not isinstance(algorithm_hash, str)
    ):
        raise ConfigurationError(f"VARIATION_ENGINE_REGISTRY_INVALID: version={engine_version}")
    algorithm_path = repository_file(
        repository_root,
        algorithm_relative_path,
        "VARIATION_ENGINE_VERSION_NOT_FOUND",
    )
    actual_algorithm_hash = file_sha256(
        algorithm_path,
        "VARIATION_ENGINE_VERSION_NOT_FOUND",
    )
    if actual_algorithm_hash != algorithm_hash:
        raise ConfigurationError(
            "VARIATION_ALGORITHM_HASH_MISMATCH: "
            f"version={engine_version}, expected={algorithm_hash}, "
            f"actual={actual_algorithm_hash}"
        )
    algorithm_specification = load_json_object(algorithm_path)
    if (
        algorithm_specification.get("variation_engine_version") != engine_version
        or algorithm_specification.get("algorithm_id") != algorithm_id
    ):
        raise ConfigurationError(
            f"VARIATION_ENGINE_REGISTRY_INVALID: version={engine_version}, path={algorithm_path}"
        )
    ensure_version_supported(
        channel_content_version,
        version_range(
            algorithm_specification,
            "supported_channel_content_versions",
            f"engine={engine_version}",
        ),
        "VARIATION_ENGINE_CHANNEL_INCOMPATIBLE",
        f"engine={engine_version}, channel={channel_content_version}",
    )
    ensure_version_supported(
        channel_content_version,
        version_range(
            catalog_entry,
            "supported_channel_content_versions",
            f"catalog={catalog_version}",
        ),
        "VARIATION_CATALOG_CHANNEL_INCOMPATIBLE",
        f"catalog={catalog_version}, channel={channel_content_version}",
    )
    ensure_version_supported(
        catalog_version,
        version_range(
            algorithm_specification,
            "supported_catalog_versions",
            f"engine={engine_version}",
        ),
        "VARIATION_ENGINE_CATALOG_INCOMPATIBLE",
        f"engine={engine_version}, catalog={catalog_version}",
    )
    ensure_version_supported(
        engine_version,
        version_range(
            catalog_entry,
            "supported_engine_versions",
            f"catalog={catalog_version}",
        ),
        "VARIATION_ENGINE_CATALOG_INCOMPATIBLE",
        f"engine={engine_version}, catalog={catalog_version}",
    )
    required = required_capabilities(
        algorithm_specification,
        f"engine={engine_version}",
    ) | required_capabilities(catalog_entry, f"catalog={catalog_version}")
    missing_capabilities = sorted(
        capability for capability in required if not capability_is_available(channel, capability)
    )
    if missing_capabilities:
        raise ConfigurationError(
            "VARIATION_REQUIRED_CAPABILITY_MISSING: "
            f"capabilities={missing_capabilities}, channel={channel_content_version}"
        )
    catalog_relative_path = catalog_entry.get("path")
    catalog_hash = catalog_entry.get("catalog_sha256")
    if not isinstance(catalog_relative_path, str) or not isinstance(catalog_hash, str):
        raise ConfigurationError(f"VARIATION_CATALOG_REGISTRY_INVALID: version={catalog_version}")
    catalog_path = repository_file(
        repository_root,
        catalog_relative_path,
        "VARIATION_CATALOG_VERSION_NOT_FOUND",
    )
    actual_catalog_hash = file_sha256(
        catalog_path,
        "VARIATION_CATALOG_VERSION_NOT_FOUND",
    )
    if actual_catalog_hash != catalog_hash:
        raise ConfigurationError(
            "CATALOG_SNAPSHOT_HASH_MISMATCH: "
            f"version={catalog_version}, expected={catalog_hash}, actual={actual_catalog_hash}"
        )
    entrypoint_name, implementation_files, expected_implementation_hash = implementation_contract(
        engine_entry, engine_version
    )
    actual_implementation_hash = implementation_sha256(
        repository_root,
        implementation_files,
    )
    if actual_implementation_hash != expected_implementation_hash:
        raise ConfigurationError(
            "VARIATION_IMPLEMENTATION_HASH_MISMATCH: "
            f"version={engine_version}, expected={expected_implementation_hash}, "
            f"actual={actual_implementation_hash}"
        )
    entrypoint = load_entrypoint(entrypoint_name, implementation_files)
    return VariationRuntime(
        engine_version=engine_version,
        catalog_version=catalog_version,
        algorithm_sha256=algorithm_hash,
        implementation_sha256=expected_implementation_hash,
        catalog_sha256=catalog_hash,
        catalog_path=catalog_relative_path,
        entrypoint_name=entrypoint_name,
        entrypoint=entrypoint,
        catalog=load_json_object(catalog_path),
    )


def resolve_variation_runtime(
    repository_root: Path,
    production_config: Mapping[str, object],
) -> VariationRuntime:
    """Project Channel DNA를 먼저 해석한 뒤 Versioned Runtime을 반환한다."""
    channel, _manifest, _channel_path = resolve_project_channel(
        repository_root,
        production_config,
        None,
    )
    return resolve_variation_runtime_for_channel(
        repository_root,
        production_config,
        channel,
    )


def variation_runtime_binding_issues(
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    runtime: Mapping[str, object],
) -> list[ValidationIssue]:
    """Variation 문서와 Candidate가 Project Pin 및 구현 Hash에 결속됐는지 검증한다."""
    expected = {
        "variation_engine_version": runtime.get("engine_version"),
        "variation_catalog_version": runtime.get("catalog_version"),
        "catalog_sha256": runtime.get("catalog_sha256"),
        "algorithm_sha256": runtime.get("algorithm_sha256"),
        "implementation_sha256": runtime.get("implementation_sha256"),
    }
    mismatches = {
        field: {"expected": value, "actual": variations.get(field)}
        for field, value in expected.items()
        if variations.get(field) != value
    }
    if production_config.get("variation_engine_version") != runtime.get("engine_version"):
        mismatches["production_config.variation_engine_version"] = {
            "expected": runtime.get("engine_version"),
            "actual": production_config.get("variation_engine_version"),
        }
    if production_config.get("variation_catalog_version") != runtime.get("catalog_version"):
        mismatches["production_config.variation_catalog_version"] = {
            "expected": runtime.get("catalog_version"),
            "actual": production_config.get("variation_catalog_version"),
        }
    candidates = variations.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            candidate_id = candidate.get("candidate_id")
            for field, value in expected.items():
                if candidate.get(field) != value:
                    mismatches[f"{candidate_id}.{field}"] = {
                        "expected": value,
                        "actual": candidate.get(field),
                    }
    if not mismatches:
        return []
    return [
        ValidationIssue(
            severity="ERROR",
            code="VARIATION_RUNTIME_BINDING_MISMATCH",
            message=(
                "Variation Candidate가 Project의 Version Pin과 Registry Hash에 결속되지 않았습니다."
            ),
            artifact="00_PROJECT/variation_candidates.json",
            context={"mismatches": mismatches},
        )
    ]

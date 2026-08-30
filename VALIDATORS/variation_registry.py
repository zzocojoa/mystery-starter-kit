"""Project Pin으로 Variation Engine과 Catalog를 해석한다."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import TypedDict

from VALIDATORS.compatibility import parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue


class VariationRuntime(TypedDict):
    """검증된 Variation Runtime 식별자와 Catalog."""

    engine_version: str
    catalog_version: str
    algorithm_sha256: str
    catalog_sha256: str
    catalog: dict[str, object]


def registry_entries(
    registry: Mapping[str, object],
    registry_name: str,
    field: str,
) -> Mapping[str, object]:
    """Version Registry의 entries 객체를 반환한다."""
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


def validate_channel_runtime_pair(
    channel_content_version: str,
    engine_version: str,
    catalog_version: str,
) -> None:
    """Channel 세대와 명시된 Variation Runtime 세대의 조합을 검증한다."""
    is_v2 = parse_semantic_version(channel_content_version) >= (2, 0, 0)
    expected = "2.0.0" if is_v2 else "1.0.0"
    if engine_version != expected or catalog_version != expected:
        raise ConfigurationError(
            "VARIATION_VERSION_CHANNEL_MISMATCH: "
            f"channel={channel_content_version}, expected={expected}, "
            f"engine={engine_version}, catalog={catalog_version}"
        )


def resolve_variation_runtime(
    repository_root: Path,
    production_config: Mapping[str, object],
) -> VariationRuntime:
    """Registry, Hash, Project Pin을 모두 검증한 Variation Runtime을 반환한다."""
    engine_version = pinned_version(production_config, "variation_engine_version")
    catalog_version = pinned_version(production_config, "variation_catalog_version")
    channel_content_version = pinned_version(production_config, "channel_content_version")
    validate_channel_runtime_pair(
        channel_content_version,
        engine_version,
        catalog_version,
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
    algorithm_path = repository_root / algorithm_relative_path
    try:
        actual_algorithm_hash = sha256(algorithm_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ConfigurationError(
            f"VARIATION_ENGINE_VERSION_NOT_FOUND: path={algorithm_path}"
        ) from error
    if actual_algorithm_hash != algorithm_hash:
        raise ConfigurationError(
            "VARIATION_ALGORITHM_HASH_MISMATCH: "
            f"version={engine_version}, expected={algorithm_hash}, actual={actual_algorithm_hash}"
        )
    algorithm_specification = load_json_object(algorithm_path)
    if (
        algorithm_specification.get("variation_engine_version") != engine_version
        or algorithm_specification.get("algorithm_id") != algorithm_id
    ):
        raise ConfigurationError(
            f"VARIATION_ENGINE_REGISTRY_INVALID: version={engine_version}, path={algorithm_path}"
        )
    relative_path = catalog_entry.get("path")
    catalog_hash = catalog_entry.get("catalog_sha256")
    if not isinstance(relative_path, str) or not isinstance(catalog_hash, str):
        raise ConfigurationError(f"VARIATION_CATALOG_REGISTRY_INVALID: version={catalog_version}")
    catalog_path = repository_root / relative_path
    try:
        actual_catalog_hash = sha256(catalog_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ConfigurationError(
            f"VARIATION_CATALOG_VERSION_NOT_FOUND: path={catalog_path}"
        ) from error
    if actual_catalog_hash != catalog_hash:
        raise ConfigurationError(
            "VARIATION_CATALOG_HASH_MISMATCH: "
            f"version={catalog_version}, expected={catalog_hash}, actual={actual_catalog_hash}"
        )
    return VariationRuntime(
        engine_version=engine_version,
        catalog_version=catalog_version,
        algorithm_sha256=algorithm_hash,
        catalog_sha256=catalog_hash,
        catalog=load_json_object(catalog_path),
    )


def variation_runtime_binding_issues(
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    runtime: Mapping[str, object],
) -> list[ValidationIssue]:
    """Variation 문서와 각 Candidate가 Project Pin 및 Registry Hash에 결속됐는지 검증한다."""
    expected = {
        "variation_engine_version": runtime.get("engine_version"),
        "variation_catalog_version": runtime.get("catalog_version"),
        "catalog_sha256": runtime.get("catalog_sha256"),
        "algorithm_sha256": runtime.get("algorithm_sha256"),
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

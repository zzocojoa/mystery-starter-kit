"""Variation Runtime 호환 범위, 구현 Hash와 Snapshot 불변성 검증."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from shutil import copytree

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation_registry import (
    resolve_variation_runtime,
    resolve_variation_runtime_for_channel,
)
from VALIDATORS.version_immutability import registered_version_mutations

ROOT = Path(__file__).resolve().parents[1]


def isolated_runtime_root(tmp_path: Path) -> Path:
    """Registry와 Version 파일을 독립 수정할 Test Repository를 만든다."""
    repository_root = tmp_path / "repository"
    copytree(
        ROOT / "STANDARD" / "variation_engines", repository_root / "STANDARD" / "variation_engines"
    )
    copytree(
        ROOT / "STANDARD" / "variation_catalogs",
        repository_root / "STANDARD" / "variation_catalogs",
    )
    copytree(
        ROOT / "VALIDATORS" / "variation_engines",
        repository_root / "VALIDATORS" / "variation_engines",
    )
    (repository_root / "STANDARD").mkdir(parents=True, exist_ok=True)
    (repository_root / "STANDARD" / "variation_catalog.json").write_bytes(
        (ROOT / "STANDARD" / "variation_catalog.json").read_bytes()
    )
    return repository_root


def pinned_config(
    channel_version: str,
    engine_version: str,
    catalog_version: str,
) -> dict[str, object]:
    """명시적 Runtime Pin을 가진 Production Config를 반환한다."""
    return {
        "channel_content_version": channel_version,
        "variation_engine_version": engine_version,
        "variation_catalog_version": catalog_version,
    }


def crime_channel(content_version: str) -> dict[str, object]:
    """v2 Crime Psychology Capability가 활성화된 Channel을 반환한다."""
    return {
        "content_version": content_version,
        "capabilities": {"CRIME_PSYCHOLOGY_POLICY": {"enabled": True}},
    }


def channel_without_crime_policy(content_version: str) -> dict[str, object]:
    """필수 Crime Psychology Capability가 없는 Channel을 반환한다."""
    return {"content_version": content_version, "capabilities": {}}


def add_engine_version(
    repository_root: Path,
    source_version: str,
    target_version: str,
) -> None:
    """동일 구현을 사용하는 호환성 Test용 Engine Version을 Registry에 추가한다."""
    source_path = repository_root / "STANDARD" / "variation_engines" / f"{source_version}.json"
    target_path = repository_root / "STANDARD" / "variation_engines" / f"{target_version}.json"
    specification = load_json_object(source_path)
    specification["variation_engine_version"] = target_version
    write_json_object(target_path, specification)
    registry_path = repository_root / "STANDARD" / "variation_engines" / "registry.json"
    registry = load_json_object(registry_path)
    entries = registry["engines"]
    assert isinstance(entries, dict)
    source_entry = entries[source_version]
    assert isinstance(source_entry, dict)
    target_entry = deepcopy(source_entry)
    target_entry["path"] = f"STANDARD/variation_engines/{target_version}.json"
    target_entry["algorithm_sha256"] = sha256(target_path.read_bytes()).hexdigest()
    entries[target_version] = target_entry
    write_json_object(registry_path, registry)


def add_catalog_version(
    repository_root: Path,
    source_version: str,
    target_version: str,
) -> None:
    """내용이 같은 호환성 Test용 Catalog Snapshot을 Registry에 추가한다."""
    source_path = repository_root / "STANDARD" / "variation_catalogs" / f"{source_version}.json"
    target_path = repository_root / "STANDARD" / "variation_catalogs" / f"{target_version}.json"
    target_path.write_bytes(source_path.read_bytes())
    registry_path = repository_root / "STANDARD" / "variation_catalogs" / "registry.json"
    registry = load_json_object(registry_path)
    entries = registry["catalogs"]
    assert isinstance(entries, dict)
    source_entry = entries[source_version]
    assert isinstance(source_entry, dict)
    target_entry = deepcopy(source_entry)
    target_entry["path"] = f"STANDARD/variation_catalogs/{target_version}.json"
    target_entry["catalog_sha256"] = sha256(target_path.read_bytes()).hexdigest()
    entries[target_version] = target_entry
    write_json_object(registry_path, registry)


def test_variation_registries_and_engine_specifications_pass_schema() -> None:
    """Version Registry와 모든 Engine Specification이 자체 Schema를 통과한다."""
    pairs = (
        (
            ROOT / "STANDARD" / "variation_engines" / "registry.json",
            ROOT / "STANDARD" / "schemas" / "variation_engine_registry.schema.json",
        ),
        (
            ROOT / "STANDARD" / "variation_catalogs" / "registry.json",
            ROOT / "STANDARD" / "schemas" / "variation_catalog_registry.schema.json",
        ),
    )
    for document_path, schema_path in pairs:
        assert (
            collect_schema_errors(
                load_json_object(document_path),
                load_json_object(schema_path),
                str(document_path),
            )
            == []
        )
    engine_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "variation_engine_specification.schema.json"
    )
    for version in ("1.0.0", "2.0.0"):
        path = ROOT / "STANDARD" / "variation_engines" / f"{version}.json"
        assert collect_schema_errors(load_json_object(path), engine_schema, str(path)) == []


def test_project_pins_resolve_exact_engine_catalog_and_hashes() -> None:
    """Project Pin은 정확한 Engine·Catalog·실행 구현 Hash를 해석한다."""
    runtime = resolve_variation_runtime(
        ROOT,
        {
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "1.1.0",
            "variation_engine_version": "1.0.0",
            "variation_catalog_version": "1.0.0",
        },
    )
    assert runtime["engine_version"] == "1.0.0"
    assert runtime["catalog_version"] == "1.0.0"
    assert len(runtime["algorithm_sha256"]) == 64
    assert len(runtime["implementation_sha256"]) == 64
    assert len(runtime["catalog_sha256"]) == 64


def test_channel_2_0_accepts_engine_2_1_and_catalog_2_0(tmp_path: Path) -> None:
    """Channel과 Engine의 Minor Version이 달라도 호환 범위 안이면 통과한다."""
    repository_root = isolated_runtime_root(tmp_path)
    add_engine_version(repository_root, "2.0.0", "2.1.0")

    runtime = resolve_variation_runtime_for_channel(
        repository_root,
        pinned_config("2.0.0", "2.1.0", "2.0.0"),
        crime_channel("2.0.0"),
    )

    assert runtime["engine_version"] == "2.1.0"
    assert runtime["catalog_version"] == "2.0.0"


def test_channel_2_1_accepts_engine_2_0_and_catalog_2_0_1(tmp_path: Path) -> None:
    """Channel Minor와 Catalog Patch가 달라도 교집합 범위 안이면 통과한다."""
    repository_root = isolated_runtime_root(tmp_path)
    add_catalog_version(repository_root, "2.0.0", "2.0.1")

    runtime = resolve_variation_runtime_for_channel(
        repository_root,
        pinned_config("2.1.0", "2.0.0", "2.0.1"),
        crime_channel("2.1.0"),
    )

    assert runtime["engine_version"] == "2.0.0"
    assert runtime["catalog_version"] == "2.0.1"


def test_channel_outside_engine_range_fails(tmp_path: Path) -> None:
    """Engine 지원 범위 밖 Channel은 명시적 오류로 실패한다."""
    repository_root = isolated_runtime_root(tmp_path)

    with pytest.raises(
        ConfigurationError,
        match="VARIATION_ENGINE_CHANNEL_INCOMPATIBLE",
    ):
        resolve_variation_runtime_for_channel(
            repository_root,
            pinned_config("3.0.0", "2.0.0", "2.0.0"),
            crime_channel("3.0.0"),
        )


def test_required_capability_missing_fails(tmp_path: Path) -> None:
    """Engine 또는 Catalog가 요구한 Capability 누락은 실패한다."""
    repository_root = isolated_runtime_root(tmp_path)

    with pytest.raises(
        ConfigurationError,
        match="VARIATION_REQUIRED_CAPABILITY_MISSING",
    ):
        resolve_variation_runtime_for_channel(
            repository_root,
            pinned_config("2.0.0", "2.0.0", "2.0.0"),
            channel_without_crime_policy("2.0.0"),
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        "VALIDATORS/variation_engines/v2_0_0.py",
        "VALIDATORS/variation_engines/common.py",
    ],
)
def test_implementation_byte_change_fails_before_entrypoint_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
) -> None:
    """Version 구현 또는 공유 Helper 변경은 Import 전에 Hash 실패한다."""
    repository_root = isolated_runtime_root(tmp_path)
    path = repository_root / relative_path
    path.write_bytes(path.read_bytes() + b"\n")
    imported: list[str] = []

    def record_import(module_name: str) -> object:
        imported.append(module_name)
        raise AssertionError("Hash 실패 전에 Entrypoint를 Import하면 안 됩니다.")

    monkeypatch.setattr("VALIDATORS.variation_registry.import_module", record_import)
    with pytest.raises(
        ConfigurationError,
        match="VARIATION_IMPLEMENTATION_HASH_MISMATCH",
    ):
        resolve_variation_runtime_for_channel(
            repository_root,
            pinned_config("2.0.0", "2.0.0", "2.0.0"),
            crime_channel("2.0.0"),
        )
    assert imported == []


def test_missing_entrypoint_fails(tmp_path: Path) -> None:
    """Hash가 맞아도 등록 Entrypoint 함수가 없으면 실패한다."""
    repository_root = isolated_runtime_root(tmp_path)
    registry_path = repository_root / "STANDARD" / "variation_engines" / "registry.json"
    registry = load_json_object(registry_path)
    engines = registry["engines"]
    assert isinstance(engines, dict)
    engine = engines["2.0.0"]
    assert isinstance(engine, dict)
    implementation = engine["implementation"]
    assert isinstance(implementation, dict)
    implementation["entrypoint"] = "VALIDATORS.variation_engines.v2_0_0:missing"
    write_json_object(registry_path, registry)

    with pytest.raises(ConfigurationError, match="VARIATION_ENTRYPOINT_INVALID"):
        resolve_variation_runtime_for_channel(
            repository_root,
            pinned_config("2.0.0", "2.0.0", "2.0.0"),
            crime_channel("2.0.0"),
        )


def test_runtime_reads_only_versioned_catalog_snapshot(tmp_path: Path) -> None:
    """루트 Authoring Catalog 변경은 등록된 2.0.0 Runtime에 영향을 주지 않는다."""
    repository_root = isolated_runtime_root(tmp_path)
    root_catalog = repository_root / "STANDARD" / "variation_catalog.json"
    root_catalog.write_text("{}\n", encoding="utf-8")

    runtime = resolve_variation_runtime_for_channel(
        repository_root,
        pinned_config("2.0.0", "2.0.0", "2.0.0"),
        crime_channel("2.0.0"),
    )

    assert runtime["catalog_path"] == "STANDARD/variation_catalogs/2.0.0.json"
    assert runtime["catalog"]["schema_family"] == "variation-catalog"
    registry = load_json_object(
        repository_root / "STANDARD" / "variation_catalogs" / "registry.json"
    )
    assert registry["root_catalog"] == {
        "path": "STANDARD/variation_catalog.json",
        "role": "AUTHORING_SOURCE",
    }


def test_registered_snapshot_hash_change_fails(tmp_path: Path) -> None:
    """등록된 2.0.0 Snapshot 한 Byte 변경은 Runtime에서 실패한다."""
    repository_root = isolated_runtime_root(tmp_path)
    snapshot = repository_root / "STANDARD" / "variation_catalogs" / "2.0.0.json"
    snapshot.write_bytes(snapshot.read_bytes() + b"\n")

    with pytest.raises(ConfigurationError, match="CATALOG_SNAPSHOT_HASH_MISMATCH"):
        resolve_variation_runtime_for_channel(
            repository_root,
            pinned_config("2.0.0", "2.0.0", "2.0.0"),
            crime_channel("2.0.0"),
        )


def test_registered_version_immutability_rejects_mutation_and_allows_new_version(
    tmp_path: Path,
) -> None:
    """Base 등록 파일 수정은 실패하고 새 Version 추가는 허용한다."""
    repository_root = isolated_runtime_root(tmp_path)
    base_engine_registry = load_json_object(
        repository_root / "STANDARD" / "variation_engines" / "registry.json"
    )
    base_catalog_registry = load_json_object(
        repository_root / "STANDARD" / "variation_catalogs" / "registry.json"
    )
    base_paths = {
        "STANDARD/variation_engines/1.0.0.json",
        "STANDARD/variation_engines/2.0.0.json",
        "VALIDATORS/variation_engines/common.py",
        "VALIDATORS/variation_engines/v1_0_0.py",
        "VALIDATORS/variation_engines/v2_0_0.py",
        "STANDARD/variation_catalogs/1.0.0.json",
        "STANDARD/variation_catalogs/2.0.0.json",
    }
    base_files = {
        relative_path: (repository_root / relative_path).read_bytes()
        for relative_path in base_paths
    }
    snapshot = repository_root / "STANDARD" / "variation_catalogs" / "2.0.0.json"
    snapshot.write_bytes(snapshot.read_bytes() + b"\n")
    assert registered_version_mutations(
        repository_root,
        base_files,
        base_engine_registry,
        base_catalog_registry,
    ) == ["STANDARD/variation_catalogs/2.0.0.json"]

    snapshot.write_bytes(base_files["STANDARD/variation_catalogs/2.0.0.json"])
    add_catalog_version(repository_root, "2.0.0", "2.0.1")
    assert (
        registered_version_mutations(
            repository_root,
            base_files,
            base_engine_registry,
            base_catalog_registry,
        )
        == []
    )


def test_registered_version_immutability_rejects_registry_entry_change(
    tmp_path: Path,
) -> None:
    """등록된 Version의 경로·Hash Entry 자체도 같은 번호로 변경할 수 없다."""
    repository_root = isolated_runtime_root(tmp_path)
    engine_registry_path = repository_root / "STANDARD/variation_engines/registry.json"
    base_engine_registry = load_json_object(engine_registry_path)
    base_catalog_registry = load_json_object(
        repository_root / "STANDARD/variation_catalogs/registry.json"
    )
    base_files = {
        relative_path: (repository_root / relative_path).read_bytes()
        for relative_path in {
            "STANDARD/variation_engines/1.0.0.json",
            "STANDARD/variation_engines/2.0.0.json",
            "VALIDATORS/variation_engines/common.py",
            "VALIDATORS/variation_engines/v1_0_0.py",
            "VALIDATORS/variation_engines/v2_0_0.py",
            "STANDARD/variation_catalogs/1.0.0.json",
            "STANDARD/variation_catalogs/2.0.0.json",
        }
    }
    current_engine_registry = deepcopy(base_engine_registry)
    engines = current_engine_registry["engines"]
    assert isinstance(engines, dict)
    engine_entry = engines["2.0.0"]
    assert isinstance(engine_entry, dict)
    engine_entry["algorithm_sha256"] = "0" * 64
    write_json_object(engine_registry_path, current_engine_registry)

    assert registered_version_mutations(
        repository_root,
        base_files,
        base_engine_registry,
        base_catalog_registry,
    ) == ["STANDARD/variation_engines/registry.json#engines.2.0.0"]

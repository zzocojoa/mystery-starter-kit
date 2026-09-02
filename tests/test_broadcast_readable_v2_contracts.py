"""Broadcast Readable v2 Version 계약과 v1 불변 경계를 검증한다."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from RUNTIME.broadcast_readable_renderer import render_broadcast_readable_script
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.output_profiles import resolve_broadcast_readable_output_profile
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.version_immutability import output_profile_version_mutations

ROOT = Path(__file__).resolve().parents[1]
PILOT_ROOT = ROOT / "PROJECTS/PRJ-006"
REGISTRY_RELATIVE_PATH = "CHANNELS/mystery_main/output_profiles/registry.json"
REGISTRY_PATH = ROOT / REGISTRY_RELATIVE_PATH
REGISTRY_SCHEMA_RELATIVE_PATH = (
    "STANDARD/schemas/reenactment_output_profile_registry.schema.json"
)
REGISTRY_SCHEMA_PATH = ROOT / REGISTRY_SCHEMA_RELATIVE_PATH
V1_PROFILE_RELATIVE_PATH = (
    "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/1.0.0.json"
)
V1_PROFILE_PATH = ROOT / V1_PROFILE_RELATIVE_PATH
V1_PROFILE_SHA256 = "7c8b59c96af7a65f59faf7f4ed68d2ad7ffba10ef59fbbbb3189dd1445943667"
V1_SCHEMA_RELATIVE_PATH = "STANDARD/schemas/broadcast_readable_output_profile.schema.json"
V1_SCHEMA_PATH = ROOT / V1_SCHEMA_RELATIVE_PATH
V1_OUTPUT_SHA256 = "a823e34f69132c857d6eea6a93b9842dd5f40add50edfe6409b1a2f6c4fbe2fa"
V2_PROFILE_RELATIVE_PATH = (
    "CHANNELS/mystery_main/output_profiles/broadcast-readable-script/2.0.0.json"
)
V2_PROFILE_PATH = ROOT / V2_PROFILE_RELATIVE_PATH
V2_SCHEMA_RELATIVE_PATH = (
    "STANDARD/schemas/broadcast_readable_output_profile_2_0.schema.json"
)
V2_SCHEMA_PATH = ROOT / V2_SCHEMA_RELATIVE_PATH
REENACTMENT_PROFILE_RELATIVE_PATH = (
    "CHANNELS/mystery_main/output_profiles/reenactment-character-script/1.0.0.json"
)


def v2_production_config() -> dict[str, object]:
    """v2 Profile을 직접 Pin한 기존 형식의 Config Fixture를 반환한다."""
    config = load_json_object(PILOT_ROOT / "00_PROJECT/production_config.json")
    config["broadcast_readable_output_profile_version"] = "2.0.0"
    return config


def copy_file(source: Path, destination: Path) -> None:
    """테스트 Repository에 한 파일을 동일 Bytes로 복사한다."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def copy_profile_bundle(repository_root: Path) -> None:
    """Resolver와 불변성 검사에 필요한 Profile Bundle을 복사한다."""
    for relative_path in (
        REGISTRY_RELATIVE_PATH,
        REGISTRY_SCHEMA_RELATIVE_PATH,
        V1_PROFILE_RELATIVE_PATH,
        V1_SCHEMA_RELATIVE_PATH,
        V2_PROFILE_RELATIVE_PATH,
        V2_SCHEMA_RELATIVE_PATH,
        REENACTMENT_PROFILE_RELATIVE_PATH,
    ):
        copy_file(ROOT / relative_path, repository_root / relative_path)


def profile_versions(registry: dict[str, object]) -> dict[str, object]:
    """Readable Profile의 Version Entry 사전을 엄격하게 반환한다."""
    profiles = registry["profiles"]
    assert isinstance(profiles, dict)
    profile = profiles["BROADCAST_READABLE_SCRIPT"]
    assert isinstance(profile, dict)
    versions = profile["versions"]
    assert isinstance(versions, dict)
    return versions


def render_v1_pilot() -> str:
    """PRJ-006 Canonical 입력과 v1 Profile로 기준 Readable을 재렌더한다."""
    config = load_json_object(PILOT_ROOT / "00_PROJECT/production_config.json")
    resolved = resolve_broadcast_readable_output_profile(ROOT, config)
    assert resolved is not None
    return render_broadcast_readable_script(
        load_json_object(PILOT_ROOT / "07_SCRIPT/screenplay_units.json"),
        load_json_object(PILOT_ROOT / "02_CHARACTER/characters.json"),
        load_json_object(PILOT_ROOT / "06_SCENE/panel_cast.json"),
        load_json_object(PILOT_ROOT / "06_SCENE/reaction_segments.json"),
        load_json_object(PILOT_ROOT / "06_SCENE/presentation_plan.json"),
        resolved["document"],
    )


def test_v1_profile_registry_entry_and_rendered_bytes_are_immutable() -> None:
    """v1 파일·Registry Entry·재렌더 Bytes를 고정 기준과 비교한다."""
    registry = load_json_object(REGISTRY_PATH)
    versions = profile_versions(registry)

    assert sha256(V1_PROFILE_PATH.read_bytes()).hexdigest() == V1_PROFILE_SHA256
    assert versions["1.0.0"] == {
        "path": V1_PROFILE_RELATIVE_PATH,
        "sha256": V1_PROFILE_SHA256,
    }
    assert sha256(render_v1_pilot().encode("utf-8")).hexdigest() == V1_OUTPUT_SHA256


def test_v1_and_v2_profiles_use_distinct_valid_schemas() -> None:
    """v1과 v2 Profile은 각 Version Schema에서 독립 검증된다."""
    v1_schema = load_json_object(V1_SCHEMA_PATH)
    v2_schema = load_json_object(V2_SCHEMA_PATH)
    Draft202012Validator.check_schema(v1_schema)
    Draft202012Validator.check_schema(v2_schema)

    assert collect_schema_errors(
        load_json_object(V1_PROFILE_PATH),
        v1_schema,
        str(V1_PROFILE_PATH),
    ) == []
    assert collect_schema_errors(
        load_json_object(V2_PROFILE_PATH),
        v2_schema,
        str(V2_PROFILE_PATH),
    ) == []
    assert collect_schema_errors(
        load_json_object(V2_PROFILE_PATH),
        v1_schema,
        str(V2_PROFILE_PATH),
    )


def test_v2_profile_resolves_through_version_schema_routing() -> None:
    """Registry의 v2 Entry가 전용 Schema 경로와 Profile을 해석한다."""
    resolved = resolve_broadcast_readable_output_profile(ROOT, v2_production_config())

    assert resolved is not None
    assert resolved["profile_version"] == "2.0.0"
    assert resolved["relative_path"] == V2_PROFILE_RELATIVE_PATH
    assert resolved["schema_relative_path"] == V2_SCHEMA_RELATIVE_PATH
    assert resolved["sha256"] == sha256(V2_PROFILE_PATH.read_bytes()).hexdigest()


def test_v2_missing_and_unregistered_pins_fail_without_fallback() -> None:
    """v2 Pin 누락·미등록 Version은 v1으로 대체되지 않는다."""
    missing = v2_production_config()
    missing.pop("broadcast_readable_output_profile_version")
    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_OUTPUT_PROFILE_PIN_MISSING",
    ):
        resolve_broadcast_readable_output_profile(ROOT, missing)

    unregistered = v2_production_config()
    unregistered["broadcast_readable_output_profile_version"] = "2.0.1"
    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_OUTPUT_PROFILE_PIN_INVALID",
    ):
        resolve_broadcast_readable_output_profile(ROOT, unregistered)


def test_v2_profile_hash_mismatch_fails(tmp_path: Path) -> None:
    """등록 v2 Profile의 한 Byte 변경도 Registry Hash에서 실패한다."""
    copy_profile_bundle(tmp_path)
    changed_path = tmp_path / V2_PROFILE_RELATIVE_PATH
    changed_path.write_bytes(changed_path.read_bytes() + b"\n")

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_OUTPUT_PROFILE_HASH_MISMATCH",
    ):
        resolve_broadcast_readable_output_profile(tmp_path, v2_production_config())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "../broadcast-readable-script/2.0.0.json"),
        ("schema_path", "../broadcast_readable_output_profile_2_0.schema.json"),
    ],
)
def test_v2_registry_path_traversal_fails(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    """v2 Profile 또는 Schema 경로가 Repository 경계를 벗어날 수 없다."""
    copy_profile_bundle(tmp_path)
    registry_path = tmp_path / REGISTRY_RELATIVE_PATH
    registry = load_json_object(registry_path)
    versions = profile_versions(registry)
    v2_entry = versions["2.0.0"]
    assert isinstance(v2_entry, dict)
    v2_entry[field] = value
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_OUTPUT_PROFILE_REGISTRY_INVALID",
    ):
        resolve_broadcast_readable_output_profile(tmp_path, v2_production_config())


def test_v2_missing_registered_schema_fails_explicitly(tmp_path: Path) -> None:
    """등록 Schema 파일이 없으면 v1 Schema로 대체하지 않는다."""
    copy_profile_bundle(tmp_path)
    (tmp_path / V2_SCHEMA_RELATIVE_PATH).unlink()

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_OUTPUT_PROFILE_SCHEMA_UNSUPPORTED",
    ):
        resolve_broadcast_readable_output_profile(tmp_path, v2_production_config())


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0"])
def test_each_registered_readable_version_mutation_is_detected(
    tmp_path: Path,
    version: str,
) -> None:
    """v1과 v2 등록 파일을 각각 독립 Mutation으로 보호한다."""
    copy_profile_bundle(tmp_path)
    registry = load_json_object(REGISTRY_PATH)
    base_files = {
        relative_path: (ROOT / relative_path).read_bytes()
        for relative_path in (
            REENACTMENT_PROFILE_RELATIVE_PATH,
            V1_PROFILE_RELATIVE_PATH,
            V2_PROFILE_RELATIVE_PATH,
        )
    }
    changed_relative_path = (
        V1_PROFILE_RELATIVE_PATH if version == "1.0.0" else V2_PROFILE_RELATIVE_PATH
    )
    changed_path = tmp_path / changed_relative_path
    changed_path.write_bytes(changed_path.read_bytes() + b"\n")

    assert output_profile_version_mutations(
        tmp_path,
        base_files,
        registry,
    ) == [changed_relative_path]


def test_v2_registry_entry_mutation_is_detected(tmp_path: Path) -> None:
    """등록된 v2 Entry의 Path·Hash·Schema 변경도 불변성 위반이다."""
    copy_profile_bundle(tmp_path)
    base_registry = load_json_object(REGISTRY_PATH)
    current_registry = deepcopy(base_registry)
    versions = profile_versions(current_registry)
    v2_entry = versions["2.0.0"]
    assert isinstance(v2_entry, dict)
    v2_entry["schema_path"] = V1_SCHEMA_RELATIVE_PATH
    (tmp_path / REGISTRY_RELATIVE_PATH).write_text(
        json.dumps(current_registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    base_files = {
        relative_path: (ROOT / relative_path).read_bytes()
        for relative_path in (
            REENACTMENT_PROFILE_RELATIVE_PATH,
            V1_PROFILE_RELATIVE_PATH,
            V2_PROFILE_RELATIVE_PATH,
        )
    }

    assert output_profile_version_mutations(
        tmp_path,
        base_files,
        base_registry,
    ) == [
        "CHANNELS/mystery_main/output_profiles/registry.json#profiles."
        "BROADCAST_READABLE_SCRIPT@2.0.0"
    ]

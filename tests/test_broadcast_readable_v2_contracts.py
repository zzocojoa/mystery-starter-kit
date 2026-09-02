"""Broadcast Readable v2 Version 계약과 v1 불변 경계를 검증한다."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from RUNTIME.broadcast_readable_renderer import render_broadcast_readable_script
from RUNTIME.contracts import load_artifact_contracts, load_task_catalog
from RUNTIME.planner import task_condition_matches
from VALIDATORS.dependency import (
    artifact_hash,
    artifact_required_for_project,
    build_initial_project_state,
    dependency_artifacts,
    invalidate_artifact_dependents,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.output_profiles import (
    broadcast_readable_activation_mode,
    resolve_active_broadcast_readable_output_profile,
    resolve_broadcast_readable_output_profile,
)
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
CONFIG_SCHEMA_PATH = ROOT / "STANDARD/schemas/broadcast_readable_config.schema.json"
PRODUCTION_CONFIG_SCHEMA_PATH = ROOT / "STANDARD/schemas/production_config.schema.json"
TEMPLATE_CONFIG_PATH = ROOT / "TEMPLATES/PROJECT/00_PROJECT/production_config.json"
DEPENDENCY_GRAPH_PATH = ROOT / "STANDARD/dependency_graph.json"


def readable_config(enabled: bool) -> dict[str, object]:
    """활성 여부에 맞는 v2 Readable Config Fixture를 반환한다."""
    document: dict[str, object] = {
        "$schema": "../../../STANDARD/schemas/broadcast_readable_config.schema.json",
        "schema_family": "broadcast-readable-config",
        "schema_version": "1.0.0",
        "project_id": "PRJ-006",
        "enabled": enabled,
    }
    if enabled:
        document["profile_id"] = "BROADCAST_READABLE_SCRIPT"
        document["profile_version"] = "2.0.0"
    return document


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


def test_v2_config_schema_accepts_explicit_enable_and_disable() -> None:
    """별도 Config는 v2 Opt-in 또는 명시적 비활성만 표현한다."""
    schema = load_json_object(CONFIG_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)

    assert collect_schema_errors(readable_config(True), schema, "enabled") == []
    assert collect_schema_errors(readable_config(False), schema, "disabled") == []
    invalid = readable_config(True)
    invalid["profile_version"] = "1.0.0"
    assert collect_schema_errors(invalid, schema, "invalid version")


def test_activation_priority_supports_v2_v1_and_inactive_paths() -> None:
    """v2 Config가 우선하고 없을 때만 v1 Pin Pair를 사용한다."""
    v1_config = load_json_object(PILOT_ROOT / "00_PROJECT/production_config.json")
    no_pins = deepcopy(v1_config)
    no_pins.pop("broadcast_readable_output_profile_id")
    no_pins.pop("broadcast_readable_output_profile_version")

    assert broadcast_readable_activation_mode(no_pins, {}) == "DISABLED"
    assert broadcast_readable_activation_mode(v1_config, {}) == "V1_COMPATIBILITY"
    legacy_with_pins = deepcopy(v1_config)
    legacy_with_pins["script_source_mode"] = "LEGACY_MARKDOWN"
    assert broadcast_readable_activation_mode(legacy_with_pins, {}) == "DISABLED"
    assert broadcast_readable_activation_mode(
        v1_config,
        {"broadcast_readable_config": readable_config(True)},
    ) == "V2_CONFIG"
    assert broadcast_readable_activation_mode(
        v1_config,
        {"broadcast_readable_config": readable_config(False)},
    ) == "DISABLED"
    resolved = resolve_active_broadcast_readable_output_profile(
        ROOT,
        v1_config,
        {"broadcast_readable_config": readable_config(True)},
    )
    assert resolved is not None
    assert resolved["profile_version"] == "2.0.0"


def test_runtime_tasks_follow_v2_v1_and_inactive_activation() -> None:
    """GATE-08·09·13 Task가 동일한 명시적 활성화 규칙을 따른다."""
    tasks = load_task_catalog(ROOT)
    no_pins = load_json_object(TEMPLATE_CONFIG_PATH)
    v1_config = deepcopy(no_pins)
    v1_config["broadcast_readable_output_profile_id"] = (
        "BROADCAST_READABLE_SCRIPT"
    )
    v1_config["broadcast_readable_output_profile_version"] = "1.0.0"
    legacy_with_pins = deepcopy(v1_config)
    legacy_with_pins["script_source_mode"] = "LEGACY_MARKDOWN"
    enabled_artifacts = {"broadcast_readable_config": readable_config(True)}
    disabled_artifacts = {"broadcast_readable_config": readable_config(False)}

    for task_id in (
        "script.render_broadcast_readable",
        "continuity.validate_broadcast_readable",
        "production.package_broadcast_readable",
    ):
        condition = tasks[task_id]["condition"]
        assert not task_condition_matches(condition, no_pins, {}, {})
        assert task_condition_matches(condition, v1_config, {}, {})
        assert not task_condition_matches(condition, legacy_with_pins, {}, {})
        assert task_condition_matches(condition, no_pins, {}, enabled_artifacts)
        assert not task_condition_matches(condition, v1_config, {}, disabled_artifacts)


def test_config_artifact_uses_strict_atomic_contract() -> None:
    """별도 Config Artifact가 전용 Schema와 원자 Commit에 결속된다."""
    contract = load_artifact_contracts(ROOT)["broadcast_readable_config"]

    assert contract == {
        "media_type": "application/json",
        "schema": "STANDARD/schemas/broadcast_readable_config.schema.json",
        "validators": [],
        "commit_policy": "ATOMIC_ON_PASS",
        "max_bytes": 262144,
    }


def test_disabled_v2_config_overrides_existing_v1_pins() -> None:
    """명시적 비활성 Config는 기존 v1 Pin의 암묵적 실행을 차단한다."""
    production_config = load_json_object(
        PILOT_ROOT / "00_PROJECT/production_config.json"
    )

    assert resolve_active_broadcast_readable_output_profile(
        ROOT,
        production_config,
        {"broadcast_readable_config": readable_config(False)},
    ) is None


def test_partial_v1_pin_pair_fails_activation() -> None:
    """Config가 없을 때 불완전한 v1 Pair는 비활성으로 숨기지 않는다."""
    config = load_json_object(PILOT_ROOT / "00_PROJECT/production_config.json")
    config.pop("broadcast_readable_output_profile_version")

    with pytest.raises(
        ConfigurationError,
        match="BROADCAST_READABLE_PROFILE_PIN_MISSING",
    ):
        broadcast_readable_activation_mode(config, {})


def test_v2_config_project_mismatch_fails() -> None:
    """별도 Config가 다른 Project를 가리키면 해석을 중단한다."""
    production_config = load_json_object(
        PILOT_ROOT / "00_PROJECT/production_config.json"
    )
    config = readable_config(True)
    config["project_id"] = "PRJ-999"

    with pytest.raises(ConfigurationError, match="BROADCAST_READABLE_CONFIG_INVALID"):
        resolve_active_broadcast_readable_output_profile(
            ROOT,
            production_config,
            {"broadcast_readable_config": config},
        )


def test_new_screenplay_template_does_not_enable_readable_v2() -> None:
    """신규 Scaffold의 Screenplay mode는 Readable을 자동 활성화하지 않는다."""
    template = load_json_object(TEMPLATE_CONFIG_PATH)
    schema = load_json_object(PRODUCTION_CONFIG_SCHEMA_PATH)

    assert collect_schema_errors(template, schema, str(TEMPLATE_CONFIG_PATH)) == []
    assert "broadcast_readable_output_profile_id" not in template
    assert "broadcast_readable_output_profile_version" not in template
    assert broadcast_readable_activation_mode(template, {}) == "DISABLED"


def test_production_config_allows_only_atomic_optional_v1_pin_pair() -> None:
    """SCREENPLAY_UNITS에서 v1 Readable Pair는 선택 사항이지만 원자적이다."""
    schema = load_json_object(PRODUCTION_CONFIG_SCHEMA_PATH)
    without_pins = load_json_object(TEMPLATE_CONFIG_PATH)
    partial = deepcopy(without_pins)
    partial["broadcast_readable_output_profile_id"] = "BROADCAST_READABLE_SCRIPT"
    complete = deepcopy(partial)
    complete["broadcast_readable_output_profile_version"] = "1.0.0"

    assert collect_schema_errors(without_pins, schema, "without pins") == []
    assert collect_schema_errors(partial, schema, "partial pins")
    assert collect_schema_errors(complete, schema, "complete pins") == []


def test_readable_requiredness_uses_config_or_v1_compatibility_pair() -> None:
    """Readable Artifact 필수성은 별도 Config와 v1 fallback만 따른다."""
    graph = load_json_object(DEPENDENCY_GRAPH_PATH)
    definition = dependency_artifacts(graph)["broadcast_readable_script"]
    no_pins = load_json_object(TEMPLATE_CONFIG_PATH)
    v1_config = deepcopy(no_pins)
    v1_config["broadcast_readable_output_profile_id"] = "BROADCAST_READABLE_SCRIPT"
    v1_config["broadcast_readable_output_profile_version"] = "1.0.0"

    assert not artifact_required_for_project(definition, {}, no_pins, {})
    assert artifact_required_for_project(definition, {}, v1_config, {})
    assert artifact_required_for_project(
        definition,
        {},
        v1_config,
        {"broadcast_readable_config": readable_config(True)},
    )
    assert not artifact_required_for_project(
        definition,
        {},
        v1_config,
        {"broadcast_readable_config": readable_config(False)},
    )


def test_readable_config_change_invalidates_exact_readable_chain() -> None:
    """v2 Config 변경은 Readable 파생 체인과 Editorial만 DIRTY로 만든다."""
    graph = load_json_object(DEPENDENCY_GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-006", "2026-09-03T00:00:00Z")
    for artifact_state in state["artifacts"].values():
        artifact_state["status"] = "CLEAN"
        artifact_state["content_hash"] = "0" * 64
    changed = invalidate_artifact_dependents(
        graph,
        state,
        "broadcast_readable_config",
        artifact_hash(b"changed-readable-config"),
        "2026-09-03T00:01:00Z",
    )
    expected_dirty = {
        "broadcast_readable_config",
        "broadcast_readable_script",
        "broadcast_readable_report",
        "production_broadcast_readable_script",
        "production_manifest",
        "editorial_review",
    }

    assert {
        artifact_name
        for artifact_name, artifact_state in changed["artifacts"].items()
        if artifact_state["status"] == "DIRTY"
    } == expected_dirty
    for artifact_name in (
        "variation_candidates",
        "story_dna",
        "case_input",
        "characters",
        "relationships",
        "scene_cards",
        "screenplay_units",
        "drama_script",
        "narration_script",
        "panel_reaction_script",
        "draft_script",
        "final_script",
        "reenactment_character_script",
        "reenactment_export_report",
    ):
        assert changed["artifacts"][artifact_name]["status"] == "CLEAN"

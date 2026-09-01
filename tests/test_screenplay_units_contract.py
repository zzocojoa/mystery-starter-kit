"""Screenplay Units와 재연극 Output Profile 계약 검증."""

from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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
    resolve_reenactment_output_profile,
    script_source_mode,
)
from VALIDATORS.requirements import requirement_matches
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.screenplay_units import validate_screenplay_units
from VALIDATORS.version_immutability import output_profile_version_mutations

ROOT = Path(__file__).resolve().parents[1]
SCREENPLAY_SCHEMA_PATH = ROOT / "STANDARD/schemas/screenplay_units.schema.json"
PROFILE_PATH = (
    ROOT
    / "CHANNELS/mystery_main/output_profiles/reenactment-character-script/1.0.0.json"
)
PROFILE_SCHEMA_PATH = ROOT / "STANDARD/schemas/reenactment_output_profile.schema.json"
PROFILE_REGISTRY_PATH = ROOT / "CHANNELS/mystery_main/output_profiles/registry.json"
PROFILE_REGISTRY_SCHEMA_PATH = (
    ROOT / "STANDARD/schemas/reenactment_output_profile_registry.schema.json"
)
PRODUCTION_CONFIG_PATH = ROOT / "TEMPLATES/PROJECT/00_PROJECT/production_config.json"
PRODUCTION_CONFIG_SCHEMA_PATH = ROOT / "STANDARD/schemas/production_config.schema.json"
EXPORT_REPORT_SCHEMA_PATH = ROOT / "STANDARD/schemas/reenactment_export_report.schema.json"


def references() -> dict[str, object]:
    """모든 Unit에서 요구하는 빈 구조화 참조를 만든다."""
    return {
        "fact_ids": [],
        "clue_ids": [],
        "crime_event_ids": [],
        "harm_ids": [],
        "development_function_ids": [],
        "reveal_target_ids": [],
    }


def unit(
    unit_id: str,
    order: int,
    unit_type: str,
    speaker_id: str | None,
) -> dict[str, object]:
    """유형별 speaker 규칙을 지키는 Unit Fixture를 만든다."""
    document: dict[str, object] = {
        "unit_id": unit_id,
        "order": order,
        "type": unit_type,
        "text": f"{unit_type} 원문을 그대로 보존한다.",
        "segment_id": "SEG-001",
        "references": references(),
    }
    if speaker_id is not None:
        document["speaker_id"] = speaker_id
        document["delivery"] = {"instruction": "절제된 호흡", "pace": "NORMAL"}
    return document


def screenplay_document() -> dict[str, object]:
    """허용된 열한 Unit 유형을 모두 포함하는 정상 문서를 만든다."""
    unit_types = [
        "ACTION",
        "SOUND",
        "DIALOGUE",
        "NARRATION",
        "INNER_MONOLOGUE",
        "HALLUCINATION",
        "MESSAGE",
        "CHAT",
        "NOTE",
        "RECORDING",
        "SCREEN_TEXT",
    ]
    speaker_types = {
        "DIALOGUE",
        "NARRATION",
        "INNER_MONOLOGUE",
        "HALLUCINATION",
        "MESSAGE",
        "CHAT",
        "NOTE",
        "RECORDING",
    }
    units = [
        unit(
            f"UNIT-{index:03d}",
            index,
            unit_type,
            "CHAR-001" if unit_type in speaker_types else None,
        )
        for index, unit_type in enumerate(unit_types, start=1)
    ]
    context = {
        "location_description": "폐쇄된 기록 보관실",
        "time_description": "현재, 자정 직전",
        "previous_scene_id": None,
        "background_music_description": "낮고 불규칙한 현악음",
        "sound_cues": [
            {
                "sound_cue_id": "SOUND-001",
                "order": 1,
                "description": "형광등이 짧게 떨린다.",
            }
        ],
        "opening_character_state": "인물은 출구를 확인하고 있다.",
        "opening_emotional_state": "불안을 숨긴 경계 상태",
        "action_summary": "봉인된 기록을 확인한다.",
        "audience_information_gain": "기록 시각이 진술과 다르다는 사실",
    }
    reconstruction_context = deepcopy(context)
    reconstruction_context["previous_scene_id"] = "SCN-001"
    reconstruction_context["retrospective_meaning"] = "첫 장면의 소리가 경보였음이 드러난다."
    reconstruction_unit = unit("UNIT-012", 1, "ACTION", None)
    reconstruction_unit["segment_id"] = "SEG-002"
    return {
        "$schema": "../../../STANDARD/schemas/screenplay_units.schema.json",
        "schema_family": "screenplay-units",
        "schema_version": "1.0.0",
        "project_id": "PRJ-005",
        "title": "봉인된 시각",
        "source_truth_classification": "ORIGINAL_FICTION",
        "scenes": [
            {
                "scene_id": "SCN-001",
                "order": 1,
                "title": "닫힌 기록실",
                "time_layer": "COLD_OPEN",
                "location_id": "LOC-001",
                "segment_ids": ["SEG-001"],
                "context": context,
                "units": units,
            },
            {
                "scene_id": "SCN-002",
                "order": 2,
                "title": "같은 소리의 의미",
                "time_layer": "RECONSTRUCTION",
                "location_id": "LOC-001",
                "segment_ids": ["SEG-002"],
                "reconstruction_of_scene_id": "SCN-001",
                "context": reconstruction_context,
                "units": [reconstruction_unit],
            },
        ],
    }


def issue_codes(document: dict[str, object]) -> set[str]:
    """의미 Validator 오류 코드 집합을 반환한다."""
    return {issue["code"] for issue in validate_screenplay_units(document)}


def test_screenplay_schema_accepts_every_unit_type() -> None:
    """정상 Fixture는 열한 Unit 유형과 재구성 장면을 모두 보존한다."""
    document = screenplay_document()
    schema = load_json_object(SCREENPLAY_SCHEMA_PATH)

    assert collect_schema_errors(document, schema, "screenplay fixture") == []
    assert validate_screenplay_units(document) == []


def test_screenplay_rejects_invalid_speaker_type_combinations() -> None:
    """인물 발화는 speaker를 요구하고 지문은 speaker를 금지한다."""
    document = screenplay_document()
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    first_scene = scenes[0]
    assert isinstance(first_scene, dict)
    units = first_scene["units"]
    assert isinstance(units, list)
    action = units[0]
    dialogue = units[2]
    assert isinstance(action, dict)
    assert isinstance(dialogue, dict)
    action["speaker_id"] = "CHAR-001"
    dialogue.pop("speaker_id")

    schema_errors = collect_schema_errors(
        document,
        load_json_object(SCREENPLAY_SCHEMA_PATH),
        "invalid speaker fixture",
    )

    assert schema_errors
    assert {
        "SCREENPLAY_SPEAKER_PROHIBITED",
        "SCREENPLAY_SPEAKER_REQUIRED",
    }.issubset(issue_codes(document))


def test_screenplay_rejects_duplicate_unit_id_and_order() -> None:
    """Unit ID와 배열 내 order 중복은 결정론적 출력 계약을 위반한다."""
    document = screenplay_document()
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    first_scene = scenes[0]
    assert isinstance(first_scene, dict)
    units = first_scene["units"]
    assert isinstance(units, list)
    first_unit = units[0]
    second_unit = units[1]
    assert isinstance(first_unit, dict)
    assert isinstance(second_unit, dict)
    second_unit["unit_id"] = first_unit["unit_id"]
    second_unit["order"] = first_unit["order"]

    assert {
        "SCREENPLAY_UNIT_ID_DUPLICATED",
        "REENACTMENT_UNIT_ORDER_INVALID",
    }.issubset(issue_codes(document))


def test_screenplay_rejects_future_reconstruction_reference() -> None:
    """재구성 장면은 자신이나 미래 장면을 원본으로 사용할 수 없다."""
    document = screenplay_document()
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    reconstruction = scenes[1]
    assert isinstance(reconstruction, dict)
    reconstruction["reconstruction_of_scene_id"] = "SCN-002"

    assert "RECONSTRUCTION_REFERENCE_INVALID" in issue_codes(document)


def test_screenplay_v11_requires_exact_binding_for_repeated_reconstruction_unit() -> None:
    """재구성에서 반복한 Unit은 원본 Unit과 exact text/type 결속을 보존해야 한다."""
    document = screenplay_document()
    document["schema_version"] = "1.1.0"
    scenes = document["scenes"]
    assert isinstance(scenes, list)
    reconstruction = scenes[1]
    assert isinstance(reconstruction, dict)
    reconstruction["reconstruction_bindings"] = [
        {
            "source_unit_id": "UNIT-001",
            "repeated_unit_id": "UNIT-012",
            "preservation": "EXACT_TEXT",
        }
    ]

    assert collect_schema_errors(
        document,
        load_json_object(SCREENPLAY_SCHEMA_PATH),
        "screenplay 1.1 fixture",
    ) == []
    assert validate_screenplay_units(document) == []

    units = reconstruction["units"]
    assert isinstance(units, list)
    repeated = units[0]
    assert isinstance(repeated, dict)
    repeated["text"] = "재구성에서 임의로 바꾼 문장"

    assert "RECONSTRUCTION_REPETITION_MISMATCH" in issue_codes(document)


def test_output_profile_and_registry_are_schema_valid_and_resolvable() -> None:
    """등록 Profile은 Pin, Schema와 File Hash가 모두 일치해야 한다."""
    assert collect_schema_errors(
        load_json_object(PROFILE_PATH),
        load_json_object(PROFILE_SCHEMA_PATH),
        str(PROFILE_PATH),
    ) == []
    assert collect_schema_errors(
        load_json_object(PROFILE_REGISTRY_PATH),
        load_json_object(PROFILE_REGISTRY_SCHEMA_PATH),
        str(PROFILE_REGISTRY_PATH),
    ) == []
    config = load_json_object(PRODUCTION_CONFIG_PATH)
    config.update(
        {
            "script_source_mode": "SCREENPLAY_UNITS",
            "reenactment_output_profile_id": "REENACTMENT_CHARACTER_SCRIPT",
            "reenactment_output_profile_version": "1.0.0",
        }
    )
    assert collect_schema_errors(
        config,
        load_json_object(PRODUCTION_CONFIG_SCHEMA_PATH),
        "screenplay production config",
    ) == []

    resolved = resolve_reenactment_output_profile(ROOT, config)

    assert resolved is not None
    assert resolved["profile_id"] == "REENACTMENT_CHARACTER_SCRIPT"
    assert resolved["profile_version"] == "1.0.0"
    assert len(resolved["sha256"]) == 64


def test_reenactment_export_report_schema_compiles() -> None:
    """향후 CORE Report Artifact가 사용할 JSON Schema는 Draft 2020-12로 유효하다."""
    Draft202012Validator.check_schema(load_json_object(EXPORT_REPORT_SCHEMA_PATH))


def test_registered_output_profile_version_is_immutable(tmp_path: Path) -> None:
    """등록된 Profile 파일은 같은 Version에서 내용을 바꿀 수 없다."""
    relative_profile_path = (
        "CHANNELS/mystery_main/output_profiles/reenactment-character-script/1.0.0.json"
    )
    temporary_registry_path = (
        tmp_path / "CHANNELS/mystery_main/output_profiles/registry.json"
    )
    temporary_profile_path = tmp_path / relative_profile_path
    temporary_registry_path.parent.mkdir(parents=True)
    temporary_profile_path.parent.mkdir(parents=True)
    temporary_registry_path.write_bytes(PROFILE_REGISTRY_PATH.read_bytes())
    original_profile = PROFILE_PATH.read_bytes()
    temporary_profile_path.write_bytes(original_profile + b"\n")

    mutations = output_profile_version_mutations(
        tmp_path,
        {relative_profile_path: original_profile},
        load_json_object(PROFILE_REGISTRY_PATH),
    )

    assert mutations == [relative_profile_path]


def test_invalid_output_profile_version_pin_fails_explicitly() -> None:
    """Registry에 없는 Profile Version Pin은 임의 fallback 없이 실패한다."""
    config = load_json_object(PRODUCTION_CONFIG_PATH)
    config.update(
        {
            "script_source_mode": "SCREENPLAY_UNITS",
            "reenactment_output_profile_id": "REENACTMENT_CHARACTER_SCRIPT",
            "reenactment_output_profile_version": "9.9.9",
        }
    )

    with pytest.raises(ConfigurationError, match="REENACTMENT_OUTPUT_PROFILE_PIN_INVALID"):
        resolve_reenactment_output_profile(ROOT, config)


def test_legacy_production_config_remains_valid_without_profile_pin() -> None:
    """기존 Production Config는 자동 Migration 없이 Legacy mode로 남는다."""
    config = load_json_object(PRODUCTION_CONFIG_PATH)
    schema = load_json_object(PRODUCTION_CONFIG_SCHEMA_PATH)

    assert collect_schema_errors(config, schema, str(PRODUCTION_CONFIG_PATH)) == []
    assert script_source_mode(config) == "LEGACY_MARKDOWN"
    assert resolve_reenactment_output_profile(ROOT, config) is None
    assert not requirement_matches(
        {"config_equals": ["script_source_mode", "SCREENPLAY_UNITS"]},
        config,
        {},
        {},
    )


def test_screenplay_mode_requires_both_output_profile_pins() -> None:
    """새 Source mode는 Profile ID와 Version을 함께 고정해야 한다."""
    config = load_json_object(PRODUCTION_CONFIG_PATH)
    config["script_source_mode"] = "SCREENPLAY_UNITS"

    errors = collect_schema_errors(
        config,
        load_json_object(PRODUCTION_CONFIG_SCHEMA_PATH),
        "screenplay production config",
    )

    assert errors
    assert {
        error["context"]["validator"]
        for error in errors
    } == {"required"}


def test_screenplay_artifacts_are_opt_in_and_invalidate_all_exports() -> None:
    """새 Artifact는 새 mode에서만 필수이며 Unit 변경은 모든 Export를 무효화한다."""
    graph = load_json_object(ROOT / "STANDARD/dependency_graph.json")
    definition = dependency_artifacts(graph)["screenplay_units"]
    legacy_config = load_json_object(PRODUCTION_CONFIG_PATH)
    screenplay_config = deepcopy(legacy_config)
    screenplay_config["script_source_mode"] = "SCREENPLAY_UNITS"
    channel: dict[str, object] = {"capabilities": {}}

    assert not artifact_required_for_project(
        definition,
        channel,
        legacy_config,
        {},
    )
    assert artifact_required_for_project(
        definition,
        channel,
        screenplay_config,
        {},
    )

    state = build_initial_project_state(graph, "PRJ-005", "2026-09-01T00:00:00Z")
    changed = invalidate_artifact_dependents(
        graph,
        state,
        "screenplay_units",
        artifact_hash(b"changed-screenplay-units"),
        "2026-09-01T00:01:00Z",
    )

    for artifact_name in (
        "final_script",
        "reenactment_character_script",
        "reenactment_export_report",
        "production_reenactment_character_script",
        "editorial_review",
    ):
        assert changed["artifacts"][artifact_name]["status"] == "DIRTY"

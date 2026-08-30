"""CORE Production Footprint와 최종 Production 대조 테스트."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.io import load_json_object
from VALIDATORS.production_footprint import (
    build_production_footprint,
    production_manifest_from_scene_cards,
    production_scene_marker,
    validate_final_production_footprint,
    validate_production_footprint,
)
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def production_inputs() -> dict[str, dict[str, object]]:
    """제작 규모가 제한 안에 있는 Scene 기반 입력을 만든다."""
    return {
        "project_constraints": {
            "project_id": "PRJ-970",
            "production_limits": {
                "max_locations": 2,
                "max_major_characters": 2,
                "max_production_complexity": "MEDIUM",
                "max_special_effect_level": "LOW",
                "allow_child_actor": False,
                "allow_moving_vehicle": False,
                "max_graphic_violence": "IMPLIED",
                "enforce_final_footprint": True,
            },
        },
        "characters": {
            "project_id": "PRJ-970",
            "characters": [
                {
                    "character_id": "CHAR-01",
                    "name": "주인공",
                    "role": "PROTAGONIST",
                    "production_role": "MAJOR",
                },
                {
                    "character_id": "CHAR-02",
                    "name": "용의자",
                    "role": "SUSPECT",
                    "production_role": "MAJOR",
                },
            ],
        },
        "actual_timeline": {
            "project_id": "PRJ-970",
            "events": [
                {"event_id": "EVT-01", "location_id": "LOC-01"},
                {"event_id": "EVT-02", "location_id": "LOC-02"},
            ],
        },
        "scene_cards": {
            "project_id": "PRJ-970",
            "scenes": [
                {
                    "scene_id": "SCN-01",
                    "order": 1,
                    "location_id": "LOC-01",
                    "cast_ids": ["CHAR-01"],
                    "child_actor_use": "NONE",
                    "vehicle_scene": "NONE",
                    "special_effect_level": "NONE",
                    "graphic_violence": "NONE",
                    "production_complexity": "LOW",
                },
                {
                    "scene_id": "SCN-02",
                    "order": 2,
                    "location_id": "LOC-02",
                    "cast_ids": ["CHAR-01", "CHAR-02"],
                    "child_actor_use": "NONE",
                    "vehicle_scene": "STATIC",
                    "special_effect_level": "LOW",
                    "graphic_violence": "IMPLIED",
                    "production_complexity": "MEDIUM",
                },
            ],
        },
        "variation_candidates": {
            "approved_candidate_id": "VAR-01",
            "candidates": [
                {
                    "candidate_id": "VAR-01",
                    "selection": {
                        "location_count": "LOCATIONS_5",
                        "major_character_count": "MAJOR_7",
                        "production_complexity": "HIGH",
                        "special_effect_level": "HIGH",
                        "child_actor_use": "PRIMARY",
                        "vehicle_scene": "MOVING",
                        "graphic_violence": "GRAPHIC",
                    },
                }
            ],
        },
    }


def build_current_footprint(inputs: dict[str, dict[str, object]]) -> dict[str, object]:
    """Test 입력에서 현재 Footprint를 계산한다."""
    return build_production_footprint(
        "PRJ-970",
        inputs["scene_cards"],
        inputs["characters"],
        inputs["actual_timeline"],
    )


def footprint_codes(
    inputs: dict[str, dict[str, object]],
    footprint: dict[str, object] | None,
) -> set[str]:
    """GATE-07 검증 오류 코드를 반환한다."""
    return {
        issue["code"]
        for issue in validate_production_footprint(
            inputs["project_constraints"],
            footprint,
            inputs["scene_cards"],
            inputs["characters"],
            inputs["actual_timeline"],
            inputs["variation_candidates"],
        )
    }


def test_core_production_footprint_is_schema_valid_and_passes_limits() -> None:
    """CORE 계산 Footprint는 Schema와 Project Limit을 모두 통과한다."""
    inputs = production_inputs()
    footprint = build_current_footprint(inputs)
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "production_footprint.schema.json"
    )
    assert collect_schema_errors(footprint, schema, "production_footprint") == []
    assert footprint_codes(inputs, footprint) == set()


def test_child_actor_addition_exceeds_constraint() -> None:
    """Scene에 아역을 추가하면 비허용 Project Limit에서 실패한다."""
    inputs = production_inputs()
    scenes = inputs["scene_cards"]["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    scene["child_actor_use"] = "SUPPORTING"
    assert "PRODUCTION_LIMIT_EXCEEDED" in footprint_codes(
        inputs,
        build_current_footprint(inputs),
    )


def test_moving_vehicle_addition_exceeds_constraint() -> None:
    """이동 차량 Scene은 비허용 Project Limit에서 실패한다."""
    inputs = production_inputs()
    scenes = inputs["scene_cards"]["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    scene["vehicle_scene"] = "MOVING"
    assert "PRODUCTION_LIMIT_EXCEEDED" in footprint_codes(
        inputs,
        build_current_footprint(inputs),
    )


def test_graphic_violence_increase_exceeds_constraint() -> None:
    """Graphic Violence 상승은 허용 Severity를 넘으면 실패한다."""
    inputs = production_inputs()
    scenes = inputs["scene_cards"]["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    scene["graphic_violence"] = "GRAPHIC"
    assert "PRODUCTION_LIMIT_EXCEEDED" in footprint_codes(
        inputs,
        build_current_footprint(inputs),
    )


def test_special_effect_increase_exceeds_constraint() -> None:
    """특수효과 수준 상승은 허용 Severity를 넘으면 실패한다."""
    inputs = production_inputs()
    scenes = inputs["scene_cards"]["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    scene["special_effect_level"] = "HIGH"
    assert "PRODUCTION_LIMIT_EXCEEDED" in footprint_codes(
        inputs,
        build_current_footprint(inputs),
    )


def test_location_count_exceeds_constraint() -> None:
    """고유 Scene Location 수가 Limit을 넘으면 실패한다."""
    inputs = production_inputs()
    scenes = inputs["scene_cards"]["scenes"]
    events = inputs["actual_timeline"]["events"]
    assert isinstance(scenes, list)
    assert isinstance(events, list)
    scenes.append(
        {
            "scene_id": "SCN-03",
            "order": 3,
            "location_id": "LOC-03",
            "cast_ids": ["CHAR-01"],
            "child_actor_use": "NONE",
            "vehicle_scene": "NONE",
            "special_effect_level": "NONE",
            "graphic_violence": "NONE",
            "production_complexity": "LOW",
        }
    )
    events.append({"event_id": "EVT-03", "location_id": "LOC-03"})
    assert "PRODUCTION_LIMIT_EXCEEDED" in footprint_codes(
        inputs,
        build_current_footprint(inputs),
    )


def test_shooting_script_unregistered_scene_fails() -> None:
    """Shooting Script에 Manifest 밖 Scene이 추가되면 실패한다."""
    inputs = production_inputs()
    footprint = build_current_footprint(inputs)
    manifest = production_manifest_from_scene_cards(
        "PRJ-970",
        footprint,
        inputs["scene_cards"],
        inputs["characters"],
        inputs["actual_timeline"],
    )
    manifest_scenes = manifest["scenes"]
    assert isinstance(manifest_scenes, list)
    script = "\n".join(
        production_scene_marker(scene)
        for scene in manifest_scenes
        if isinstance(scene, dict)
    )
    script += (
        "\n<!-- PRODUCTION_SCENE:SCN-99 LOCATION:LOC-99 CAST:CHAR-01 "
        "CHILD:NONE VEHICLE:NONE SFX:NONE VIOLENCE:NONE COMPLEXITY:LOW -->"
    )
    issues = validate_final_production_footprint(
        inputs["project_constraints"],
        footprint,
        manifest,
        inputs["scene_cards"],
        inputs["characters"],
        inputs["actual_timeline"],
        inputs["variation_candidates"],
        script,
    )
    assert "UNDECLARED_PRODUCTION_ELEMENT" in {issue["code"] for issue in issues}


def test_final_manifest_and_shooting_script_pass_with_non_ascii_location() -> None:
    """공백·한글 Location도 정규 Marker에서 손실 없이 최종 검증을 통과한다."""
    inputs = production_inputs()
    timeline_events = inputs["actual_timeline"]["events"]
    scenes = inputs["scene_cards"]["scenes"]
    assert isinstance(timeline_events, list)
    assert isinstance(scenes, list)
    timeline_event = timeline_events[0]
    scene = scenes[0]
    assert isinstance(timeline_event, dict)
    assert isinstance(scene, dict)
    timeline_event["location_id"] = "동네 상담실 CAST:위조 A"
    scene["location_id"] = "동네 상담실 CAST:위조 A"
    footprint = build_current_footprint(inputs)
    manifest = production_manifest_from_scene_cards(
        "PRJ-970",
        footprint,
        inputs["scene_cards"],
        inputs["characters"],
        inputs["actual_timeline"],
    )
    manifest_scenes = manifest["scenes"]
    assert isinstance(manifest_scenes, list)
    script = "\n".join(
        production_scene_marker(manifest_scene)
        for manifest_scene in manifest_scenes
        if isinstance(manifest_scene, dict)
    )
    assert validate_final_production_footprint(
        inputs["project_constraints"],
        footprint,
        manifest,
        inputs["scene_cards"],
        inputs["characters"],
        inputs["actual_timeline"],
        inputs["variation_candidates"],
        script,
    ) == []


def test_footprint_source_hash_stale_fails() -> None:
    """Scene Source가 바뀐 뒤 재계산하지 않은 Footprint는 실패한다."""
    inputs = production_inputs()
    footprint = build_current_footprint(inputs)
    changed = deepcopy(inputs)
    scenes = changed["scene_cards"]["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    scene["production_complexity"] = "MEDIUM"
    assert "PRODUCTION_FOOTPRINT_STALE" in footprint_codes(changed, footprint)


def test_legacy_v1_project_does_not_require_footprint() -> None:
    """명시적 활성화가 없는 Legacy v1.1 Project에는 Footprint를 소급 요구하지 않는다."""
    inputs = production_inputs()
    limits = inputs["project_constraints"]["production_limits"]
    assert isinstance(limits, dict)
    limits["enforce_final_footprint"] = False
    assert footprint_codes(inputs, None) == set()

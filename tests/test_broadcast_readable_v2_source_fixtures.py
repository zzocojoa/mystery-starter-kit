"""추상 기능군 R1·R2의 Original Fiction Source-style Fixture를 검증한다."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_broadcast_readable_v2_validation import (
    PilotFixture,
    build_report,
    byte_fragment,
    issue_codes,
    mapping_records,
    pilot_fixture,
    render_fixture,
    replace_mapped_fragment,
    replace_once,
)

from RUNTIME.screenplay_renderers import (
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
)
from VALIDATORS.io import load_json_object

ROOT = Path(__file__).resolve().parents[1]
FEATURE_FIXTURES_PATH = (
    ROOT
    / "tests/fixtures/broadcast_readable_v2/source_style_features.json"
)
FORBIDDEN_VISIBLE_TOKENS = (
    "SCN-",
    "SEG-",
    "UNIT-",
    "CHAR-",
    "PANEL-",
    "RSEG-",
    "FACT-",
    "CLUE-",
    "HARM-",
    "CDEV-",
    "REVEAL-",
    "<!--",
    "-->",
    "[청취 불명확]",
    "[화자 불명확]",
)
CANONICAL_SCHEMA_PATHS = {
    "screenplay_units": ROOT / "STANDARD/schemas/screenplay_units.schema.json",
    "relationships": ROOT / "STANDARD/schemas/relationships.schema.json",
    "panel_cast": ROOT / "STANDARD/schemas/panel_cast.schema.json",
    "reaction_segments": ROOT / "STANDARD/schemas/reaction_segments.schema.json",
    "presentation_plan": ROOT / "STANDARD/schemas/presentation_plan.schema.json",
}


def mapping_value(document: dict[str, object], field: str) -> dict[str, object]:
    """Fixture 필수 객체 필드를 반환한다."""
    value = document[field]
    assert isinstance(value, dict)
    return value


def mapping_list(document: dict[str, object], field: str) -> list[dict[str, object]]:
    """Fixture 필수 객체 배열을 반환한다."""
    value = document[field]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return [item for item in value if isinstance(item, dict)]


def string_list(document: dict[str, object], field: str) -> list[str]:
    """Fixture 필수 문자열 배열을 반환한다."""
    value = document[field]
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return [item for item in value if isinstance(item, str)]


def mapping_byte_start(mapping: dict[str, object]) -> int:
    """Report Mapping의 Byte 시작 위치를 정수로 반환한다."""
    value = mapping_value(mapping, "actual_byte_range")["byte_start"]
    assert isinstance(value, int)
    return value


def feature_spec(fixture_id: str) -> dict[str, object]:
    """요청한 R1 또는 R2 기능 Fixture 명세를 반환한다."""
    document = load_json_object(FEATURE_FIXTURES_PATH)
    matches = [
        fixture
        for fixture in mapping_list(document, "fixtures")
        if fixture.get("fixture_id") == fixture_id
    ]
    assert len(matches) == 1
    return matches[0]


def replace_named_values(
    records: list[dict[str, object]],
    id_field: str,
    value_field: str,
    replacements: dict[str, object],
) -> None:
    """ID별 Fixture 표시값을 Canonical Record에 적용한다."""
    records_by_id = {str(record[id_field]): record for record in records}
    for record_id, replacement in replacements.items():
        assert isinstance(replacement, str)
        records_by_id[record_id][value_field] = replacement


def align_presentation_timing(fixture: PilotFixture) -> None:
    """재배치된 Segment와 Reaction의 누적 시간을 함께 정합화한다."""
    reactions = {
        str(reaction["reaction_segment_id"]): reaction
        for reaction in mapping_list(
            fixture["reaction_segments"],
            "reaction_segments",
        )
    }
    cursor = 0
    for segment in mapping_list(fixture["presentation_plan"], "segments"):
        duration = segment["duration_sec"]
        assert isinstance(duration, int)
        segment["start_sec"] = cursor
        reaction_id = segment.get("reaction_segment_id")
        if isinstance(reaction_id, str):
            reaction = reactions[reaction_id]
            reaction["start_sec"] = cursor
            reaction["duration_sec"] = duration
            reaction["after_scene_id"] = segment["scene_id"]
        cursor += duration


def align_reconstruction_units(fixture: PilotFixture) -> None:
    """재구성 반복 Unit의 가시 정체성을 원본 Unit과 일치시킨다."""
    scenes = mapping_list(fixture["screenplay_units"], "scenes")
    scenes_by_id = {str(scene["scene_id"]): scene for scene in scenes}
    visible_fields = ("type", "text", "speaker_id", "delivery")
    for scene in scenes:
        source_scene_id = scene.get("reconstruction_of_scene_id")
        if not isinstance(source_scene_id, str):
            continue
        source_units = {
            str(unit["unit_id"]): unit
            for unit in mapping_list(scenes_by_id[source_scene_id], "units")
        }
        repeated_units = {
            str(unit["unit_id"]): unit
            for unit in mapping_list(scene, "units")
        }
        raw_bindings = scene.get("reconstruction_bindings")
        if raw_bindings is None:
            continue
        assert isinstance(raw_bindings, list)
        assert all(isinstance(binding, dict) for binding in raw_bindings)
        bindings = [binding for binding in raw_bindings if isinstance(binding, dict)]
        for binding in bindings:
            source_unit = source_units[str(binding["source_unit_id"])]
            repeated_unit = repeated_units[str(binding["repeated_unit_id"])]
            for field in visible_fields:
                if field in source_unit:
                    repeated_unit[field] = deepcopy(source_unit[field])
                else:
                    repeated_unit.pop(field, None)


def render_fixture_machine_master(fixture: PilotFixture) -> str:
    """각 Fixture의 Canonical Source에서 Machine Master를 생성한다."""
    crime_event_contract = load_json_object(
        ROOT / "PROJECTS/PRJ-006/01_CASE/crime_event_contract.json"
    )
    drama_script = render_drama_layer(
        fixture["screenplay_units"],
        fixture["presentation_plan"],
        crime_event_contract,
    )
    narration_script = render_narration_layer(
        fixture["screenplay_units"],
        fixture["presentation_plan"],
        crime_event_contract,
    )
    panel_reaction_script = render_panel_layer(
        fixture["reaction_segments"],
        fixture["presentation_plan"],
    )
    return render_broadcast_master(
        fixture["presentation_plan"],
        {
            "drama_script": drama_script,
            "narration_script": narration_script,
            "panel_reaction_script": panel_reaction_script,
        },
    )


def apply_feature_fixture(fixture_id: str) -> PilotFixture:
    """PRJ-006 구조에 독립 Original Fiction 기능 명세를 적용한다."""
    fixture = deepcopy(pilot_fixture())
    spec = feature_spec(fixture_id)
    project_id = spec["project_id"]
    title = spec["title"]
    assert isinstance(project_id, str)
    assert isinstance(title, str)
    fixture["config"]["project_id"] = project_id
    fixture["screenplay_units"]["title"] = title
    for document_name in (
        "screenplay_units",
        "characters",
        "relationships",
        "panel_cast",
        "reaction_segments",
        "presentation_plan",
    ):
        fixture[document_name]["project_id"] = project_id
    replace_named_values(
        mapping_list(fixture["characters"], "characters"),
        "character_id",
        "name",
        mapping_value(spec, "character_names"),
    )
    replace_named_values(
        mapping_list(fixture["panel_cast"], "panelists"),
        "panelist_id",
        "display_name",
        mapping_value(spec, "panel_names"),
    )
    replace_named_values(
        mapping_list(fixture["relationships"], "relationships"),
        "relationship_id",
        "display_summary",
        mapping_value(spec, "relationship_summaries"),
    )
    scenes = mapping_list(fixture["screenplay_units"], "scenes")
    scenes_by_id = {str(scene["scene_id"]): scene for scene in scenes}
    for scene_id, raw_context in mapping_value(spec, "scene_context").items():
        assert isinstance(raw_context, dict)
        context = mapping_value(scenes_by_id[scene_id], "context")
        context.update(raw_context)
    units = [
        unit
        for scene in scenes
        for unit in mapping_list(scene, "units")
    ]
    replace_named_values(
        units,
        "unit_id",
        "text",
        mapping_value(spec, "unit_text"),
    )
    align_reconstruction_units(fixture)
    turns = [
        turn
        for reaction in mapping_list(
            fixture["reaction_segments"],
            "reaction_segments",
        )
        for turn in mapping_list(reaction, "turns")
    ]
    replace_named_values(
        turns,
        "turn_id",
        "spoken_line",
        mapping_value(spec, "panel_text"),
    )
    segments = mapping_list(fixture["presentation_plan"], "segments")
    segments_by_id = {str(segment["segment_id"]): segment for segment in segments}
    front_ids = string_list(spec, "presentation_front_ids")
    reordered = [segments_by_id[segment_id] for segment_id in front_ids]
    reordered.extend(
        segment for segment in segments if segment["segment_id"] not in front_ids
    )
    fixture["presentation_plan"]["segments"] = reordered
    for scene_id, raw_segment_ids in mapping_value(spec, "scene_segment_ids").items():
        assert isinstance(raw_segment_ids, list)
        assert all(isinstance(item, str) for item in raw_segment_ids)
        scenes_by_id[scene_id]["segment_ids"] = raw_segment_ids
    align_presentation_timing(fixture)
    fixture["final_script"] = render_fixture_machine_master(fixture)
    return fixture


def assert_fixture_source_style(fixture_id: str) -> None:
    """공통 Source-style 구조·원문·순서·가시성 불변식을 검증한다."""
    fixture = apply_feature_fixture(fixture_id)
    spec = feature_spec(fixture_id)
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)
    assert report["result"] == "NEEDS_REVIEW"
    assert report["issues"] == []
    documents = {
        "screenplay_units": fixture["screenplay_units"],
        "relationships": fixture["relationships"],
        "panel_cast": fixture["panel_cast"],
        "reaction_segments": fixture["reaction_segments"],
        "presentation_plan": fixture["presentation_plan"],
    }
    for document_name, schema_path in CANONICAL_SCHEMA_PATHS.items():
        validator = Draft202012Validator(load_json_object(schema_path))
        assert list(validator.iter_errors(documents[document_name])) == []
    assert "| 인물 | 역할 | 관계 |" in rendered
    rendered_lines = rendered.splitlines()
    for heading in ("정리 기준", "등장인물", "패널", "방송 대본"):
        assert rendered_lines.count(f"## {heading}") == 1
    for text in string_list(spec, "required_visible_text"):
        assert text in rendered
    for token in FORBIDDEN_VISIBLE_TOKENS:
        assert token not in rendered
    segment_mappings = mapping_records(report, "segment_mappings")
    segment_starts = [mapping_byte_start(mapping) for mapping in segment_mappings]
    assert segment_starts == sorted(segment_starts)
    for scene in mapping_list(fixture["screenplay_units"], "scenes"):
        for unit in mapping_list(scene, "units"):
            unit_text = unit["text"]
            assert isinstance(unit_text, str)
            assert unit_text in rendered
    for reaction in mapping_list(
        fixture["reaction_segments"],
        "reaction_segments",
    ):
        for turn in mapping_list(reaction, "turns"):
            spoken_line = turn["spoken_line"]
            assert isinstance(spoken_line, str)
            assert spoken_line in rendered
    retrospective = report["retrospective_meaning_coverage"]
    assert isinstance(retrospective, dict)
    assert retrospective["mappings_complete"] is True
    assert fixture["final_script"] == render_fixture_machine_master(fixture)


@pytest.mark.parametrize("fixture_id", ["R1", "R2"])
def test_source_style_fixture_is_issue_free(fixture_id: str) -> None:
    """R1·R2는 Raw Reference 없이 독립 Original Fiction Source 문서를 만든다."""
    assert_fixture_source_style(fixture_id)


def test_r1_reentry_note_signal_and_retrospective_positions() -> None:
    """R1의 Note Reveal·반복 신호 재해석·Scene 재진입 순서를 증명한다."""
    fixture = apply_feature_fixture("R1")
    rendered = render_fixture(fixture)
    report = build_report(fixture, rendered)
    assert "**최은결(쪽지)**" in rendered
    assert rendered.count("### 장면 1 재개.") == 1
    assert rendered.count("### 장면 2 재개.") == 1
    scene_mapping = mapping_records(report, "scene_mappings")[0]
    scene_fragment = byte_fragment(rendered, scene_mapping)
    assert scene_fragment.index("세 번째 종이 짧게 끊긴다") < scene_fragment.index(
        "수동 재시작 신호로 다시 읽힌다"
    )


def test_r2_result_first_flashback_message_and_responsibility() -> None:
    """R2의 결과 선제시·회상·Message 위협·책임 진술을 전역 순서로 증명한다."""
    fixture = apply_feature_fixture("R2")
    rendered = render_fixture(fixture)
    assert rendered.index("결과 장면") < rendered.index("사건 열두 시간 전")
    assert "**서준혁(메시지)**" in rendered
    assert "장부를 바꾸고 위협을 보낸 책임은 각자 말해야 합니다" in rendered
    assert "서준혁: 연수원 장부를 함께 관리했지만" in rendered


def test_r1_context_and_retrospective_negative_mutations_fail() -> None:
    """R1의 시작 Sound Context 누락과 Scene-end 재해석 조기 배치를 탐지한다."""
    fixture = apply_feature_fixture("R1")
    rendered = render_fixture(fixture)
    sound_context = next(
        line for line in rendered.splitlines() if line.startswith("*[음향·행동 설명:")
    )
    missing_context = replace_once(rendered, f"{sound_context}\n\n", "")
    assert "BROADCAST_READABLE_V2_CONTEXT_OCCURRENCE_MISMATCH" in issue_codes(
        build_report(fixture, missing_context)
    )
    retrospective = next(
        line for line in rendered.splitlines() if "수동 재시작 신호" in line
    )
    first_mapping = mapping_records(
        build_report(fixture, rendered),
        "unit_mappings",
    )[0]
    first_unit = byte_fragment(rendered, first_mapping)
    moved = replace_once(rendered, f"{retrospective}\n\n", "")
    moved = replace_mapped_fragment(
        moved,
        first_mapping,
        f"{retrospective}\n\n{first_unit}",
    )
    assert "BROADCAST_READABLE_V2_RETROSPECTIVE_POSITION_MISMATCH" in issue_codes(
        build_report(fixture, moved)
    )


def test_r2_relationship_panel_and_unsupported_negative_mutations_fail() -> None:
    """R2 관계 Row·Panel 원문 변조와 미지원 Segment를 각각 탐지한다."""
    fixture = apply_feature_fixture("R2")
    rendered = render_fixture(fixture)
    relationship_row = next(
        line for line in rendered.splitlines() if line.startswith("| 문강석 |")
    )
    relationship_mutation = replace_once(
        rendered,
        relationship_row,
        relationship_row.replace("책임 진술", "책임 회피", 1),
    )
    assert "BROADCAST_READABLE_V2_RELATIONSHIP_ROW_MISMATCH" in issue_codes(
        build_report(fixture, relationship_mutation)
    )
    panel_line = "결과 장면을 먼저 보여 줬지만 빈 좌석의 주인을 섣불리 정하면 안 됩니다."
    panel_mutation = replace_once(rendered, panel_line, f"{panel_line[:-1]}요.")
    assert "BROADCAST_READABLE_V2_PANEL_TURN_OCCURRENCE_MISMATCH" in issue_codes(
        build_report(fixture, panel_mutation)
    )
    unsupported = deepcopy(fixture)
    first_segment = mapping_list(unsupported["presentation_plan"], "segments")[0]
    first_segment["segment_type"] = "EXPERT_ANALYSIS"
    assert "BROADCAST_READABLE_UNSUPPORTED_SEGMENT_TYPE" in issue_codes(
        build_report(unsupported, rendered)
    )


def test_r1_r2_have_distinct_source_derived_machine_masters() -> None:
    """두 Fixture의 Machine Master는 각자의 Canonical Source에서 생성한다."""
    r1 = apply_feature_fixture("R1")
    r2 = apply_feature_fixture("R2")
    assert render_fixture(r1) != render_fixture(r2)
    original_hash = sha256(
        (ROOT / "PROJECTS/PRJ-006/07_SCRIPT/final_script.md").read_bytes()
    ).hexdigest()
    r1_hash = sha256(r1["final_script"].encode("utf-8")).hexdigest()
    r2_hash = sha256(r2["final_script"].encode("utf-8")).hexdigest()
    assert r1_hash != original_hash
    assert r2_hash != original_hash
    assert r1_hash != r2_hash

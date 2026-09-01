"""네 소스형 추상 기능을 독립 Original Fiction 재연 Fixture로 검증한다."""

from copy import deepcopy
from pathlib import Path
from typing import TypedDict, cast

import pytest
from test_screenplay_renderers import (
    characters_document,
    output_profile,
    presentation_plan,
    reaction_segments,
    relationships_document,
    screenplay_document,
)

from RUNTIME.screenplay_renderers import (
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.screenplay_units import validate_screenplay_units

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "TESTS" / "fixtures" / "reenactment_source_style_cases.json"
SCREENPLAY_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "screenplay_units.schema.json"
UNIT_LABELS: dict[str, str] = {
    "ACTION": "[지문]",
    "SOUND": "[음향]",
    "NARRATION": "[내레이션]",
    "INNER_MONOLOGUE": "[속마음]",
    "HALLUCINATION": "[환청·환각]",
    "MESSAGE": "[메시지]",
    "CHAT": "[채팅]",
    "NOTE": "[메모]",
    "RECORDING": "[녹음]",
    "SCREEN_TEXT": "[화면 문구]",
}


class SourceStyleCase(TypedDict):
    """소스 원문을 반입하지 않는 추상 기능 Fixture 형식."""

    case_id: str
    title: str
    pattern: str
    core_action_type: str
    character_names: list[str]
    relationship_engine: str
    scene_titles: list[str]
    seed_sound: str
    retrospective_meaning: str
    unit_texts: dict[str, str]
    expected_unit_types: list[str]
    expected_phrases: list[str]


def source_style_cases() -> list[SourceStyleCase]:
    """Versioned JSON Fixture의 네 독립 사례를 읽는다."""
    document = load_json_object(CASES_PATH)
    raw_cases = document.get("cases")
    assert document.get("schema_family") == "reenactment-source-style-cases"
    assert document.get("schema_version") == "1.0.0"
    assert isinstance(raw_cases, list)
    assert all(isinstance(item, dict) for item in raw_cases)
    return cast(list[SourceStyleCase], raw_cases)


def case_screenplay(case: SourceStyleCase) -> dict[str, object]:
    """공통 구조에 사례별 Original Fiction 내용을 순수하게 적용한다."""
    screenplay = deepcopy(screenplay_document())
    screenplay["title"] = case["title"]
    scenes = screenplay.get("scenes")
    assert isinstance(scenes, list) and len(scenes) == 2
    first_scene = scenes[0]
    reconstruction = scenes[1]
    assert isinstance(first_scene, dict)
    assert isinstance(reconstruction, dict)
    first_scene["title"] = case["scene_titles"][0]
    reconstruction["title"] = case["scene_titles"][1]
    reconstruction_context = reconstruction.get("context")
    assert isinstance(reconstruction_context, dict)
    reconstruction_context["retrospective_meaning"] = case["retrospective_meaning"]
    units_by_id: dict[str, dict[str, object]] = {}
    for scene in scenes:
        assert isinstance(scene, dict)
        units = scene.get("units")
        assert isinstance(units, list)
        for unit in units:
            assert isinstance(unit, dict)
            unit_id = unit.get("unit_id")
            assert isinstance(unit_id, str)
            units_by_id[unit_id] = unit
    for unit_id, text in case["unit_texts"].items():
        units_by_id[unit_id]["text"] = text
    units_by_id["UNIT-002"]["text"] = case["seed_sound"]
    units_by_id["UNIT-012"]["text"] = case["seed_sound"]
    return screenplay


def case_characters(case: SourceStyleCase) -> dict[str, object]:
    """Fixture 인물 이름만 교체한 Canonical Cast를 반환한다."""
    characters = deepcopy(characters_document())
    records = characters.get("characters")
    assert isinstance(records, list)
    assert len(records) == len(case["character_names"])
    for record, name in zip(records, case["character_names"], strict=True):
        assert isinstance(record, dict)
        record["name"] = name
    return characters


def case_relationships(case: SourceStyleCase) -> dict[str, object]:
    """Fixture의 관계 변화 엔진을 반영한다."""
    relationships = deepcopy(relationships_document())
    records = relationships.get("relationships")
    assert isinstance(records, list) and records
    first_record = records[0]
    assert isinstance(first_record, dict)
    first_record["engine"] = case["relationship_engine"]
    return relationships


@pytest.mark.parametrize(
    "case",
    source_style_cases(),
    ids=lambda case: f"fixture-{case['case_id']}-{case['pattern'].lower()}",
)
def test_source_style_reenactment_fixtures_preserve_requested_features(
    case: SourceStyleCase,
) -> None:
    """A-D의 추상 기능은 Unit 원문으로 보존되고 방송 전용 Layer는 분리된다."""
    screenplay = case_screenplay(case)
    characters = case_characters(case)
    relationships = case_relationships(case)

    assert collect_schema_errors(
        screenplay,
        load_json_object(SCREENPLAY_SCHEMA_PATH),
        case["case_id"],
    ) == []
    assert validate_screenplay_units(screenplay) == []

    reenactment = render_reenactment_character_script(
        screenplay,
        characters,
        relationships,
        output_profile(),
    )
    contract: dict[str, object] = {
        "event_id": "EVENT-01",
        "core_action_type": case["core_action_type"],
    }
    plan = presentation_plan()
    drama = render_drama_layer(screenplay, plan, contract)
    narration = render_narration_layer(screenplay, plan, contract)
    panel = render_panel_layer(reaction_segments(), plan)
    broadcast = render_broadcast_master(
        plan,
        {
            "drama_script": drama,
            "narration_script": narration,
            "panel_reaction_script": panel,
        },
    )

    assert f"# {case['title']} — 인물별 대사 스크립트" in reenactment
    assert "작품 구분: ORIGINAL_FICTION" in reenactment
    assert reenactment.count(case["seed_sound"]) == 2
    assert all(phrase in reenactment for phrase in case["expected_phrases"])
    assert all(UNIT_LABELS[unit_type] in reenactment for unit_type in case["expected_unit_types"])
    assert case["retrospective_meaning"] in reenactment
    assert "[RSEG-001]" in broadcast
    assert f"ACTION={case['core_action_type']}" in broadcast
    assert "HARM=HARM-01,HARM-02" in broadcast
    assert all(
        marker not in reenactment
        for marker in (
            "[RSEG-001]",
            "PANEL_REACTION",
            "EXPERT_ANALYSIS",
            "AUDIENCE_PROMPT",
            "<!--",
            "EVENT-01",
            "HARM-01",
            "UNIT-001",
        )
    )


def test_source_style_fixture_catalog_covers_all_four_requested_patterns() -> None:
    """Fixture Catalog가 요구한 A-D 기능군을 중복 없이 고정한다."""
    cases = source_style_cases()

    assert [case["case_id"] for case in cases] == ["A", "B", "C", "D"]
    assert {case["pattern"] for case in cases} == {
        "DOMESTIC_FAMILY_CONTROL",
        "LIMITED_FIRST_PERSON_MURDER_WITNESS",
        "STALKING_ESCALATING_HARM",
        "ACCESS_CRIME_CONFINEMENT",
    }
    assert all(len(case["expected_unit_types"]) >= 4 for case in cases)
    assert all(len(case["expected_phrases"]) >= 3 for case in cases)

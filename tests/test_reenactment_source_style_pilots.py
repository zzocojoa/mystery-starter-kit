"""네 소스형 추상 기능을 독립 Original Fiction 재연 Fixture로 검증한다."""

from copy import deepcopy
from hashlib import sha256
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
from VALIDATORS.crime_harms import derived_harm_fields, structured_harm_issues
from VALIDATORS.io import load_json_object
from VALIDATORS.reenactment_export import (
    ScreenplayDerivedOutputs,
    build_reenactment_export_report,
    validate_reenactment_export_report,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.screenplay_units import (
    validate_screenplay_unit_references,
    validate_screenplay_units,
)

TESTS_DIR = Path(__file__).parent
ROOT = TESTS_DIR.parent
CASES_PATH = TESTS_DIR / "fixtures" / "reenactment_source_style_cases.json"
SCREENPLAY_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "screenplay_units.schema.json"
CRIME_CONTRACT_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "crime_event_contract.schema.json"
EXPORT_REPORT_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "reenactment_export_report.schema.json"
PROFILE_PATH = (
    ROOT
    / "CHANNELS"
    / "mystery_main"
    / "output_profiles"
    / "reenactment-character-script"
    / "1.0.0.json"
)
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


class HarmSpec(TypedDict):
    """Fixture가 선언하는 구조화 피해 한 건."""

    harm_id: str
    classification: str
    timing: str
    summary: str


class SourceStyleCase(TypedDict):
    """소스 원문을 반입하지 않는 추상 기능 Fixture 형식."""

    case_id: str
    title: str
    pattern: str
    primary_crime: str
    core_action_type: str
    related_crimes: list[str]
    responsible_agent_structure: str
    harms: list[HarmSpec]
    character_names: list[str]
    relationship_engine: str
    relationship_summary: str
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
    screenplay["project_id"] = "PRJ-006"
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
    for unit_id, unit_text in case["unit_texts"].items():
        units_by_id[unit_id]["text"] = unit_text
    units_by_id["UNIT-002"]["text"] = case["seed_sound"]
    units_by_id["UNIT-012"]["text"] = case["seed_sound"]
    return screenplay


def case_characters(case: SourceStyleCase) -> dict[str, object]:
    """Fixture 인물 이름만 교체한 Canonical Cast를 반환한다."""
    characters = deepcopy(characters_document())
    characters["project_id"] = "PRJ-006"
    records = characters.get("characters")
    assert isinstance(records, list)
    assert len(records) == len(case["character_names"])
    for record, name in zip(records, case["character_names"], strict=True):
        assert isinstance(record, dict)
        record["name"] = name
    return characters


def case_relationships(case: SourceStyleCase) -> dict[str, object]:
    """Fixture의 관계 변화 엔진과 사람이 읽는 요약을 반영한다."""
    relationships = deepcopy(relationships_document())
    relationships["project_id"] = "PRJ-006"
    records = relationships.get("relationships")
    assert isinstance(records, list) and records
    first_record = records[0]
    assert isinstance(first_record, dict)
    first_record["engine"] = case["relationship_engine"]
    first_record["display_summary"] = case["relationship_summary"]
    return relationships


def case_harms(case: SourceStyleCase) -> list[dict[str, object]]:
    """Fixture 피해를 Canonical Character에 결속한다."""
    return [{**deepcopy(harm), "victim_ids": ["CHAR-001"]} for harm in case["harms"]]


def original_fiction_truth_basis() -> dict[str, object]:
    """외부 Source Claim이 없는 Original Fiction 근거를 만든다."""
    evidence = {"classification": "ORIGINAL_FICTION", "claim_ids": []}
    return {
        "source_truth_classification": "ORIGINAL_FICTION",
        "field_evidence": {
            field: deepcopy(evidence)
            for field in (
                "PRIMARY_CRIME",
                "CULPRIT",
                "MOTIVE",
                "METHOD",
                "HARM_RESULT",
                "LEGAL_OUTCOME",
            )
        },
    }


def case_crime_contract(case: SourceStyleCase) -> dict[str, object]:
    """등록 범죄와 두 피해를 가진 완전한 사건 계약을 만든다."""
    harms = case_harms(case)
    dual_agents = case["responsible_agent_structure"] == "DUAL_AGENTS"
    offender_slots = ["OFFENDER-01", "OFFENDER-02"] if dual_agents else ["OFFENDER-01"]
    actor_ids = ["CHAR-002", "CHAR-003"] if dual_agents else ["CHAR-002"]
    role_bindings = [
        {
            "role_slot": role_slot,
            "character_id": character_id,
            "role_type": "OFFENDER",
        }
        for role_slot, character_id in zip(offender_slots, actor_ids, strict=True)
    ]
    role_bindings.append(
        {
            "role_slot": "VICTIM-01",
            "character_id": "CHAR-001",
            "role_type": "VICTIM",
        }
    )
    contract: dict[str, object] = {
        "schema_family": "crime-event-contract",
        "schema_version": "1.2.0",
        "project_id": "PRJ-006",
        "approved_candidate_id": "VAR-01",
        "candidate_selection_sha256": "0" * 64,
        "candidate_event_brief_sha256": "1" * 64,
        "event_id": "EVENT-01",
        "primary_crime": case["primary_crime"],
        "related_crimes": case["related_crimes"],
        "core_action_type": case["core_action_type"],
        "responsible_agent_structure": case["responsible_agent_structure"],
        "victim_structure": "SINGLE_VICTIM",
        "offender_role_slots": offender_slots,
        "victim_role_slots": ["VICTIM-01"],
        "protagonist_role_slot": "PROTAGONIST-01",
        "role_bindings": role_bindings,
        "actor_ids": actor_ids,
        "victim_ids": ["CHAR-001"],
        "protagonist_id": "CHAR-001",
        "relationship_context": case["relationship_summary"],
        "target_selection_reason": "가해자가 신뢰 또는 접근 권한을 악용할 수 있는 대상이었다.",
        "initiating_context": "일상 공간의 작은 이상 징후가 반복되기 시작한다.",
        "trigger_event": "기록과 물리적 흔적이 같은 행위자를 가리킨다.",
        "motive_category": "CONTROL_AND_CONCEALMENT",
        "motive_summary": "가해자는 피해자를 통제하고 자신의 개입을 숨기려 한다.",
        "non_actionable_method_summary": (
            "접근 권한과 신뢰를 악용해 비선정적으로 범죄 행동을 실행한다."
        ),
        "concealment_or_denial": "우연과 보호를 주장하며 반복 행동의 연결을 부인한다.",
        "discovery_path": "반복된 소리와 기록의 시간 순서를 대조해 책임 경로를 확인한다.",
        "responsibility_path": "구조화된 기록과 재구성이 가해자의 행동과 피해 결과를 연결한다.",
        "central_pursuit_question": "익숙한 신호를 이용해 피해자를 해친 사람은 누구인가?",
        "protagonist_goal": "범죄 행동을 입증하고 안전을 회복한다.",
        "protagonist_risk": "추가 접근과 신체적·심리적 피해 위험이 있다.",
        "depiction_mode": "IMPLIED",
        "development_functions": [
            {
                "development_function_id": f"CDEV-{index:03d}",
                "function_type": function_type,
                "summary": f"{function_type} 기능을 행동과 결과로 구현한다.",
                "required": True,
            }
            for index, function_type in enumerate(
                (
                    "HARM_OR_DANGER_RECOGNITION",
                    "INVOLVEMENT_OR_SUSPICION",
                    "MOTIVE_AND_RESPONSIBILITY",
                    "EVENT_RECONSTRUCTION",
                ),
                1,
            )
        ],
        "reveal_targets": [
            {
                "reveal_target_id": f"REVEAL-TARGET-{index:02d}",
                "target_type": target_type,
                "summary": f"{target_type}의 책임 정보를 후반에 공개한다.",
                "planned_phase": "LATE",
                "planned_segment_id": "SEG-004",
            }
            for index, target_type in enumerate(
                ("CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"),
                1,
            )
        ],
        "method_detail_level": "NON_ACTIONABLE_SUMMARY_ONLY",
        "truth_basis": original_fiction_truth_basis(),
        "harms": harms,
    }
    contract.update(derived_harm_fields(harms))
    return contract


def facts_document() -> dict[str, object]:
    """Unit 참조 검증용 사실 문서를 만든다."""
    return {
        "project_id": "PRJ-006",
        "facts": [{"fact_id": "FACT-01", "statement": "반복 신호는 범죄 행동과 연결된다."}],
    }


def clue_matrix() -> dict[str, object]:
    """표면 의미가 후반에 실제 의미로 변하는 단서를 만든다."""
    return {
        "schema_family": "clue-matrix",
        "schema_version": "1.1.0",
        "project_id": "PRJ-006",
        "clues": [
            {
                "clue_id": "CLUE-01",
                "reveal_mode": "SEEDED_REINTERPRETATION",
                "surface_meaning": "반복 소리는 일상적인 알림이다.",
                "actual_meaning": "반복 소리는 가해 행동의 시작 또는 은폐 신호다.",
                "first_seen_scene_id": "SCN-001",
                "reveal_scene_id": "SCN-002",
                "recontextualized_scene_ids": ["SCN-001"],
            }
        ],
    }


def case_presentation_plan() -> dict[str, object]:
    """PRJ-006용 방송 Presentation Plan을 반환한다."""
    plan = deepcopy(presentation_plan())
    plan["project_id"] = "PRJ-006"
    return plan


def case_reaction_segments() -> dict[str, object]:
    """PRJ-006용 방송 Panel Reaction을 반환한다."""
    reactions = deepcopy(reaction_segments())
    reactions["project_id"] = "PRJ-006"
    return reactions


def production_config() -> dict[str, object]:
    """Fixture Export Report용 Screenplay Unit 설정을 만든다."""
    return {
        "project_id": "PRJ-006",
        "script_source_mode": "SCREENPLAY_UNITS",
        "source_truth_classification": "ORIGINAL_FICTION",
        "reenactment_output_profile_id": "REENACTMENT_CHARACTER_SCRIPT",
        "reenactment_output_profile_version": "1.0.0",
    }


def derived_outputs(
    screenplay: dict[str, object],
    characters: dict[str, object],
    relationships: dict[str, object],
    contract: dict[str, object],
) -> ScreenplayDerivedOutputs:
    """현재 Fixture 입력에서 방송·재연 출력을 결정론적으로 만든다."""
    plan = case_presentation_plan()
    reactions = case_reaction_segments()
    drama = render_drama_layer(screenplay, plan, contract)
    narration = render_narration_layer(screenplay, plan, contract)
    panel = render_panel_layer(reactions, plan)
    master = render_broadcast_master(
        plan,
        {
            "drama_script": drama,
            "narration_script": narration,
            "panel_reaction_script": panel,
        },
    )
    reenactment = render_reenactment_character_script(
        screenplay,
        characters,
        relationships,
        output_profile(),
    )
    return ScreenplayDerivedOutputs(
        drama_script=drama,
        narration_script=narration,
        panel_reaction_script=panel,
        draft_script=master,
        final_script=master,
        reenactment_character_script=reenactment,
    )


def report_for_case(
    screenplay: dict[str, object],
    characters: dict[str, object],
    relationships: dict[str, object],
    contract: dict[str, object],
    outputs: ScreenplayDerivedOutputs,
) -> dict[str, object]:
    """사례의 모든 Canonical 입력과 출력에서 Export Report를 만든다."""
    return build_reenactment_export_report(
        production_config(),
        screenplay,
        facts_document(),
        characters,
        relationships,
        contract,
        clue_matrix(),
        output_profile(),
        sha256(PROFILE_PATH.read_bytes()).hexdigest(),
        case_presentation_plan(),
        case_reaction_segments(),
        outputs,
    )


def test_source_style_fixture_catalog_file_exists() -> None:
    """Linux에서도 실제 소문자 tests 경로의 Fixture를 찾는다."""
    assert CASES_PATH.is_file()


@pytest.mark.parametrize(
    "case",
    source_style_cases(),
    ids=lambda case: f"fixture-{case['case_id']}-{case['pattern'].lower()}",
)
def test_source_style_reenactment_fixtures_preserve_requested_features(
    case: SourceStyleCase,
) -> None:
    """A-D는 완전한 범죄 계약부터 방송·재연 Export까지 검증된다."""
    screenplay = case_screenplay(case)
    characters = case_characters(case)
    relationships = case_relationships(case)
    contract = case_crime_contract(case)
    facts = facts_document()
    clues = clue_matrix()
    plan = case_presentation_plan()

    assert (
        collect_schema_errors(
            screenplay,
            load_json_object(SCREENPLAY_SCHEMA_PATH),
            case["case_id"],
        )
        == []
    )
    assert validate_screenplay_units(screenplay) == []
    assert (
        collect_schema_errors(
            contract,
            load_json_object(CRIME_CONTRACT_SCHEMA_PATH),
            case["case_id"],
        )
        == []
    )
    assert (
        structured_harm_issues(
            contract,
            "01_CASE/crime_event_contract.json",
            "victim_ids",
            {"CHAR-001"},
            True,
        )
        == []
    )
    assert (
        validate_screenplay_unit_references(
            screenplay,
            facts,
            clues,
            contract,
            characters,
            plan,
        )
        == []
    )

    outputs = derived_outputs(screenplay, characters, relationships, contract)
    reenactment = outputs["reenactment_character_script"]
    broadcast = outputs["final_script"]
    report = report_for_case(
        screenplay,
        characters,
        relationships,
        contract,
        outputs,
    )

    assert (
        collect_schema_errors(
            report,
            load_json_object(EXPORT_REPORT_SCHEMA_PATH),
            case["case_id"],
        )
        == []
    )
    assert (
        validate_reenactment_export_report(
            report,
            production_config(),
            screenplay,
            facts,
            characters,
            relationships,
            contract,
            clues,
            output_profile(),
            sha256(PROFILE_PATH.read_bytes()).hexdigest(),
            plan,
            case_reaction_segments(),
            outputs,
        )
        == []
    )
    assert report["result"] == "NEEDS_REVIEW"
    assert f"# {case['title']} — 인물별 대사 스크립트" in reenactment
    assert "작품 구분: ORIGINAL_FICTION" in reenactment
    assert reenactment.count(case["seed_sound"]) == 2
    assert all(phrase in reenactment for phrase in case["expected_phrases"])
    assert all(UNIT_LABELS[unit_type] in reenactment for unit_type in case["expected_unit_types"])
    assert case["retrospective_meaning"] in reenactment
    assert case["relationship_summary"] in reenactment
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


@pytest.mark.parametrize(
    "case",
    source_style_cases(),
    ids=lambda case: f"fixture-{case['case_id']}-negative-reference",
)
def test_each_source_style_family_rejects_an_unknown_reference(
    case: SourceStyleCase,
) -> None:
    """A-D 각 기능군은 상위 Artifact에 없는 참조를 명시적으로 거부한다."""
    mutations = {
        "A": ("fact_ids", "FACT-999", "SCREENPLAY_FACT_REFERENCE_UNKNOWN"),
        "B": ("clue_ids", "CLUE-999", "SCREENPLAY_CLUE_REFERENCE_UNKNOWN"),
        "C": ("crime_event_ids", "EVENT-999", "SCREENPLAY_EVENT_REFERENCE_UNKNOWN"),
        "D": ("harm_ids", "HARM-999", "SCREENPLAY_HARM_REFERENCE_UNKNOWN"),
    }
    field, unknown_id, expected_code = mutations[case["case_id"]]
    screenplay = case_screenplay(case)
    scenes = screenplay["scenes"]
    assert isinstance(scenes, list)
    first_scene = scenes[0]
    assert isinstance(first_scene, dict)
    units = first_scene["units"]
    assert isinstance(units, list)
    first_unit = units[0]
    assert isinstance(first_unit, dict)
    references = first_unit["references"]
    assert isinstance(references, dict)
    references[field] = [unknown_id]

    issues = validate_screenplay_unit_references(
        screenplay,
        facts_document(),
        clue_matrix(),
        case_crime_contract(case),
        case_characters(case),
        case_presentation_plan(),
    )

    assert expected_code in {issue["code"] for issue in issues}


def test_source_style_fixture_catalog_covers_all_four_requested_patterns() -> None:
    """Fixture Catalog가 요구한 A-D 기능군과 등록 범죄를 고정한다."""
    cases = source_style_cases()

    assert [case["case_id"] for case in cases] == ["A", "B", "C", "D"]
    assert {case["pattern"] for case in cases} == {
        "DOMESTIC_FAMILY_CONTROL",
        "LIMITED_FIRST_PERSON_MURDER_WITNESS",
        "STALKING_ESCALATING_HARM",
        "ACCESS_CRIME_CONFINEMENT",
    }
    assert {case["primary_crime"] for case in cases} == {
        "DOMESTIC_VIOLENCE",
        "MURDER",
        "STALKING",
        "CONFINEMENT",
    }
    assert all(len(case["harms"]) == 2 for case in cases)
    assert all(len(case["expected_unit_types"]) >= 4 for case in cases)
    assert all(len(case["expected_phrases"]) >= 3 for case in cases)

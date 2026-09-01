"""결정론적 Screenplay·재연 Renderer 회귀 테스트."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from RUNTIME.screenplay_renderers import (
    package_production_reenactment_script,
    reenactment_export_filename,
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = (
    ROOT
    / "CHANNELS"
    / "mystery_main"
    / "output_profiles"
    / "reenactment-character-script"
    / "1.0.0.json"
)
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "reenactment_character_script.golden.md"


def references(
    fact_ids: list[str],
    clue_ids: list[str],
    event_ids: list[str],
    harm_ids: list[str],
    function_ids: list[str],
    reveal_ids: list[str],
) -> dict[str, object]:
    """Renderer Fixture의 구조화된 Unit 참조를 만든다."""
    return {
        "fact_ids": fact_ids,
        "clue_ids": clue_ids,
        "crime_event_ids": event_ids,
        "harm_ids": harm_ids,
        "development_function_ids": function_ids,
        "reveal_target_ids": reveal_ids,
    }


def screenplay_unit(
    unit_id: str,
    order: int,
    unit_type: str,
    text: str,
    segment_id: str,
    speaker_id: str | None,
    unit_references: Mapping[str, object],
) -> dict[str, object]:
    """한 Screenplay Unit Fixture를 만든다."""
    unit: dict[str, object] = {
        "unit_id": unit_id,
        "order": order,
        "type": unit_type,
        "text": text,
        "segment_id": segment_id,
        "references": dict(unit_references),
    }
    if speaker_id is not None:
        unit["speaker_id"] = speaker_id
        unit["delivery"] = {"instruction": "낮고 또렷하게", "pace": "SLOW"}
    return unit


def context(previous_scene_id: str | None, retrospective_meaning: str | None) -> dict[str, object]:
    """재연 문서에 필요한 상세 Scene Context를 만든다."""
    value: dict[str, object] = {
        "location_description": "폐쇄된 지하 기록실",
        "time_description": "현재, 자정 직전",
        "previous_scene_id": previous_scene_id,
        "background_music_description": "낮고 불규칙한 현악음",
        "sound_cues": [
            {
                "sound_cue_id": "SOUND-001",
                "order": 1,
                "description": "형광등 안정기가 짧게 떨린다.",
            }
        ],
        "opening_character_state": "지안은 출구를 등지고 봉인함을 바라본다.",
        "opening_emotional_state": "불안을 감춘 경계 상태",
        "action_summary": "봉인된 기록의 시각을 확인한다.",
        "audience_information_gain": "경보음의 의미가 처음 보인 것과 다를 수 있다.",
    }
    if retrospective_meaning is not None:
        value["retrospective_meaning"] = retrospective_meaning
    return value


def screenplay_document() -> dict[str, object]:
    """열한 유형과 의도적 재구성 반복을 포함한 Screenplay Fixture를 만든다."""
    empty = references([], [], [], [], [], [])
    crime = references(
        ["FACT-01"],
        ["CLUE-01"],
        ["EVENT-01"],
        ["HARM-01", "HARM-02"],
        ["CDEV-001"],
        ["REVEAL-TARGET-01"],
    )
    return {
        "schema_family": "screenplay-units",
        "schema_version": "1.1.0",
        "project_id": "PRJ-005",
        "title": "봉인된 시각",
        "source_truth_classification": "ORIGINAL_FICTION",
        "scenes": [
            {
                "scene_id": "SCN-001",
                "order": 1,
                "title": "경보 이전",
                "time_layer": "COLD_OPEN",
                "location_id": "LOC-001",
                "segment_ids": ["SEG-001", "SEG-002"],
                "context": context(None, None),
                "units": [
                    screenplay_unit(
                        "UNIT-001",
                        1,
                        "ACTION",
                        "지안이 봉인함 위의 붉은 표시를 손끝으로 짚는다.",
                        "SEG-001",
                        None,
                        crime,
                    ),
                    screenplay_unit(
                        "UNIT-002",
                        2,
                        "SOUND",
                        "짧은 경보음이 두 번 울린다.",
                        "SEG-001",
                        None,
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-003",
                        3,
                        "DIALOGUE",
                        "이 소리는 문이 열린 뒤에만 나요.",
                        "SEG-001",
                        "CHAR-001",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-004",
                        4,
                        "NARRATION",
                        "그때의 나는 경보가 이미 끝난 사건을 가리킨다고 믿었다.",
                        "SEG-002",
                        "CHAR-001",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-005",
                        5,
                        "INNER_MONOLOGUE",
                        "내 기억이 또 틀렸다면 누구를 믿어야 하지?",
                        "SEG-001",
                        "CHAR-001",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-006",
                        6,
                        "HALLUCINATION",
                        "돌아보지 마.",
                        "SEG-001",
                        "CHAR-002",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-007",
                        7,
                        "MESSAGE",
                        "기록실에서 기다려.",
                        "SEG-001",
                        "CHAR-002",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-008",
                        8,
                        "CHAT",
                        "자정 전에는 아무도 들어가면 안 돼.",
                        "SEG-001",
                        "CHAR-001",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-009",
                        9,
                        "NOTE",
                        "경보 두 번은 잠금 해제 신호.",
                        "SEG-001",
                        "CHAR-002",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-010",
                        10,
                        "RECORDING",
                        "문을 연 사람은 나 혼자가 아니야.",
                        "SEG-001",
                        "CHAR-002",
                        empty,
                    ),
                    screenplay_unit(
                        "UNIT-011",
                        11,
                        "SCREEN_TEXT",
                        "23:47 잠금 해제",
                        "SEG-001",
                        None,
                        empty,
                    ),
                ],
            },
            {
                "scene_id": "SCN-002",
                "order": 2,
                "title": "같은 소리의 의미",
                "time_layer": "RECONSTRUCTION",
                "location_id": "LOC-001",
                "segment_ids": ["SEG-004"],
                "reconstruction_of_scene_id": "SCN-001",
                "reconstruction_bindings": [
                    {
                        "source_unit_id": "UNIT-002",
                        "repeated_unit_id": "UNIT-012",
                        "preservation": "EXACT_TEXT",
                    }
                ],
                "context": context(
                    "SCN-001",
                    "첫 장면의 경보음은 침입 이후가 아니라 공범의 잠금 해제 신호였다.",
                ),
                "units": [
                    screenplay_unit(
                        "UNIT-012",
                        1,
                        "SOUND",
                        "짧은 경보음이 두 번 울린다.",
                        "SEG-004",
                        None,
                        crime,
                    ),
                    screenplay_unit(
                        "UNIT-013",
                        2,
                        "DIALOGUE",
                        "끝난 뒤의 경보가 아니라, 시작하라는 신호였어.",
                        "SEG-004",
                        "CHAR-001",
                        crime,
                    ),
                ],
            },
        ],
    }


def characters_document() -> dict[str, object]:
    """Canonical Cast Fixture를 만든다."""
    return {
        "project_id": "PRJ-005",
        "characters": [
            {"character_id": "CHAR-001", "name": "지안", "role": "기록 분석가"},
            {"character_id": "CHAR-002", "name": "민호", "role": "실종된 동료"},
            {"character_id": "CHAR-003", "name": "서윤", "role": "수사관"},
        ],
    }


def relationships_document() -> dict[str, object]:
    """Canonical Relationship Fixture를 만든다."""
    return {
        "project_id": "PRJ-005",
        "relationships": [
            {
                "relationship_id": "REL-001",
                "from": "CHAR-001",
                "to": "CHAR-002",
                "engine": "TRUST_TO_BETRAYAL",
            }
        ],
    }


def presentation_plan() -> dict[str, object]:
    """Drama→Narration→Panel→재구성 순서의 Presentation Fixture를 만든다."""
    return {
        "schema_family": "presentation-plan",
        "schema_version": "2.1.0",
        "project_id": "PRJ-005",
        "modes": ["DRAMA", "NARRATION", "PANEL_REACTION"],
        "segments": [
            {
                "segment_id": "SEG-001",
                "segment_type": "DRAMA",
                "scene_id": "SCN-001",
                "start_sec": 0,
                "duration_sec": 45,
                "source_artifact": "drama_script",
                "revealed_fact_ids": ["FACT-01"],
                "revealed_clue_ids": ["CLUE-01"],
            },
            {
                "segment_id": "SEG-002",
                "segment_type": "NARRATION",
                "scene_id": "SCN-001",
                "start_sec": 45,
                "duration_sec": 15,
                "source_artifact": "narration_script",
                "revealed_fact_ids": [],
                "revealed_clue_ids": [],
            },
            {
                "segment_id": "SEG-003",
                "segment_type": "PANEL_REACTION",
                "scene_id": "SCN-001",
                "reaction_segment_id": "RSEG-001",
                "start_sec": 60,
                "duration_sec": 20,
                "source_artifact": "panel_reaction_script",
                "revealed_fact_ids": [],
                "revealed_clue_ids": [],
            },
            {
                "segment_id": "SEG-004",
                "segment_type": "DRAMA",
                "scene_id": "SCN-002",
                "start_sec": 80,
                "duration_sec": 40,
                "source_artifact": "drama_script",
                "revealed_fact_ids": ["FACT-01"],
                "revealed_clue_ids": ["CLUE-01"],
            },
        ],
    }


def reaction_segments() -> dict[str, object]:
    """기존 Panel Reaction Contract Fixture를 만든다."""
    return {
        "schema_family": "reaction-segments",
        "schema_version": "2.1.0",
        "project_id": "PRJ-005",
        "reaction_segments": [
            {
                "reaction_segment_id": "RSEG-001",
                "after_scene_id": "SCN-001",
                "order": 1,
                "start_sec": 60,
                "duration_sec": 20,
                "segment_function": "HYPOTHESIS_REVISION",
                "hypothesis_before": "경보는 사건 종료를 뜻한다.",
                "hypothesis_after": "경보는 공범의 행동 신호일 수 있다.",
                "tone": "SUSPICIOUS",
                "turns": [
                    {
                        "turn_id": "TURN-001-01",
                        "panelist_id": "PANEL-01",
                        "function": "HYPOTHESIS_REVISION",
                        "spoken_line": "경보의 순서를 다시 봐야 합니다.",
                        "evidence_ids": ["CLUE-01"],
                        "known_fact_ids": ["FACT-01"],
                        "tone": "SUSPICIOUS",
                    }
                ],
            }
        ],
    }


def crime_event_contract() -> dict[str, object]:
    """Unit Event 참조에서 ACTION 추적 값을 해석할 Contract Fixture를 만든다."""
    return {"event_id": "EVENT-01", "core_action_type": "COERCIVE_CONFINEMENT"}


def output_profile() -> dict[str, object]:
    """등록된 고정 Reenactment Output Profile을 읽는다."""
    return load_json_object(PROFILE_PATH)


def test_reenactment_character_script_matches_golden_snapshot() -> None:
    """동일 입력은 승인된 Golden Markdown과 바이트 단위로 일치한다."""
    rendered = render_reenactment_character_script(
        screenplay_document(),
        characters_document(),
        relationships_document(),
        output_profile(),
    )

    assert rendered.encode("utf-8") == GOLDEN_PATH.read_bytes()
    assert render_reenactment_character_script(
        screenplay_document(),
        characters_document(),
        relationships_document(),
        output_profile(),
    ).encode("utf-8") == rendered.encode("utf-8")


def test_reenactment_preserves_unit_text_and_special_labels() -> None:
    """모든 포함 Unit 원문과 특수 유형 표기가 손실 없이 출력된다."""
    screenplay = screenplay_document()
    rendered = render_reenactment_character_script(
        screenplay,
        characters_document(),
        relationships_document(),
        output_profile(),
    )
    expected_text_counts: dict[str, int] = {}
    scenes = screenplay["scenes"]
    assert isinstance(scenes, list)
    for scene in scenes:
        assert isinstance(scene, dict)
        units = scene["units"]
        assert isinstance(units, list)
        for unit in units:
            assert isinstance(unit, dict)
            text = unit["text"]
            assert isinstance(text, str)
            expected_text_counts[text] = expected_text_counts.get(text, 0) + 1

    assert all(rendered.count(text) == count for text, count in expected_text_counts.items())
    assert "[내레이션] 지안:" in rendered
    assert "[속마음] 지안:" in rendered
    assert "[환청·환각] 민호:" in rendered
    assert "[메시지] 민호:" in rendered
    assert "[채팅] 지안:" in rendered
    assert "[메모] 민호:" in rendered
    assert "[녹음] 민호:" in rendered
    assert "[화면 문구] 23:47 잠금 해제" in rendered


def test_reenactment_excludes_broadcast_and_internal_content() -> None:
    """재연 Export에는 Panel·분석·유도·내부 추적 Marker가 없다."""
    rendered = render_reenactment_character_script(
        screenplay_document(),
        characters_document(),
        relationships_document(),
        output_profile(),
    )

    forbidden = (
        "경보의 순서를 다시 봐야 합니다.",
        "PANEL_REACTION",
        "EXPERT_ANALYSIS",
        "AUDIENCE_PROMPT",
        "<!--",
        "FACT-01",
        "CLUE-01",
        "EVENT-01",
        "HARM-01",
        "UNIT-001",
    )
    assert all(marker not in rendered for marker in forbidden)


def test_layers_and_broadcast_master_are_deterministic_and_ordered() -> None:
    """방송 Layer와 Master는 Unit 참조 추적과 Presentation 순서를 보존한다."""
    screenplay = screenplay_document()
    plan = presentation_plan()
    contract = crime_event_contract()
    drama = render_drama_layer(screenplay, plan, contract)
    narration = render_narration_layer(screenplay, plan, contract)
    panel = render_panel_layer(reaction_segments(), plan)
    layers = {
        "drama_script": drama,
        "narration_script": narration,
        "panel_reaction_script": panel,
    }
    master = render_broadcast_master(plan, layers)

    assert "EVENT=EVENT-01" in drama
    assert "ACTION=COERCIVE_CONFINEMENT" in drama
    assert "HARM=HARM-01,HARM-02" in drama
    assert "DEV=CDEV-001" in drama
    assert "<!-- UNIT:UNIT-001" in drama
    assert "[RSEG-001] [PANEL-01] [HYPOTHESIS_REVISION]" in panel
    assert [master.index(f"<!-- SEGMENT:SEG-00{index} ") for index in range(1, 5)] == sorted(
        master.index(f"<!-- SEGMENT:SEG-00{index} ") for index in range(1, 5)
    )
    assert master.encode("utf-8") == render_broadcast_master(plan, layers).encode("utf-8")
    assert master.count("짧은 경보음이 두 번 울린다.") == 2


def test_layer_render_rejects_unit_on_wrong_presentation_layer() -> None:
    """Narration Unit을 Drama Segment에 놓으면 조용히 유실하지 않고 실패한다."""
    screenplay = screenplay_document()
    scenes = screenplay["scenes"]
    assert isinstance(scenes, list)
    first_scene = scenes[0]
    assert isinstance(first_scene, dict)
    units = first_scene["units"]
    assert isinstance(units, list)
    narration = units[3]
    assert isinstance(narration, dict)
    narration["segment_id"] = "SEG-001"

    with pytest.raises(ConfigurationError, match="SCREENPLAY_UNIT_LAYER_MISMATCH"):
        render_drama_layer(screenplay, presentation_plan(), crime_event_contract())


def test_production_packaging_is_byte_identical_and_filename_is_safe() -> None:
    """Production 복사는 바이트 동일하며 외부 Export 이름은 경로가 될 수 없다."""
    rendered = render_reenactment_character_script(
        screenplay_document(),
        characters_document(),
        relationships_document(),
        output_profile(),
    )

    assert package_production_reenactment_script(rendered) is rendered
    assert reenactment_export_filename("봉인된 시각") == "봉인된 시각_인물별_대사_스크립트.md"
    assert reenactment_export_filename("../봉인/시각") == "_봉인_시각_인물별_대사_스크립트.md"

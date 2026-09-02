"""Presentation Contract v2의 구조·대본·제작 검증."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from project_factory import make_complete_project_artifacts
from test_reenactment_export import clue_matrix, crime_event_contract, facts_document
from test_screenplay_renderers import (
    characters_document,
    output_profile,
    presentation_plan,
    reaction_segments,
    relationships_document,
    screenplay_document,
)

from RUNTIME.core_tasks import runtime_validation_inputs
from RUNTIME.gate_control import validate_gate
from RUNTIME.screenplay_renderers import (
    render_broadcast_master,
    render_drama_layer,
    render_narration_layer,
    render_panel_layer,
    render_reenactment_character_script,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
from VALIDATORS.output_profiles import resolve_reenactment_output_profile
from VALIDATORS.pipeline import ArtifactContent
from VALIDATORS.presentation_validation import (
    absolute_time_issues,
    actual_panel_reaction_ratio,
    audience_belief_alignment_issues,
    narration_duplication_issues,
    script_segment_alignment_issues,
    validate_presentation_design,
    validate_production_presentation,
    validate_script_integrity_v2,
)

ROOT = Path(__file__).resolve().parents[1]


def document(
    artifacts: dict[str, ArtifactContent],
    artifact_name: str,
) -> dict[str, object]:
    """테스트 Artifact의 JSON 객체를 엄격하게 읽는다."""
    value = artifacts[artifact_name]
    assert isinstance(value, dict)
    return value


def text_artifact(
    artifacts: dict[str, ArtifactContent],
    artifact_name: str,
) -> str:
    """테스트 Artifact의 Markdown 문자열을 엄격하게 읽는다."""
    value = artifacts[artifact_name]
    assert isinstance(value, str)
    return value


def issue_codes(issues: Sequence[Mapping[str, object]]) -> set[str]:
    """검증 결과에서 오류 코드 집합을 반환한다."""
    return {
        cast(str, issue["code"])
        for issue in issues
        if isinstance(issue.get("code"), str)
    }


def presentation_design_issues(
    artifacts: dict[str, ArtifactContent],
) -> list[ValidationIssue]:
    """완전한 Project Fixture에 GATE-07 검증을 실행한다."""
    return validate_presentation_design(
        document(artifacts, "panel_cast"),
        document(artifacts, "reaction_segments"),
        document(artifacts, "presentation_plan"),
        document(artifacts, "scene_cards"),
        document(artifacts, "viewer_timeline"),
        document(artifacts, "facts"),
        document(artifacts, "clue_matrix"),
        load_json_object(
            ROOT / "CHANNELS" / "mystery_main" / "versions" / "1.1.0" / "channel_dna.json"
        ),
        document(artifacts, "production_config"),
    )


def script_integrity_issues(
    artifacts: dict[str, ArtifactContent],
) -> list[ValidationIssue]:
    """완전한 Project Fixture에 GATE-08 검증을 실행한다."""
    return validate_script_integrity_v2(
        document(artifacts, "presentation_plan"),
        document(artifacts, "reaction_segments"),
        document(artifacts, "scene_cards"),
        document(artifacts, "viewer_timeline"),
        document(artifacts, "audience_belief"),
        document(artifacts, "actual_timeline"),
        text_artifact(artifacts, "drama_script"),
        text_artifact(artifacts, "narration_script"),
        text_artifact(artifacts, "panel_reaction_script"),
        text_artifact(artifacts, "expert_analysis_script"),
        text_artifact(artifacts, "draft_script"),
        text_artifact(artifacts, "final_script"),
    )


def direct_gate_issues(
    artifacts: dict[str, ArtifactContent],
    gate_id: str,
) -> list[ValidationIssue]:
    """완전한 Fixture에 지정 Gate Validator를 직접 실행한다."""
    (
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        novelty_thresholds,
    ) = runtime_validation_inputs(ROOT)
    config = document(artifacts, "production_config")
    resolved_profile = (
        resolve_reenactment_output_profile(ROOT, config)
        if isinstance(config.get("reenactment_output_profile_id"), str)
        and isinstance(config.get("reenactment_output_profile_version"), str)
        else None
    )
    if resolved_profile is not None:
        presentation_schemas = dict(presentation_schemas)
        presentation_schemas["reenactment_output_profile"] = resolved_profile[
            "document"
        ]
        presentation_schemas["reenactment_output_profile_binding"] = {
            "sha256": resolved_profile["sha256"]
        }
    return validate_gate(
        gate_id,
        artifacts,
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        reference_policy,
        novelty_thresholds,
        [],
        None,
    )


def new_mode_gate_artifacts() -> dict[str, ArtifactContent]:
    """Screenplay Unit 경로의 GATE-08 직접 검증 Fixture를 만든다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    config = document(artifacts, "production_config")
    config.update(
        {
            "script_source_mode": "SCREENPLAY_UNITS",
            "reenactment_output_profile_id": "REENACTMENT_CHARACTER_SCRIPT",
            "reenactment_output_profile_version": "1.0.0",
        }
    )
    project_id = cast(str, config["project_id"])
    replacements = {
        "screenplay_units": screenplay_document(),
        "facts": facts_document(),
        "characters": characters_document(),
        "relationships": relationships_document(),
        "crime_event_contract": crime_event_contract(),
        "clue_matrix": clue_matrix(),
        "presentation_plan": presentation_plan(),
        "reaction_segments": reaction_segments(),
    }
    for artifact_name, value in replacements.items():
        value["project_id"] = project_id
        artifacts[artifact_name] = value
    screenplay = document(artifacts, "screenplay_units")
    plan = document(artifacts, "presentation_plan")
    crime_contract = document(artifacts, "crime_event_contract")
    reactions = document(artifacts, "reaction_segments")
    characters = document(artifacts, "characters")
    relationships = document(artifacts, "relationships")
    profile = output_profile()
    drama = render_drama_layer(screenplay, plan, crime_contract)
    narration = render_narration_layer(screenplay, plan, crime_contract)
    panel = render_panel_layer(reactions, plan)
    master = render_broadcast_master(
        plan,
        {
            "drama_script": drama,
            "narration_script": narration,
            "panel_reaction_script": panel,
        },
    )
    artifacts.update(
        {
            "drama_script": drama,
            "narration_script": narration,
            "panel_reaction_script": panel,
            "draft_script": master,
            "final_script": master,
            "reenactment_character_script": render_reenactment_character_script(
                screenplay,
                characters,
                relationships,
                profile,
            ),
        }
    )
    return artifacts


def test_complete_presentation_contract_passes() -> None:
    """v2 Cast, Reaction, Timeline, Layer와 Broadcast Master는 모두 통과한다."""
    artifacts = make_complete_project_artifacts()

    assert presentation_design_issues(artifacts) == []
    assert script_integrity_issues(artifacts) == []
    ratio = actual_panel_reaction_ratio(document(artifacts, "presentation_plan"))
    assert ratio == 0.2


def test_state_transition_is_required_only_after_scene_design() -> None:
    """GATE-06은 빈 Scene 참조를 검사하지 않고 GATE-07에서 Transition을 요구한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    config = document(artifacts, "production_config")
    config["script_source_mode"] = "SCREENPLAY_UNITS"

    gate_six_issues = direct_gate_issues(artifacts, "GATE-06")
    gate_seven_issues = direct_gate_issues(artifacts, "GATE-07")

    assert not any(
        issue["artifact"] == "character_state_transitions"
        or issue["artifact"] == "05_STORY/character_state_transitions.json"
        for issue in gate_six_issues
    )
    assert any(
        issue["code"] == "REQUIRED_CHANNEL_ARTIFACT_MISSING"
        and issue["artifact"] == "character_state_transitions"
        for issue in gate_seven_issues
    )


@pytest.mark.parametrize(
    ("reference_field", "expected_code"),
    (
        ("fact_ids", "SCREENPLAY_FACT_REFERENCE_UNKNOWN"),
        ("clue_ids", "SCREENPLAY_CLUE_REFERENCE_UNKNOWN"),
        ("crime_event_ids", "SCREENPLAY_EVENT_REFERENCE_UNKNOWN"),
        ("harm_ids", "SCREENPLAY_HARM_REFERENCE_UNKNOWN"),
        (
            "development_function_ids",
            "SCREENPLAY_DEVELOPMENT_FUNCTION_REFERENCE_UNKNOWN",
        ),
        ("reveal_target_ids", "SCREENPLAY_REVEAL_TARGET_REFERENCE_UNKNOWN"),
    ),
)
def test_gate_eight_rejects_every_unknown_screenplay_reference_family(
    reference_field: str,
    expected_code: str,
) -> None:
    """GATE-08은 모든 Unit 상위 참조 Family를 안정된 코드로 거부한다."""
    artifacts = new_mode_gate_artifacts()
    screenplay = document(artifacts, "screenplay_units")
    scenes = screenplay["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    units = scene["units"]
    assert isinstance(units, list)
    unit = units[0]
    assert isinstance(unit, dict)
    references = unit["references"]
    assert isinstance(references, dict)
    references[reference_field] = ["UNKNOWN-99"]

    assert expected_code in issue_codes(direct_gate_issues(artifacts, "GATE-08"))


def test_panel_cast_speaker_function_and_ratio_failures_are_reported() -> None:
    """Cast·화자·기능·실제 시간 비율 위반을 각각 보고한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    cast_document = document(artifacts, "panel_cast")
    panelists = cast_document["panelists"]
    assert isinstance(panelists, list)
    cast_document["panelists"] = panelists[:1]
    reaction_document = document(artifacts, "reaction_segments")
    reactions = reaction_document["reaction_segments"]
    assert isinstance(reactions, list)
    for reaction in reactions:
        assert isinstance(reaction, dict)
        turns = reaction["turns"]
        assert isinstance(turns, list)
        for turn in turns:
            assert isinstance(turn, dict)
            turn["panelist_id"] = "PANEL-99"
            turn["function"] = "EMOTIONAL_REACTION"
    plan = document(artifacts, "presentation_plan")
    segments = plan["segments"]
    assert isinstance(segments, list)
    first_segment = segments[0]
    assert isinstance(first_segment, dict)
    first_segment["duration_sec"] = 200

    codes = issue_codes(presentation_design_issues(artifacts))

    assert {
        "PANEL_CAST_MISSING",
        "PANEL_SPEAKER_INVALID",
        "PANEL_REACTION_FUNCTION_MISSING",
        "PANEL_REACTION_RATIO_OUT_OF_RANGE",
    } <= codes


def test_panel_cast_requires_distinct_function_profiles() -> None:
    """Persona가 달라도 기능 구성이 같으면 별도 Panel 역할로 인정하지 않는다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    cast_document = document(artifacts, "panel_cast")
    panelists = cast_document["panelists"]
    assert isinstance(panelists, list)
    first = panelists[0]
    assert isinstance(first, dict)
    functions = first["allowed_functions"]
    for panelist in panelists:
        assert isinstance(panelist, dict)
        panelist["allowed_functions"] = deepcopy(functions)

    assert "PANEL_CAST_MISSING" in issue_codes(presentation_design_issues(artifacts))


def test_missing_panel_reaction_segments_are_reported() -> None:
    """실제 Reaction이 없으면 수동 모드 선언과 무관하게 실패한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    reaction_document = document(artifacts, "reaction_segments")
    reaction_document["reaction_segments"] = []

    codes = issue_codes(presentation_design_issues(artifacts))

    assert "PANEL_REACTION_SEGMENT_MISSING" in codes


def test_required_gates_independently_reject_missing_panel_reactions() -> None:
    """GATE-07·08·12·13은 선행 Gate 결과에 기대지 않고 Reaction 누락을 거부한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    reaction_document = document(artifacts, "reaction_segments")
    reaction_document["reaction_segments"] = []

    for gate_id in ("GATE-07", "GATE-08", "GATE-12", "GATE-13"):
        assert "PANEL_REACTION_SEGMENT_MISSING" in issue_codes(
            direct_gate_issues(artifacts, gate_id)
        )


def test_reaction_evidence_knowledge_and_hypothesis_boundaries_fail() -> None:
    """미공개 정보·잘못된 단서·무변화 가설·인물 행동 혼용을 차단한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    clue_matrix = document(artifacts, "clue_matrix")
    clues = clue_matrix["clues"]
    assert isinstance(clues, list)
    clues.append(
        {
            "clue_id": "CLUE-03",
            "role": "SUPPORTING",
            "introduced_scene_order": 2,
            "introduced_scene_id": "SCN-02",
        }
    )
    reaction_document = document(artifacts, "reaction_segments")
    reactions = reaction_document["reaction_segments"]
    assert isinstance(reactions, list)
    first = reactions[0]
    assert isinstance(first, dict)
    turns = first["turns"]
    assert isinstance(turns, list)
    first_turn = turns[0]
    assert isinstance(first_turn, dict)
    first_turn["evidence_ids"] = ["CLUE-03", "CLUE-99"]
    first_turn["known_fact_ids"] = ["FACT-02"]
    first["hypothesis_after"] = first["hypothesis_before"]
    first_turn["spoken_line"] = "그는 고개를 숙이고 침묵한다."

    codes = issue_codes(presentation_design_issues(artifacts))

    assert {
        "REACTION_EVIDENCE_REFERENCE_BROKEN",
        "REACTION_EVIDENCE_NOT_YET_REVEALED",
        "REACTION_KNOWLEDGE_BOUNDARY_VIOLATION",
        "REACTION_HYPOTHESIS_DELTA_MISSING",
        "CHARACTER_REACTION_MISLABELED_AS_PANEL",
    } <= codes


def test_broadcast_master_missing_duplicate_order_and_duration_failures() -> None:
    """Broadcast Master의 누락·중복·순서·시간 Marker 오류를 차단한다."""
    artifacts = make_complete_project_artifacts()
    plan = document(artifacts, "presentation_plan")
    final_script = text_artifact(artifacts, "final_script")
    segment_two_start = final_script.index("<!-- SEGMENT:SEG-002 ")
    segment_two_end_marker = "<!-- END_SEGMENT:SEG-002 -->"
    segment_two_end = final_script.index(segment_two_end_marker) + len(segment_two_end_marker)
    segment_two = final_script[segment_two_start:segment_two_end]
    without_segment_two = final_script[:segment_two_start] + final_script[segment_two_end:]

    missing_codes = issue_codes(
        script_segment_alignment_issues(plan, without_segment_two)
    )
    duplicated_codes = issue_codes(
        script_segment_alignment_issues(plan, final_script + "\n\n" + segment_two)
    )
    duration_codes = issue_codes(
        script_segment_alignment_issues(
            plan,
            final_script.replace("DURATION:32", "DURATION:31", 1),
        )
    )
    malformed_codes = issue_codes(
        script_segment_alignment_issues(plan, "완성 Marker가 없는 Treatment")
    )

    assert {
        "PRESENTATION_SEGMENT_MISSING_IN_FINAL_SCRIPT",
        "PRESENTATION_SEGMENT_ORDER_MISMATCH",
    } <= missing_codes
    assert "PRESENTATION_SEGMENT_DUPLICATED" in duplicated_codes
    assert "PRESENTATION_DURATION_MISMATCH" in duration_codes
    assert "FINAL_SCRIPT_NOT_BROADCAST_MASTER" in malformed_codes


def test_integrated_draft_requires_all_presentation_segments() -> None:
    """구조 메모만 있는 Draft는 통합 대본으로 인정하지 않는다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    artifacts["draft_script"] = (
        "<!-- SEGMENT:SEG-001 TYPE:DRAMA SCENE:SCN-01 DURATION:100 -->\n"
        "나머지 Segment는 Final에서 통합한다.\n"
        "<!-- END_SEGMENT:SEG-001 -->"
    )

    codes = issue_codes(script_integrity_issues(artifacts))

    assert "PRESENTATION_SEGMENT_MISSING_IN_FINAL_SCRIPT" in codes


def test_layer_duplication_and_audience_belief_mismatch_are_reported() -> None:
    """Narration 중복과 Viewer 공개 시점보다 이른 Fact 공개를 차단한다."""
    artifacts = make_complete_project_artifacts()
    drama = text_artifact(artifacts, "drama_script")
    panel = text_artifact(artifacts, "panel_reaction_script")
    drama_line = "[FACT:FACT-01] 지안은 기계 로그에서 7분의 공백을 발견한다."
    panel_line = "[PANEL-01] “7분의 공백이 이탈의 증거인지부터 확인해야 합니다.”"
    duplication_codes = issue_codes(
        narration_duplication_issues(
            drama,
            f"{drama_line}\n{panel_line}",
            panel,
        )
    )
    plan = deepcopy(document(artifacts, "presentation_plan"))
    segments = plan["segments"]
    assert isinstance(segments, list)
    first_segment = segments[0]
    assert isinstance(first_segment, dict)
    first_segment["revealed_fact_ids"] = ["FACT-02"]
    audience_codes = issue_codes(
        audience_belief_alignment_issues(
            plan,
            text_artifact(artifacts, "final_script"),
            document(artifacts, "scene_cards"),
            document(artifacts, "viewer_timeline"),
            document(artifacts, "audience_belief"),
        )
    )

    assert {
        "NARRATION_VISIBLE_ACTION_DUPLICATION",
        "NARRATION_REACTION_DUPLICATION",
    } <= duplication_codes
    assert "AUDIENCE_BELIEF_SCRIPT_MISMATCH" in audience_codes


def test_absolute_time_monotonicity_and_timeline_alignment_fail() -> None:
    """현재 시각 역행과 구조 완료 시각의 Timeline 불일치를 함께 보고한다."""
    timeline: dict[str, object] = {
        "events": [
            {
                "start_minute": 0,
                "description": "현재 사건은 21시 49분에 시작한다.",
            },
            {
                "start_minute": 10,
                "description": "구조 완료 사건",
            },
        ]
    }

    codes = issue_codes(
        absolute_time_issues(
            "21:49 현장 진입. 구조 완료 시각은 21:03이다.",
            timeline,
        )
    )

    assert {
        "ABSOLUTE_TIME_MONOTONICITY_ERROR",
        "SCRIPT_TIMELINE_ALIGNMENT_ERROR",
    } <= codes


def test_rescue_completion_uses_action_end_not_rescue_team_start() -> None:
    """구조팀 준비가 아니라 실제 구조 행동의 종료 시각을 기준으로 삼는다."""
    timeline: dict[str, object] = {
        "events": [
            {
                "start_minute": 0,
                "end_minute": 2,
                "description": "21시 41분 점검 무전을 보낸다.",
            },
            {
                "start_minute": 16,
                "end_minute": 19,
                "description": "구조팀이 점검 해치를 찾는다.",
            },
            {
                "start_minute": 19,
                "end_minute": 23,
                "description": "구조팀이 고립자를 구조한다.",
            },
            {
                "start_minute": 23,
                "end_minute": 25,
                "description": "22시 03분 구조 사고로 정정한다.",
            },
        ]
    }

    issues = absolute_time_issues(
        "구조 완료 시각은 22시 03분입니다.",
        timeline,
    )

    assert issues == []


def test_production_cues_must_preserve_reaction_and_segment_ids() -> None:
    """Production Panel Cue와 Edit Script에서 계약 ID 누락을 차단한다."""
    artifacts = make_complete_project_artifacts()

    codes = issue_codes(
        validate_production_presentation(
            document(artifacts, "presentation_plan"),
            document(artifacts, "reaction_segments"),
            "",
            "SEG-001만 존재",
        )
    )

    assert {
        "PANEL_REACTION_SEGMENT_MISSING",
        "PRESENTATION_SEGMENT_MISSING_IN_FINAL_SCRIPT",
    } <= codes


def test_edit_script_requires_exact_presentation_timecodes() -> None:
    """ID만 있거나 잘못된 구간을 적은 Edit Script를 차단한다."""
    artifacts = make_complete_project_artifacts()
    presentation_plan = document(artifacts, "presentation_plan")
    reaction_segments = document(artifacts, "reaction_segments")
    production_panel_script = text_artifact(
        artifacts,
        "production_panel_reaction_script",
    )

    missing_codes = issue_codes(
        validate_production_presentation(
            presentation_plan,
            reaction_segments,
            production_panel_script,
            "SEG-001 SEG-002 SEG-003 SEG-004 SEG-005 SEG-006",
        )
    )
    wrong_timecodes = text_artifact(artifacts, "edit_script").replace(
        "SEG-001 | 00:00-00:32",
        "SEG-001 | 00:01-00:33",
    )
    mismatch_codes = issue_codes(
        validate_production_presentation(
            presentation_plan,
            reaction_segments,
            production_panel_script,
            wrong_timecodes,
        )
    )

    assert "EDIT_TIMECODE_MISMATCH" in missing_codes
    assert "EDIT_TIMECODE_MISMATCH" in mismatch_codes

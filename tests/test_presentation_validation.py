"""Presentation Contract v2의 구조·대본·제작 검증."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import cast

from project_factory import make_complete_project_artifacts

from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
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
        load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"),
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
        text_artifact(artifacts, "draft_script"),
        text_artifact(artifacts, "final_script"),
    )


def test_complete_presentation_contract_passes() -> None:
    """v2 Cast, Reaction, Timeline, Layer와 Broadcast Master는 모두 통과한다."""
    artifacts = make_complete_project_artifacts()

    assert presentation_design_issues(artifacts) == []
    assert script_integrity_issues(artifacts) == []
    ratio = actual_panel_reaction_ratio(document(artifacts, "presentation_plan"))
    assert ratio == 0.2


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
        reaction["panelist_id"] = "PANEL-99"
        reaction["function"] = "EMOTIONAL_REACTION"
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


def test_missing_panel_reaction_segments_are_reported() -> None:
    """실제 Reaction이 없으면 수동 모드 선언과 무관하게 실패한다."""
    artifacts = deepcopy(make_complete_project_artifacts())
    reaction_document = document(artifacts, "reaction_segments")
    reaction_document["reaction_segments"] = []

    codes = issue_codes(presentation_design_issues(artifacts))

    assert "PANEL_REACTION_SEGMENT_MISSING" in codes


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
    first["evidence_ids"] = ["CLUE-03", "CLUE-99"]
    first["known_fact_ids"] = ["FACT-02"]
    first["hypothesis_after"] = first["hypothesis_before"]
    first["spoken_line"] = "그는 고개를 숙이고 침묵한다."

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


def test_layer_duplication_and_audience_belief_mismatch_are_reported() -> None:
    """Narration 중복과 Viewer 공개 시점보다 이른 Fact 공개를 차단한다."""
    artifacts = make_complete_project_artifacts()
    drama = text_artifact(artifacts, "drama_script")
    panel = text_artifact(artifacts, "panel_reaction_script")
    drama_line = "[FACT:FACT-01] 지안은 기계 로그에서 7분의 공백을 발견한다."
    panel_line = "7분의 공백이 이탈의 증거인지부터 확인해야 합니다."
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

"""Channel DNA 2.1 Scene Realization Framework 회귀 검증."""

from copy import deepcopy
from pathlib import Path
from typing import cast

from VALIDATORS.editorial import (
    make_editorial_evidence,
    validate_editorial_realization_evidence,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
from VALIDATORS.scene_realization import (
    REQUIRED_STAGE_TYPES,
    build_script_realization_report,
    channel_realization_evidence,
    validate_channel_realization_evidence,
    validate_narration_realization,
    validate_panel_design_realization,
    validate_panel_script_density,
    validate_primary_story_engine,
    validate_psychological_arc,
    validate_scene_coverage,
    validate_script_realization,
    validate_script_realization_report,
)
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = load_json_object(
    ROOT / "CHANNELS" / "mystery_main" / "versions" / "2.1.0" / "channel_dna.json"
)


def issue_codes(issues: list[ValidationIssue]) -> set[str]:
    """Issue 배열에서 오류 코드만 반환한다."""
    return {issue["code"] for issue in issues}


def psychological_arc() -> dict[str, object]:
    """아홉 Stage가 순서대로 상태를 바꾸는 Arc를 만든다."""
    return {
        "schema_family": "psychological-arc",
        "schema_version": "1.0.0",
        "project_id": "PRJ-901",
        "primary_story_engine": "CRIME_PSYCHOLOGICAL_ESCALATION",
        "stages": [
            {
                "stage_id": f"PSTAGE-{index:03d}",
                "order": index,
                "stage_type": stage_type,
                "actor_id": "CHAR-01",
                "subject_id": "CHAR-02",
                "state_before": f"상태 {index - 1}",
                "state_after": f"상태 {index}",
                "experience_goal": f"관객이 {stage_type} 변화를 인물과 함께 체험한다.",
                "required_drama_evidence": True,
            }
            for index, stage_type in enumerate(REQUIRED_STAGE_TYPES, start=1)
        ],
    }


def scene_cards() -> dict[str, object]:
    """각 Stage를 별도 Drama Scene에 배치한다."""
    return {
        "project_id": "PRJ-901",
        "scenes": [
            {
                "scene_id": f"SCN-{index:02d}",
                "order": index,
                "beat_id": f"BEAT-{index:02d}",
                "estimated_seconds": 30,
                "clue_ids": [],
                "knowledge_claims": [],
                "psychological_realization": [
                    {
                        "stage_id": f"PSTAGE-{index:03d}",
                        "stage_type": stage_type,
                        "trace_ids": [f"TRACE-{index:02d}"],
                        "actor_id": "CHAR-01",
                        "subject_id": "CHAR-02",
                        "state_before": f"상태 {index - 1}",
                        "state_after": f"상태 {index}",
                        "on_screen_evidence": f"인물의 선택이 {stage_type} 상태 변화를 드러낸다.",
                        "satisfaction_mode": (
                            "DRAMA_REQUIRED"
                            if stage_type
                            in {
                                "BOUNDARY_EROSION",
                                "CONTROL_OR_DEPENDENCY",
                                "HARM_OR_CRIME",
                                "AGENCY_RECOVERY",
                            }
                            else "DRAMA"
                        ),
                    }
                ],
            }
            for index, stage_type in enumerate(REQUIRED_STAGE_TYPES, start=1)
        ],
    }


def presentation_plan() -> dict[str, object]:
    """모든 Stage를 Drama Segment에 직접 연결한다."""
    segments: list[dict[str, object]] = []
    start = 0
    for index, stage_type in enumerate(REQUIRED_STAGE_TYPES, start=1):
        segments.append(
            {
                "segment_id": f"SEG-{index:03d}",
                "segment_type": "DRAMA",
                "scene_id": f"SCN-{index:02d}",
                "start_sec": start,
                "duration_sec": 30,
                "source_artifact": "drama_script",
                "revealed_fact_ids": ["FACT-01"] if index == 1 else [],
                "revealed_clue_ids": [],
                "psychological_stage_ids": [f"PSTAGE-{index:03d}"],
                "psychological_stage_types": [stage_type],
            }
        )
        start += 30
    segments.append(
        {
            "segment_id": "SEG-010",
            "segment_type": "NARRATION",
            "scene_id": "SCN-09",
            "start_sec": start,
            "duration_sec": 10,
            "source_artifact": "narration_script",
            "revealed_fact_ids": [],
            "revealed_clue_ids": [],
            "referenced_fact_ids": [],
            "referenced_clue_ids": [],
            "narration_function": "CHARACTER_ANCHOR",
        }
    )
    return {
        "schema_family": "presentation-plan",
        "schema_version": "2.1.0",
        "project_id": "PRJ-901",
        "modes": ["DRAMA", "NARRATION", "PANEL_REACTION"],
        "segments": segments,
    }


def final_script() -> str:
    """Stage와 Trace Tag가 실제 Drama Segment에 있는 Script를 만든다."""
    return "\n\n".join(
        (
            f"<!-- SEGMENT:SEG-{index:03d} TYPE:DRAMA SCENE:SCN-{index:02d} "
            "DURATION:30 -->\n"
            f"[PSY_STAGE:PSTAGE-{index:03d}] [PSY_TRACE:TRACE-{index:02d}]\n"
            f"인물은 설명 대신 행동으로 {stage_type}의 변화를 겪는다.\n"
            f"<!-- END_SEGMENT:SEG-{index:03d} -->"
        )
        for index, stage_type in enumerate(REQUIRED_STAGE_TYPES, start=1)
    )


def reaction_segments() -> dict[str, object]:
    """필수 정서 기능과 실제 응답 연결이 있는 Panel 설계를 만든다."""
    functions = (
        "EMOTIONAL_REACTION",
        "RISK_SIGNAL_RECOGNITION",
        "VICTIM_CONTEXTUALIZATION",
        "BELIEF_CORRECTION",
    )
    return {
        "schema_family": "reaction-segments",
        "schema_version": "2.1.0",
        "project_id": "PRJ-901",
        "reaction_segments": [
            {
                "reaction_segment_id": "RSEG-001",
                "after_scene_id": "SCN-09",
                "order": 1,
                "start_sec": 280,
                "duration_sec": 10,
                "segment_function": "EMOTIONAL_REACTION",
                "hypothesis_before": "피해자가 고립되어 있다.",
                "hypothesis_after": "피해자가 위험을 인식하고 있다.",
                "tone": "EMPATHETIC",
                "turns": [
                    {
                        "turn_id": f"TURN-001-{index:02d}",
                        "panelist_id": f"PANEL-{1 + index % 2:02d}",
                        "function": function,
                        "spoken_line": (
                            "지금 이 선택은 작은 반응처럼 보여도 인물이 위험을 "
                            "알아차리고 자기 경계를 되찾는 중요한 순간입니다."
                        ),
                        "evidence_ids": [],
                        "known_fact_ids": [],
                        "tone": "EMPATHETIC",
                        **(
                            {"responds_to_turn_id": f"TURN-001-{index - 1:02d}"}
                            if index > 1
                            else {}
                        ),
                    }
                    for index, function in enumerate(functions, start=1)
                ],
            }
        ],
    }


def panel_script() -> str:
    """계획시간의 40% 이상을 실제 발화로 채운 Panel Script를 만든다."""
    return (
        "[RSEG-001] [PANEL-02] [EMOTIONAL_REACTION]\n"
        "[PANEL-02] “지금 이 선택은 작은 반응처럼 보여도 인물이 위험을 알아차리고 "
        "자기 경계를 되찾는 중요한 순간입니다.”\n"
        "[PANEL-01] “저도 그렇게 봐요 이제는 피해자의 망설임보다 그 망설임을 만든 "
        "통제와 두려움을 먼저 봐야 합니다.”\n"
    )


def test_complete_realization_bundle_passes() -> None:
    """Arc, Scene, Script, Report와 Channel Evidence가 모두 결속되면 통과한다."""
    arc = psychological_arc()
    scenes = scene_cards()
    plan = presentation_plan()
    script = final_script()
    reactions = reaction_segments()
    report = build_script_realization_report(
        "PRJ-901",
        CHANNEL,
        arc,
        scenes,
        plan,
        script,
    )
    channel_report = {
        "project_id": "PRJ-901",
        "result": "PASS",
        "issues": [],
        "scene_realization_evidence": channel_realization_evidence(report),
    }

    assert validate_psychological_arc(CHANNEL, arc) == []
    assert validate_scene_coverage(CHANNEL, arc, scenes, plan) == []
    assert validate_narration_realization(CHANNEL, plan) == []
    assert validate_panel_design_realization(CHANNEL, reactions, plan) == []
    assert validate_panel_script_density(CHANNEL, reactions, panel_script()) == []
    assert validate_script_realization(CHANNEL, arc, scenes, plan, script) == []
    assert validate_script_realization_report(
        CHANNEL,
        arc,
        scenes,
        plan,
        script,
        report,
    ) == []
    assert validate_channel_realization_evidence(
        CHANNEL,
        arc,
        report,
        channel_report,
    ) == []


def test_realization_artifacts_match_their_schemas() -> None:
    """Psychological Arc와 재계산 가능한 Report가 신규 Schema를 따른다."""
    arc = psychological_arc()
    report = build_script_realization_report(
        "PRJ-901",
        CHANNEL,
        arc,
        scene_cards(),
        presentation_plan(),
        final_script(),
    )
    arc_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "psychological_arc.schema.json"
    )
    report_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "script_realization_report.schema.json"
    )

    assert collect_schema_errors(arc, arc_schema, "psychological_arc") == []
    assert collect_schema_errors(
        report,
        report_schema,
        "script_realization_report",
    ) == []


def test_editorial_requires_every_stage_realization_reference() -> None:
    """GATE-13 Review는 Report의 아홉 Stage를 독립 Evidence로 인용해야 한다."""
    arc = psychological_arc()
    report = build_script_realization_report(
        "PRJ-901",
        CHANNEL,
        arc,
        scene_cards(),
        presentation_plan(),
        final_script(),
    )
    artifacts: dict[str, object] = {"script_realization_report": report}
    evidence = [
        make_editorial_evidence(
            artifacts,
            "script_realization_report",
            "PSYCHOLOGICAL_STAGE_ID",
            f"PSTAGE-{index:03d}",
        )
        for index in range(1, 10)
    ]
    review = {"checks": {"victim_dignity": {"evidence": evidence}}}

    assert validate_editorial_realization_evidence(CHANNEL, review, arc) == []
    evidence.pop()
    assert "EDITORIAL_REALIZATION_EVIDENCE_MISSING" in issue_codes(
        validate_editorial_realization_evidence(CHANNEL, review, arc)
    )


def test_first_narration_premature_solution_clue_fails() -> None:
    """첫 Narration이 미공개 해결 단서를 언급하면 실패한다."""
    plan = presentation_plan()
    segments = cast(list[dict[str, object]], plan["segments"])
    narration = deepcopy(segments[-1])
    narration["segment_id"] = "SEG-000"
    narration["referenced_clue_ids"] = ["CLUE-99"]
    plan["segments"] = [narration, *segments[:-1]]

    assert "NARRATION_PREMATURE_REVEAL" in issue_codes(
        validate_narration_realization(CHANNEL, plan)
    )


def test_crime_psychology_trace_absent_from_script_fails() -> None:
    """JSON Trace가 있어도 Final Script에 Tag가 없으면 실패한다."""
    script = final_script().replace("[PSY_TRACE:TRACE-04]", "")

    assert "CRIME_PSYCHOLOGY_TRACE_UNREALIZED" in issue_codes(
        validate_script_realization(
            CHANNEL,
            psychological_arc(),
            scene_cards(),
            presentation_plan(),
            script,
        )
    )


def test_critical_stage_requires_explicit_drama_required_mode() -> None:
    """Critical Stage의 일반 DRAMA 표기는 강화된 Scene 계약을 충족하지 못한다."""
    scenes = scene_cards()
    records = cast(list[dict[str, object]], scenes["scenes"])
    realization = cast(list[dict[str, object]], records[3]["psychological_realization"])[0]
    realization["satisfaction_mode"] = "DRAMA"

    assert "CRITICAL_STAGE_UNREALIZED" in issue_codes(
        validate_scene_coverage(
            CHANNEL,
            psychological_arc(),
            scenes,
            presentation_plan(),
        )
    )


def test_state_delta_absence_fails_realization_report() -> None:
    """Script Tag가 있어도 Stage 상태 변화가 없으면 Report가 PASS할 수 없다."""
    arc = psychological_arc()
    stages = cast(list[dict[str, object]], arc["stages"])
    stages[0]["state_after"] = stages[0]["state_before"]
    report = build_script_realization_report(
        "PRJ-901",
        CHANNEL,
        arc,
        scene_cards(),
        presentation_plan(),
        final_script(),
    )

    assert report["result"] == "FAIL"
    realization_score = report["realization_score"]
    assert isinstance(realization_score, int | float)
    assert realization_score < 100


def test_panel_fifty_seconds_with_under_ten_seconds_spoken_fails() -> None:
    """50초 Panel에 짧은 발화만 있으면 Spoken Density가 실패한다."""
    reactions = reaction_segments()
    record = cast(list[dict[str, object]], reactions["reaction_segments"])[0]
    record["duration_sec"] = 50
    short_script = (
        "[RSEG-001] [PANEL-02] [EMOTIONAL_REACTION]\n"
        "[PANEL-02] “위험해 보여요.”\n"
    )

    assert "PANEL_SPOKEN_DENSITY_LOW" in issue_codes(
        validate_panel_script_density(CHANNEL, reactions, short_script)
    )


def test_panel_density_counts_the_entire_reaction_section() -> None:
    """긴 무대 지시 뒤의 발화도 해당 Reaction Segment의 밀도에 포함한다."""
    reactions = reaction_segments()
    record = cast(list[dict[str, object]], reactions["reaction_segments"])[0]
    record["duration_sec"] = 50
    long_script = (
        "[RSEG-001] [PANEL-02] [EMOTIONAL_REACTION]\n"
        f"[무대 지시] {'감정 반응을 기다린다 ' * 20}\n"
        f"[PANEL-02] “{'위험 신호와 피해자의 선택을 함께 바라본다 ' * 15}”\n"
    )

    assert validate_panel_script_density(CHANNEL, reactions, long_script) == []


def test_three_mechanical_drama_narration_panel_cycles_fail() -> None:
    """고정 D→N→P 순환이 세 번 반복되면 실패한다."""
    modes = ["DRAMA", "NARRATION", "PANEL_REACTION"] * 3
    plan = {
        "segments": [
            {"segment_id": f"SEG-{index:03d}", "segment_type": mode}
            for index, mode in enumerate(modes, start=1)
        ]
    }

    assert "PRESENTATION_MECHANICAL_CYCLE_REPETITION" in issue_codes(
        validate_panel_design_realization(CHANNEL, reaction_segments(), plan)
    )


def test_adjacent_narration_and_panel_clue_explanation_duplication_fails() -> None:
    """Narration과 인접 Panel이 같은 단서를 설명하면 실패한다."""
    plan = presentation_plan()
    segments = cast(list[dict[str, object]], plan["segments"])
    segments[0]["revealed_clue_ids"] = ["CLUE-01"]
    segments[-1]["referenced_clue_ids"] = ["CLUE-01"]
    segments.append(
        {
            "segment_id": "SEG-011",
            "segment_type": "PANEL_REACTION",
            "scene_id": "SCN-09",
            "start_sec": 280,
            "duration_sec": 10,
            "source_artifact": "panel_reaction_script",
            "revealed_fact_ids": [],
            "revealed_clue_ids": [],
            "referenced_fact_ids": [],
            "referenced_clue_ids": ["CLUE-01"],
        }
    )

    assert "NARRATION_PANEL_DUPLICATION" in issue_codes(
        validate_narration_realization(CHANNEL, plan)
    )


def test_object_location_primary_engine_fails() -> None:
    """사물 위치 질문만 Primary Engine으로 두면 실패한다."""
    story = {
        "story_dna": {
            "primary_story_engine": "OBJECT_WHEREABOUTS",
            "mystery_priority": "PRIMARY",
            "central_question_type": "WHERE_IS_OBJECT",
        }
    }

    assert "OBJECT_PUZZLE_DOMINANCE" in issue_codes(
        validate_primary_story_engine(CHANNEL, story, {})
    )


def test_channel_consistency_without_scene_evidence_fails() -> None:
    """PASS 문자열만 있는 Channel QA Report는 2.1을 통과하지 못한다."""
    report = build_script_realization_report(
        "PRJ-901",
        CHANNEL,
        psychological_arc(),
        scene_cards(),
        presentation_plan(),
        final_script(),
    )

    assert "CHANNEL_REALIZATION_EVIDENCE_MISSING" in issue_codes(
        validate_channel_realization_evidence(
            CHANNEL,
            psychological_arc(),
            report,
            {"project_id": "PRJ-901", "result": "PASS", "issues": []},
        )
    )


def test_channel_2_0_does_not_receive_realization_rules() -> None:
    """동일한 실패 입력도 Channel 2.0에는 소급 적용하지 않는다."""
    channel_v2 = load_json_object(
        ROOT
        / "CHANNELS"
        / "mystery_main"
        / "versions"
        / "2.0.0"
        / "channel_dna.json"
    )

    assert validate_psychological_arc(channel_v2, {}) == []
    assert validate_scene_coverage(channel_v2, {}, {}, {}) == []
    assert validate_script_realization(channel_v2, {}, {}, {}, "") == []

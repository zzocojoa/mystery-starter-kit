"""Channel 2.1 사건 실현·Reveal·Editorial 경계 회귀 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.crime_event import (
    build_crime_script_realization_report,
    canonical_json_hash,
    required_semantic_subjects,
    validate_candidate_crime_event,
    validate_crime_event_contract,
    validate_crime_script_realization_report,
    validate_script_crime_realization,
)
from VALIDATORS.editorial import (
    explicit_crime_runtime_evidence_issues,
    make_editorial_evidence,
    validate_editorial_crime_assessments,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ValidationIssue
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = load_json_object(ROOT / "CHANNELS/mystery_main/versions/2.1.0/channel_dna.json")


def issue_codes(issues: list[ValidationIssue]) -> set[str]:
    """Issue 배열에서 오류 코드만 반환한다."""
    return {issue["code"] for issue in issues}


def event_outline(primary_crime: str = "ASSAULT") -> dict[str, object]:
    """실제 행동·피해·후반 공개가 있는 사건 개요를 만든다."""
    action = "MURDER" if primary_crime == "MURDER" else primary_crime
    harm = "FATALITY" if primary_crime == "MURDER" else "BODILY_INJURY"
    functions = (
        [
            "HARM_OR_DANGER_RECOGNITION",
            "INVOLVEMENT_OR_SUSPICION",
            "MOTIVE_AND_RESPONSIBILITY",
            "EVENT_RECONSTRUCTION",
        ]
        if primary_crime == "MURDER"
        else [
            "VIOLENCE_OR_THREAT",
            "RELATIONSHIP_AND_POWER",
            "RESPONSE_BARRIER",
            "VIOLENCE_OUTCOME",
        ]
    )
    return {
        "event_id": "EVENT-01",
        "primary_crime": primary_crime,
        "related_crimes": [],
        "core_action_type": action,
        "relationship_context": "ACQUAINTANCE",
        "actor_ids": ["CHAR-01"],
        "victim_ids": ["CHAR-02"],
        "motive": "RETALIATION",
        "act_summary": "행위자의 비선정적 대인 폭력이 피해자의 상태를 바꾼다.",
        "harm_ids": ["HARM-01"],
        "harm_result": "구체적인 피해 결과가 남는다.",
        "harm_classifications": [harm],
        "protagonist_goal": "SURVIVE_OR_ESCAPE",
        "protagonist_risk": "PHYSICAL_HARM",
        "depiction_mode": "IMPLIED",
        "non_actionable_method_summary": "행위자가 퇴로를 막고 비선정적 폭력을 가했다.",
        "immediate_harm": "피해자는 치료가 필요한 상해를 입었다.",
        "lasting_harm": "피해자는 일상 공간에 돌아가지 못하는 불안을 겪었다.",
        "development_functions": [
            {
                "development_function_id": f"CDEV-{index:03d}",
                "function_type": function,
                "summary": f"{function} 기능을 행동과 결과로 구현한다.",
                "required": True,
            }
            for index, function in enumerate(functions, 1)
        ],
        "reveal_targets": [
            {
                "reveal_target_id": f"REVEAL-TARGET-{index:02d}",
                "target_type": target_type,
                "summary": f"{target_type} 공개",
                "planned_phase": "LATE",
                "planned_segment_id": None,
            }
            for index, target_type in enumerate(
                ("CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"),
                1,
            )
        ],
        "method_detail_level": "NON_ACTIONABLE_SUMMARY_ONLY",
        "centrality": "CENTRAL",
        "truth_status": "ORIGINAL_FICTION",
    }


def crime_contract(primary_crime: str = "ASSAULT") -> dict[str, object]:
    """Candidate와 결속된 창작 사건 계약을 만든다."""
    event = event_outline(primary_crime)
    return {
        "schema_family": "crime-event-contract",
        "schema_version": "1.0.0",
        "project_id": "PRJ-901",
        "approved_candidate_id": "VAR-01",
        "candidate_event_sha256": canonical_json_hash(event),
        **{
            key: deepcopy(value)
            for key, value in event.items()
            if key not in {"centrality", "truth_status"}
        },
        "truth_basis": {
            "source_truth_classification": "ORIGINAL_FICTION",
            "status": "ORIGINAL_FICTION",
            "source_fact_ids": [],
            "unknown_fields": [],
        },
    }


def presentation_plan() -> dict[str, object]:
    """Narration·Panel·후반 Reveal을 포함한 여섯 Segment Plan을 만든다."""
    kinds = (
        ("DRAMA", "SCN-01", "drama_script"),
        ("PANEL_REACTION", "SCN-01", "panel_reaction_script"),
        ("NARRATION", "SCN-01", "narration_script"),
        ("PANEL_REACTION", "SCN-01", "panel_reaction_script"),
        ("DRAMA", "SCN-02", "drama_script"),
        ("PANEL_REACTION", "SCN-02", "panel_reaction_script"),
    )
    segments: list[dict[str, object]] = []
    for index, (kind, scene_id, source) in enumerate(kinds, 1):
        segment: dict[str, object] = {
            "segment_id": f"SEG-{index:03d}",
            "segment_type": kind,
            "scene_id": scene_id,
            "start_sec": (index - 1) * 30,
            "duration_sec": 30,
            "source_artifact": source,
            "revealed_fact_ids": [],
            "revealed_clue_ids": [],
            "referenced_reveal_target_ids": [],
            "revealed_reveal_target_ids": [],
            "intentional_prereveal_ids": [],
        }
        if kind == "PANEL_REACTION":
            segment["reaction_segment_id"] = f"RSEG-{index:03d}"
        if kind == "NARRATION":
            segment["narrator_character_id"] = "CHAR-02"
            segment["narration_function"] = "EMOTIONAL_CONTINUITY"
        if index == 5:
            segment["crime_development_function_ids"] = [
                "CDEV-001",
                "CDEV-002",
                "CDEV-003",
                "CDEV-004",
            ]
            segment["revealed_reveal_target_ids"] = [
                "REVEAL-TARGET-01",
                "REVEAL-TARGET-02",
            ]
        if index == 6:
            segment["revealed_reveal_target_ids"] = [
                "REVEAL-TARGET-03",
                "REVEAL-TARGET-04",
            ]
        segments.append(segment)
    return {
        "schema_family": "presentation-plan",
        "schema_version": "2.1.0",
        "project_id": "PRJ-901",
        "modes": ["DRAMA", "NARRATION", "PANEL_REACTION"],
        "segments": segments,
    }


def scene_cards() -> dict[str, object]:
    """사건 행동과 피해 변화를 SEG-005에 계획한다."""
    return {
        "project_id": "PRJ-901",
        "scenes": [
            {
                "scene_id": "SCN-01",
                "order": 1,
                "beat_id": "BEAT-01",
                "estimated_seconds": 90,
                "clue_ids": [],
                "knowledge_claims": [],
            },
            {
                "scene_id": "SCN-02",
                "order": 2,
                "beat_id": "BEAT-02",
                "estimated_seconds": 90,
                "clue_ids": [],
                "knowledge_claims": [],
                "crime_realization": [
                    {
                        "event_id": "EVENT-01",
                        "harm_ids": ["HARM-01"],
                        "actor_ids": ["CHAR-01"],
                        "victim_ids": ["CHAR-02"],
                        "realization_mode": "IMPLIED_ACTION",
                        "action_evidence": "문밖의 충격과 행위자의 움직임",
                        "dialogue_or_behavior_evidence": "피해자의 즉각적인 방어 행동",
                        "choice_or_emotion_change": "도주를 선택한다.",
                        "result_change": "신체 피해가 확인된다.",
                        "planned_segment_ids": ["SEG-005"],
                        "development_function_ids": [
                            "CDEV-001",
                            "CDEV-002",
                            "CDEV-003",
                            "CDEV-004",
                        ],
                        "expected_excerpt_anchor": "CRIME_EVENT Marker",
                    }
                ],
            },
        ],
    }


def reaction_segments() -> dict[str, object]:
    """감정 반응과 용의자 추적 기능을 함께 만든다."""
    return {
        "reaction_segments": [
            {
                "reaction_segment_id": "RSEG-002",
                "turns": [
                    {"function": "EMOTIONAL_REACTION"},
                    {"function": "HYPOTHESIS_REVISION"},
                ],
            }
        ]
    }


def viewer_timeline() -> dict[str, object]:
    """조기 공개 표시가 없는 Viewer Timeline을 만든다."""
    return {
        "project_id": "PRJ-901",
        "reveals": [{"reveal_id": "REV-01", "scene_id": "SCN-01", "fact_id": "FACT-01"}],
    }


def final_script() -> str:
    """SEG-005에 비선정적 암시 폭력과 사건 인과 Marker를 둔다."""
    bodies = {
        1: "피해자는 집 앞에서 반복되는 발소리를 듣는다.",
        2: "패널은 위험에 놀라고 용의자의 동선을 수정한다.",
        3: "나는 그때 그 발소리를 우연이라고 믿었다.",
        4: "패널은 앞선 판단을 다시 검토한다.",
        5: "<!-- CRIME_TRACE\nEVENT=EVENT-01\nACTION=ASSAULT\nHARM=HARM-01\n"
        "DEV=CDEV-001,CDEV-002,CDEV-003,CDEV-004\n-->\n"
        "행위자가 퇴로를 막고 비선정적 폭력을 가했다. "
        "피해자는 치료가 필요한 상해를 입었다. "
        "피해자는 일상 공간에 돌아가지 못하는 불안을 겪었다.",
        6: "패널은 범인, 동기, 방식과 피해 결과를 공개된 근거로 정리한다.",
    }
    kinds = ("DRAMA", "PANEL_REACTION", "NARRATION", "PANEL_REACTION", "DRAMA", "PANEL_REACTION")
    scenes = ("SCN-01", "SCN-01", "SCN-01", "SCN-01", "SCN-02", "SCN-02")
    return "\n\n".join(
        f"<!-- SEGMENT:SEG-{index:03d} TYPE:{kind} SCENE:{scene} DURATION:30 -->\n"
        f"{bodies[index]}\n<!-- END_SEGMENT:SEG-{index:03d} -->"
        for index, (kind, scene) in enumerate(zip(kinds, scenes, strict=True), 1)
    )


def test_murder_label_with_theft_action_is_rejected() -> None:
    """살인 Label에 절도 행동을 붙여 범죄 중심성을 가장할 수 없다."""
    candidate = {"candidate_id": "VAR-01", "crime_event": event_outline("MURDER")}
    candidate["crime_event"]["core_action_type"] = "THEFT"  # type: ignore[index]
    assert "EXPLICIT_CRIME_ACTION_MISSING" in issue_codes(
        validate_candidate_crime_event(CHANNEL, candidate)
    )


def test_scene_id_without_crime_action_is_rejected() -> None:
    """Scene ID와 장르 문구만 있고 사건 Marker·인과가 없으면 실패한다."""
    script = final_script().replace("EVENT=EVENT-01", "범죄 스릴러")
    codes = issue_codes(
        validate_script_crime_realization(
            CHANNEL,
            crime_contract(),
            scene_cards(),
            presentation_plan(),
            reaction_segments(),
            viewer_timeline(),
            script,
        )
    )
    assert "SCRIPT_CRIME_ACTION_UNREALIZED" in codes


def test_first_narration_cannot_reveal_late_answer() -> None:
    """첫 Narration의 범인·동기 선공개는 명시된 Prereveal 근거 없이는 실패한다."""
    plan = presentation_plan()
    plan["segments"][2]["referenced_reveal_target_ids"] = ["REVEAL-TARGET-01"]  # type: ignore[index]
    codes = issue_codes(
        validate_script_crime_realization(
            CHANNEL,
            crime_contract(),
            scene_cards(),
            plan,
            reaction_segments(),
            viewer_timeline(),
            final_script(),
        )
    )
    assert "PREMATURE_CRIME_ANSWER_REVEAL" in codes


def test_unsupported_graphic_time_is_rejected_even_when_sum_matches() -> None:
    """50초 발화와 40초 Unsupported Graphic 합계가 맞아도 Runtime 근거는 실패한다."""
    review = {
        "runtime_evidence": {
            "language_unit": "KOREAN_EOJEOL",
            "estimation_assumptions": ["한국어 어절 기준"],
            "panel_segments": [
                {
                    "segment_id": "SEG-002",
                    "action_duration_sec": 0,
                    "non_speaking_duration_sec": 40,
                    "non_speech_elements": [
                        {
                            "element_type": "GRAPHIC",
                            "duration_sec": 40,
                            "time_class": "NON_SPEAKING",
                            "support_status": "UNSUPPORTED",
                            "source_reference": "근거 없음",
                        }
                    ],
                }
            ],
        }
    }
    assert "CRIME_RUNTIME_SOURCE_UNSUPPORTED" in issue_codes(
        explicit_crime_runtime_evidence_issues(CHANNEL, review)
    )


def test_implied_violence_reaches_needs_review_not_core_pass() -> None:
    """암시 폭력도 행동·피해 인과가 구체적이면 CORE 근거를 만들되 PASS하지 않는다."""
    report = build_crime_script_realization_report(
        "PRJ-901",
        CHANNEL,
        crime_contract(),
        scene_cards(),
        presentation_plan(),
        reaction_segments(),
        viewer_timeline(),
        final_script(),
    )
    assert report["result"] == "NEEDS_REVIEW"
    assert (
        validate_crime_script_realization_report(
            CHANNEL,
            "PRJ-901",
            crime_contract(),
            scene_cards(),
            presentation_plan(),
            reaction_segments(),
            viewer_timeline(),
            final_script(),
            report,
        )
        == []
    )


def test_paraphrased_action_and_later_harm_can_use_separate_scenes() -> None:
    """계약 원문을 복사하지 않은 행동과 후반 피해 장면을 독립 근거로 연결한다."""
    contract = crime_contract()
    cards = scene_cards()
    raw_scenes = cards["scenes"]
    assert isinstance(raw_scenes, list)
    action_realization = raw_scenes[1]["crime_realization"][0]
    action_realization["development_function_ids"] = ["CDEV-001", "CDEV-002"]
    raw_scenes.append(
        {
            "scene_id": "SCN-03",
            "order": 3,
            "beat_id": "BEAT-03",
            "estimated_seconds": 30,
            "clue_ids": [],
            "knowledge_claims": [],
            "crime_realization": [
                {
                    "event_id": "EVENT-01",
                    "harm_ids": ["HARM-01"],
                    "actor_ids": ["CHAR-01"],
                    "victim_ids": ["CHAR-02"],
                    "realization_mode": "AFTERMATH_CAUSAL",
                    "action_evidence": "앞선 위협의 결과가 남아 있다.",
                    "dialogue_or_behavior_evidence": "피해자가 문 앞에서 발걸음을 멈춘다.",
                    "choice_or_emotion_change": "혼자 귀가하지 않기로 한다.",
                    "result_change": "일상 동선과 안전감이 달라졌다.",
                    "planned_segment_ids": ["SEG-006"],
                    "development_function_ids": ["CDEV-003", "CDEV-004"],
                    "expected_excerpt_anchor": "후일의 생활 변화",
                }
            ],
        }
    )
    plan = presentation_plan()
    raw_segments = plan["segments"]
    assert isinstance(raw_segments, list)
    raw_segments[4]["crime_development_function_ids"] = ["CDEV-001", "CDEV-002"]
    raw_segments[5].update(
        {
            "segment_type": "DRAMA",
            "scene_id": "SCN-03",
            "source_artifact": "drama_script",
            "crime_development_function_ids": ["CDEV-003", "CDEV-004"],
        }
    )
    raw_segments[5].pop("reaction_segment_id", None)
    script = final_script()
    script = script.replace(
        "HARM=HARM-01\nDEV=CDEV-001,CDEV-002,CDEV-003,CDEV-004",
        "DEV=CDEV-001,CDEV-002",
    ).replace(
        "행위자가 퇴로를 막고 비선정적 폭력을 가했다. "
        "피해자는 치료가 필요한 상해를 입었다. "
        "피해자는 일상 공간에 돌아가지 못하는 불안을 겪었다.",
        "문이 닫히자 그는 출구 앞을 가로막았다. 손목을 뿌리치는 소리 뒤로 "
        "피해자는 비상계단 쪽으로 몸을 돌렸다.",
    )
    script = script.replace(
        "<!-- SEGMENT:SEG-006 TYPE:PANEL_REACTION SCENE:SCN-02 DURATION:30 -->\n"
        "패널은 범인, 동기, 방식과 피해 결과를 공개된 근거로 정리한다.",
        "<!-- SEGMENT:SEG-006 TYPE:DRAMA SCENE:SCN-03 DURATION:30 -->\n"
        "<!-- CRIME_TRACE\nEVENT=EVENT-01\nHARM=HARM-01\n"
        "DEV=CDEV-003,CDEV-004\n-->\n"
        "며칠 뒤에도 피해자는 익숙한 현관 앞에서 멈춰 섰다. 결국 귀가 길과 "
        "근무 시간을 바꾸고 동료에게 동행을 부탁했다.",
    )

    for field in (
        "non_actionable_method_summary",
        "immediate_harm",
        "lasting_harm",
    ):
        summary = contract[field]
        assert isinstance(summary, str)
        assert summary not in script
    assert (
        validate_script_crime_realization(
            CHANNEL,
            contract,
            cards,
            plan,
            reaction_segments(),
            viewer_timeline(),
            script,
        )
        == []
    )
    report = build_crime_script_realization_report(
        "PRJ-901",
        CHANNEL,
        contract,
        cards,
        plan,
        reaction_segments(),
        viewer_timeline(),
        script,
    )
    evidence_links = report["evidence_links"]
    assert isinstance(evidence_links, list)
    assert {link["segment_id"] for link in evidence_links} == {"SEG-005", "SEG-006"}
    assert {link["evidence_type"] for link in evidence_links} == {
        "BEHAVIOR_OR_CHOICE",
        "HARM_AFTERMATH",
    }
    schema = load_json_object(
        ROOT / "STANDARD/schemas/script_realization_report.schema.json"
    )
    assert collect_schema_errors(report, schema, "script_realization_report") == []


def test_marker_without_visible_excerpt_is_rejected() -> None:
    """기계 Marker만 있고 실제 방송 발췌가 없으면 구조 검증에서 차단한다."""
    script = final_script().replace(
        "행위자가 퇴로를 막고 비선정적 폭력을 가했다. "
        "피해자는 치료가 필요한 상해를 입었다. "
        "피해자는 일상 공간에 돌아가지 못하는 불안을 겪었다.",
        "",
    )
    assert "SCRIPT_CRIME_ACTION_UNREALIZED" in issue_codes(
        validate_script_crime_realization(
            CHANNEL,
            crime_contract(),
            scene_cards(),
            presentation_plan(),
            reaction_segments(),
            viewer_timeline(),
            script,
        )
    )


def test_murder_fatality_does_not_require_survival_or_recovery() -> None:
    """사망 피해 사건은 생존·신고·용서·회복 결말 없이 계약을 통과한다."""
    event = event_outline("MURDER")
    variations = {
        "approved_candidate_id": "VAR-01",
        "candidates": [{"candidate_id": "VAR-01", "crime_event": event}],
    }
    assert (
        validate_crime_event_contract(
            CHANNEL,
            {"source_truth_classification": "ORIGINAL_FICTION"},
            variations,
            crime_contract("MURDER"),
            {"facts": []},
        )
        == []
    )


def test_catalog_keeps_kidnapping_confinement_and_lodging() -> None:
    """파일럿 금지였던 납치·감금·숙박 장소를 사건 Catalog에서 허용한다."""
    catalog = load_json_object(ROOT / "STANDARD/variation_catalogs/2.1.0.json")
    dimensions = catalog["dimensions"]
    assert "KIDNAPPING" in dimensions["primary_crime"]  # type: ignore[index]
    assert "CONFINEMENT" in dimensions["primary_crime"]  # type: ignore[index]
    assert "LODGING" in dimensions["setting"]  # type: ignore[index]


def test_editorial_evidence_is_separate_from_core_report() -> None:
    """CORE NEEDS_REVIEW는 Editorial의 실제 발췌 EVIDENCED 평가를 대신하지 않는다."""
    contract = crime_contract()
    artifacts: dict[str, object] = {"final_script": final_script()}
    assert validate_editorial_crime_assessments(
        CHANNEL,
        {"semantic_assessments": []},
        contract,
        artifacts,
    )
    assessments = []
    for index, (category, subject_id) in enumerate(
        sorted(required_semantic_subjects(CHANNEL, contract)),
        1,
    ):
        status = "NOT_DISCLOSED" if category == "PREMATURE_DISCLOSURE_SCAN" else "EVIDENCED"
        assessments.append(
            {
                "assessment_id": f"ASSESS-{index:02d}",
                "category": category,
                "subject_id": subject_id,
                "status": status,
                "evidence": [
                    make_editorial_evidence(
                        artifacts,
                        "final_script",
                        "SEGMENT_ID",
                        "SEG-005",
                    )
                ],
                "notes": "실제 발췌를 검토함",
            }
        )
    assert (
        validate_editorial_crime_assessments(
            CHANNEL,
            {"semantic_assessments": assessments},
            contract,
            artifacts,
        )
        == []
    )

"""Channel Content Version 2.0 정책과 1.1 호환성 검증."""

from copy import deepcopy
from pathlib import Path

from RUNTIME.providers.fake import fake_presentation_plan
from VALIDATORS.channel_policy_v2 import (
    build_channel_policy_inputs,
    validate_channel_policy_v2,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def v2_channel() -> dict[str, object]:
    """모든 신규 정책을 활성화한 v2 Channel Fixture를 만든다."""
    channel = deepcopy(load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json"))
    channel["content_version"] = "2.0.0"
    capabilities = channel["capabilities"]
    assert isinstance(capabilities, dict)
    capabilities.update(
        {
            "CRIME_PSYCHOLOGY_POLICY": {
                "enabled": True,
                "primary_genres": ["CRIME_PSYCHOLOGICAL_THRILLER"],
                "threat_types": ["CRIME", "PREDATORY"],
                "require_psychological_pressure": True,
                "technical_markers": ["TECHNICAL", "MACHINE_LOG"],
                "max_technical_clue_ratio": 0.2,
                "procedural_markers": ["POLICE_PROCEDURAL"],
            },
            "TRUST_AND_SAFETY_BETRAYAL_POLICY": {
                "enabled": True,
                "require_trusted_domain": True,
                "require_safe_domain_expectation": True,
            },
            "COERCIVE_CONTROL_POLICY": {
                "enabled": True,
                "require_warning_signals": True,
                "require_boundary_erosion": True,
                "require_control_tactics": True,
                "require_exit_barriers": True,
            },
            "VICTIM_CENTERED_POLICY": {
                "enabled": True,
                "require_agency_outcome": True,
                "require_responsible_agent_payoff": True,
                "prohibited_phrases": ["피해자가 자초했다"],
            },
            "EXPERT_ANALYSIS_POLICY": {
                "enabled": True,
                "true_story_requirement": "REQUIRED",
                "inspired_requirement": "REQUIRED_OR_NA",
                "original_requirement": "OPTIONAL",
                "require_claim_evidence": True,
            },
            "RISK_SIGNAL_AND_PUBLIC_VALUE_POLICY": {
                "enabled": True,
                "require_risk_signal_payoff": True,
            },
            "SOURCE_DISCLOSURE_POLICY": {
                "enabled": True,
                "labels_by_source_truth": {
                    "ORIGINAL_FICTION": "ORIGINAL_FICTION",
                    "VERIFIED_TRUE_CASE": "VERIFIED_TRUE_CASE",
                    "INSPIRED_BY_TRUE_EVENTS": "INSPIRED_BY_TRUE_EVENTS",
                },
            },
            "CLINICAL_LABEL_POLICY": {
                "enabled": True,
                "controlled_terms": ["사이코패스"],
                "allowed_classifications": [
                    "CONFIRMED_DIAGNOSIS",
                    "EXPERT_ASSESSMENT",
                    "MEDIA_DESCRIPTION",
                    "NARRATOR_OPINION",
                    "UNVERIFIED_LABEL",
                ],
                "diagnosis_requires_expert": True,
                "diagnosis_requires_evidence": True,
            },
            "EPISODE_THEME_POLICY": {
                "enabled": True,
                "allowed_themes": ["TRUST_BETRAYAL"],
                "require_episode_theme": True,
            },
        }
    )
    return channel


def process_step(
    identifier_name: str,
    identifier: str,
    scene_id: str,
    order: int,
) -> dict[str, object]:
    """순서가 있는 범죄 심리 과정 단계를 만든다."""
    return {
        identifier_name: identifier,
        "actor_id": "CHAR-02",
        "victim_id": "CHAR-01",
        "scene_id": scene_id,
        "order": order,
        "description": f"{identifier}의 구체적 행동",
    }


def v2_artifacts() -> dict[str, object]:
    """모든 v2 필수 정책을 만족하는 First-class Artifact를 만든다."""
    project_id = "PRJ-900"
    return {
        "production_config": {
            "project_id": project_id,
            "channel_id": "MYSTERY_MAIN",
            "channel_content_version": "2.0.0",
            "story_source_mode": "ORIGINAL",
            "source_truth_classification": "ORIGINAL_FICTION",
            "genre": "CRIME_PSYCHOLOGICAL_THRILLER",
        },
        "story_dna": {
            "project_id": project_id,
            "story_source_mode": "ORIGINAL",
            "story_dna": {
                "architecture": "ARCH-20_TRUST_BETRAYAL",
                "incident_type": "FRAUD",
                "reveal_mode": "RELATIONAL_REFRAME",
                "dramatic_engine": {"primary": "PSYCHOLOGICAL_PRESSURE"},
                "episode_theme": "TRUST_BETRAYAL",
            },
        },
        "case_input": {
            "project_id": project_id,
            "central_mystery": "누가 피해자의 신뢰를 이용해 송금을 조작했는가?",
        },
        "crime_psychology": {
            "schema_family": "crime-psychology",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "applicable": True,
            "threat_type": "CRIME",
            "trusted_domain": "WORKPLACE",
            "safe_domain_betrayal": "TRUST_ABUSED",
            "safe_domain_expectation": "동료의 도움 요청은 안전하다고 믿었다.",
            "psychological_pressure": "거절하면 동료의 생계가 무너진다는 압박",
            "early_warning_signals": [process_step("warning_signal_id", "WARN-01", "SCN-01", 1)],
            "boundary_erosion_steps": [process_step("boundary_step_id", "BOUND-01", "SCN-01", 2)],
            "control_tactics": [process_step("control_tactic_id", "CTRL-01", "SCN-02", 3)],
            "victim_exit_barriers": [process_step("exit_barrier_id", "EXIT-01", "SCN-02", 4)],
            "harm_mechanism": "신뢰를 이용해 금전과 평판을 통제한다.",
            "harm_event": {
                "harm_event_id": "HARM-01",
                "actor_id": "CHAR-02",
                "victim_id": "CHAR-01",
                "scene_id": "SCN-02",
                "order": 5,
            },
            "responsible_agent": "CHAR-02",
            "responsible_agent_structure": "SINGLE_AGENT",
            "responsible_agent_payoff": "증언과 소유관계로 책임이 특정된다.",
            "victim_agency_outcome": {
                "victim_id": "CHAR-01",
                "ending_scene_id": "SCN-03",
                "outcome": "피해자가 증거를 보존하고 경계를 회복한다.",
            },
            "victim_agency_mode": "EVIDENCE_PRESERVED",
            "risk_signal_payoff": "초기 사적 부탁이 통제의 시작으로 재해석된다.",
            "episode_theme": "TRUST_BETRAYAL",
        },
        "claim_evidence": {"project_id": project_id, "claims": []},
        "source_disclosure": {
            "schema_family": "source-disclosure",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "internal_mode": "ORIGINAL_FICTION",
            "audience_label_text": "본 이야기는 창작입니다.",
        },
        "clinical_labels": {
            "schema_family": "clinical-labels",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "labels": [],
        },
        "characters": {
            "project_id": project_id,
            "characters": [
                {"character_id": "CHAR-01", "role": "VICTIM"},
                {"character_id": "CHAR-02", "role": "RESPONSIBLE_AGENT"},
            ],
        },
        "clue_matrix": {
            "project_id": project_id,
            "clues": [
                {
                    "clue_id": "CLUE-01",
                    "role": "CORE",
                    "evidence_class": "TESTIMONIAL",
                    "mechanism": "LINGUISTIC",
                    "supports_final_reveal": True,
                    "independent_ground_id": "GROUND-01",
                },
                {
                    "clue_id": "CLUE-02",
                    "role": "CORE",
                    "evidence_class": "RELATIONAL",
                    "mechanism": "OWNERSHIP",
                    "supports_final_reveal": True,
                    "independent_ground_id": "GROUND-02",
                },
                {
                    "clue_id": "CLUE-03",
                    "role": "CORE",
                    "evidence_class": "PHYSICAL_OBJECT",
                    "mechanism": "BEHAVIORAL",
                    "supports_final_reveal": False,
                },
            ],
        },
        "scene_cards": {
            "project_id": project_id,
            "scenes": [
                {"scene_id": "SCN-01", "order": 1},
                {"scene_id": "SCN-02", "order": 2},
                {"scene_id": "SCN-03", "order": 3},
            ],
        },
        "expert_segments": {
            "schema_family": "expert-segments",
            "schema_version": "1.0.0",
            "project_id": project_id,
            "status": "NOT_APPLICABLE",
            "not_applicable_reason": "순수 창작에서 전문가 사실 판정을 사용하지 않는다.",
            "segments": [],
        },
        "presentation_plan": {"project_id": project_id, "segments": []},
        "expert_analysis_script": "",
        "production_expert_analysis_script": "",
        "panel_reaction_script": "[PANEL-01] 방금 말은 앞 증언과 다르네요.",
        "final_script": "본 이야기는 창작입니다.\n피해자는 스스로 증거를 보존했다.",
    }


def policy_codes(
    channel: dict[str, object],
    artifacts: dict[str, object],
) -> set[str]:
    """v2 정책 Issue Code 집합을 반환한다."""
    return {
        issue["code"]
        for issue in validate_channel_policy_v2(
            channel,
            build_channel_policy_inputs(artifacts),
        )
    }


def configure_supported_true_story_expert(
    artifacts: dict[str, object],
) -> None:
    """TRUE_STORY에 필요한 Source·Claim·Expert Script 연결을 구성한다."""
    config = artifacts["production_config"]
    disclosure = artifacts["source_disclosure"]
    expert_segments = artifacts["expert_segments"]
    presentation = artifacts["presentation_plan"]
    assert isinstance(config, dict)
    assert isinstance(disclosure, dict)
    assert isinstance(expert_segments, dict)
    assert isinstance(presentation, dict)
    config["story_source_mode"] = "TRUE_STORY"
    config["source_truth_classification"] = "VERIFIED_TRUE_CASE"
    disclosure["internal_mode"] = "VERIFIED_TRUE_CASE"
    disclosure["audience_label_text"] = "실제 사건을 바탕으로 재구성했습니다."
    artifacts["claim_evidence"] = {
        "project_id": "PRJ-900",
        "claims": [
            {
                "claim_id": "CLAIM-01",
                "evidence_source_ids": ["SOURCE-01"],
            }
        ],
    }
    expert_segments["status"] = "PLANNED"
    expert_segments.pop("not_applicable_reason")
    expert_segments["segments"] = [
        {
            "segment_id": "SEG-900",
            "scene_id": "SCN-03",
            "expert_id": "EXPERT-01",
            "expert_role": "VICTIM_ADVOCATE",
            "function": "RISK_CONTEXT",
            "credentials": "피해자 지원 실무 12년",
            "claim_ids": ["CLAIM-01"],
            "evidence_source_ids": ["SOURCE-01"],
            "spoken_line": "초기 사적 부탁은 경계를 테스트하는 신호로 볼 수 있습니다.",
            "confidence": "MEDIUM",
            "limitations": "개별 행동만으로 임상 진단을 할 수는 없습니다.",
        }
    ]
    presentation["segments"] = [
        {
            "segment_id": "SEG-900",
            "segment_type": "EXPERT_ANALYSIS",
            "scene_id": "SCN-03",
            "start_sec": 120,
            "duration_sec": 30,
            "source_artifact": "expert_analysis_script",
            "revealed_fact_ids": [],
            "revealed_clue_ids": [],
        }
    ]
    script = (
        "<!-- SEGMENT:SEG-900 TYPE:EXPERT_ANALYSIS SCENE:SCN-03 DURATION:30 -->\n"
        "초기 사적 부탁은 경계를 테스트하는 신호로 볼 수 있습니다.\n"
        "<!-- END_SEGMENT:SEG-900 -->"
    )
    artifacts["expert_analysis_script"] = script
    artifacts["production_expert_analysis_script"] = script
    artifacts["final_script"] = (
        "실제 사건을 바탕으로 재구성했습니다.\n피해자는 스스로 증거를 보존했다."
    )


def test_complete_v2_policy_documents_pass() -> None:
    """완전한 v2 First-class Artifact는 추가 Issue 없이 통과해야 한다."""
    assert policy_codes(v2_channel(), v2_artifacts()) == set()


def test_v1_1_project_does_not_receive_v2_rules() -> None:
    """기존 1.1.0 Project에는 v2 정책을 소급 적용하지 않는다."""
    artifacts = v2_artifacts()
    config = artifacts["production_config"]
    assert isinstance(config, dict)
    config["channel_content_version"] = "1.1.0"
    artifacts["crime_psychology"] = {}
    artifacts["final_script"] = "피해자가 자초했다. 사이코패스다."

    assert policy_codes(v2_channel(), artifacts) == set()


def test_episode_theme_missing_fails() -> None:
    """v2 Case Trace에 Episode Theme이 없으면 실패한다."""
    artifacts = v2_artifacts()
    crime = artifacts["crime_psychology"]
    assert isinstance(crime, dict)
    crime.pop("episode_theme")

    assert "EPISODE_THEME_MISSING" in policy_codes(v2_channel(), artifacts)


def test_reversed_control_step_order_fails() -> None:
    """경고보다 앞서 통제가 발생하면 인과 순서 검증이 실패한다."""
    artifacts = v2_artifacts()
    crime = artifacts["crime_psychology"]
    assert isinstance(crime, dict)
    tactics = crime["control_tactics"]
    assert isinstance(tactics, list)
    tactic = tactics[0]
    assert isinstance(tactic, dict)
    tactic["order"] = 1

    assert "COERCIVE_CONTROL_ORDER_INVALID" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_late_boundary_step_after_control_fails() -> None:
    """하나의 경계 침식 단계라도 통제 뒤에 놓이면 순서 검증이 실패한다."""
    artifacts = v2_artifacts()
    crime = artifacts["crime_psychology"]
    assert isinstance(crime, dict)
    boundaries = crime["boundary_erosion_steps"]
    assert isinstance(boundaries, list)
    boundaries.append(process_step("boundary_step_id", "BOUND-02", "SCN-02", 4))

    assert "COERCIVE_CONTROL_ORDER_INVALID" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_control_trace_must_reference_real_character_and_scene() -> None:
    """통제 과정의 Actor·Victim·Scene ID는 실제 Artifact와 연결되어야 한다."""
    artifacts = v2_artifacts()
    crime = artifacts["crime_psychology"]
    assert isinstance(crime, dict)
    warnings = crime["early_warning_signals"]
    assert isinstance(warnings, list)
    warning = warnings[0]
    assert isinstance(warning, dict)
    warning["actor_id"] = "CHAR-99"

    assert "CRIME_PSYCHOLOGY_TRACE_INVALID" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_victim_agency_must_reference_trace_victim() -> None:
    """Ending의 Agency는 단순 등장인물이 아니라 실제 피해자와 연결되어야 한다."""
    artifacts = v2_artifacts()
    characters = artifacts["characters"]
    crime = artifacts["crime_psychology"]
    assert isinstance(characters, dict)
    assert isinstance(crime, dict)
    character_records = characters["characters"]
    agency = crime["victim_agency_outcome"]
    assert isinstance(character_records, list)
    assert isinstance(agency, dict)
    character_records.append({"character_id": "CHAR-03", "role": "WITNESS"})
    agency["victim_id"] = "CHAR-03"

    assert "VICTIM_AGENCY_OUTCOME_MISSING" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_technical_log_only_reveal_fails() -> None:
    """기술 로그 하나만 Final Reveal을 지지하면 실패한다."""
    artifacts = v2_artifacts()
    clue_matrix = artifacts["clue_matrix"]
    assert isinstance(clue_matrix, dict)
    clue_matrix["clues"] = [
        {
            "clue_id": "CLUE-99",
            "role": "CORE",
            "evidence_class": "TECHNICAL",
            "mechanism": "MACHINE_LOG",
            "supports_final_reveal": True,
            "independent_ground_id": "GROUND-99",
        }
    ]

    assert "TECHNICAL_PUZZLE_DOMINANCE" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_expert_marker_in_panel_script_fails() -> None:
    """Expert 발화를 Panel Script에 넣으면 Layer 분리 검증이 실패한다."""
    artifacts = v2_artifacts()
    artifacts["panel_reaction_script"] = "[EXPERT-01] 이 행동은 진단을 입증합니다."

    assert "PANEL_OPINION_USED_AS_EXPERT_FACT" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_audience_label_text_missing_fails() -> None:
    """정확한 시청자 공개 문구가 Final Script에 없으면 실패한다."""
    artifacts = v2_artifacts()
    artifacts["final_script"] = "피해자는 증거를 보존했다."

    assert "SOURCE_DISCLOSURE_MISSING" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_criminal_act_alone_cannot_confirm_psychopathy() -> None:
    """범죄 행위만으로 사이코패스 진단을 확정하면 실패한다."""
    artifacts = v2_artifacts()
    clinical = artifacts["clinical_labels"]
    assert isinstance(clinical, dict)
    clinical["labels"] = [
        {
            "term": "사이코패스",
            "subject_id": "CHAR-02",
            "classification": "CONFIRMED_DIAGNOSIS",
            "source_claim_ids": [],
            "qualified_expert": False,
            "documented_assessment": False,
        }
    ]
    artifacts["final_script"] = "본 이야기는 창작입니다. 범죄를 저지른 사이코패스다."

    codes = policy_codes(v2_channel(), artifacts)
    assert "CRIMINAL_ACT_TREATED_AS_DIAGNOSIS" in codes
    assert "CLINICAL_LABEL_SOURCE_MISSING" in codes
    assert "UNSUPPORTED_CLINICAL_DIAGNOSIS" in codes


def test_true_story_requires_expert_analysis() -> None:
    """TRUE_STORY에 Expert Segment가 없으면 실패한다."""
    artifacts = v2_artifacts()
    config = artifacts["production_config"]
    disclosure = artifacts["source_disclosure"]
    assert isinstance(config, dict)
    assert isinstance(disclosure, dict)
    config["story_source_mode"] = "TRUE_STORY"
    config["source_truth_classification"] = "VERIFIED_TRUE_CASE"
    disclosure["internal_mode"] = "VERIFIED_TRUE_CASE"
    disclosure["audience_label_text"] = "실제 사건을 바탕으로 재구성했습니다."
    artifacts["final_script"] = "실제 사건을 바탕으로 재구성했습니다."

    assert "EXPERT_ANALYSIS_REQUIRED" in policy_codes(v2_channel(), artifacts)


def test_true_story_with_claim_evidence_expert_segment_passes() -> None:
    """TRUE_STORY Expert가 실제 Claim·Source·대본과 연결되면 통과한다."""
    artifacts = v2_artifacts()
    configure_supported_true_story_expert(artifacts)

    assert policy_codes(v2_channel(), artifacts) == set()


def test_expert_claim_without_matching_evidence_fails() -> None:
    """Expert Claim이 선언한 Source와 맞지 않으면 실패한다."""
    artifacts = v2_artifacts()
    configure_supported_true_story_expert(artifacts)
    evidence = artifacts["claim_evidence"]
    assert isinstance(evidence, dict)
    claims = evidence["claims"]
    assert isinstance(claims, list)
    claim = claims[0]
    assert isinstance(claim, dict)
    claim["evidence_source_ids"] = ["SOURCE-99"]

    assert "EXPERT_ANALYSIS_UNSUPPORTED_CLAIM" in policy_codes(
        v2_channel(),
        artifacts,
    )


def test_expert_analysis_source_must_be_expert_script() -> None:
    """EXPERT_ANALYSIS Segment는 Panel Script를 Source로 사용할 수 없다."""
    presentation = fake_presentation_plan("PRJ-900", 120)
    modes = presentation["modes"]
    segments = presentation["segments"]
    assert isinstance(modes, list)
    assert isinstance(segments, list)
    modes.append("EXPERT_ANALYSIS")
    segments.append(
        {
            "segment_id": "SEG-900",
            "segment_type": "EXPERT_ANALYSIS",
            "scene_id": "SCN-02",
            "start_sec": 120,
            "duration_sec": 30,
            "source_artifact": "panel_reaction_script",
            "revealed_fact_ids": ["FACT-02"],
            "revealed_clue_ids": [],
        }
    )
    schema = load_json_object(ROOT / "STANDARD" / "schemas" / "presentation_plan.schema.json")

    assert collect_schema_errors(presentation, schema, "presentation_plan")


def test_first_class_v2_artifact_schemas_accept_complete_fixture() -> None:
    """v2 First-class JSON Artifact는 각 Schema를 통과해야 한다."""
    artifacts = v2_artifacts()
    pairs = (
        ("crime_psychology", "crime_psychology.schema.json"),
        ("source_disclosure", "source_disclosure.schema.json"),
        ("clinical_labels", "clinical_labels.schema.json"),
        ("expert_segments", "expert_segments.schema.json"),
    )
    for artifact_name, schema_name in pairs:
        artifact = artifacts[artifact_name]
        assert isinstance(artifact, dict)
        schema = load_json_object(ROOT / "STANDARD" / "schemas" / schema_name)
        assert collect_schema_errors(artifact, schema, artifact_name) == []

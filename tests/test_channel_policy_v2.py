"""Channel Content Version 2.0 정책과 1.1 호환성 검증."""

from copy import deepcopy
from pathlib import Path

from RUNTIME.providers.fake import fake_presentation_plan
from VALIDATORS.channel_policy_v2 import validate_channel_policy_v2
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def v2_channel() -> dict[str, object]:
    """모든 신규 정책을 활성화한 v2 Channel Fixture를 만든다."""
    channel = deepcopy(
        load_json_object(ROOT / "CHANNELS" / "mystery_main" / "channel_dna.json")
    )
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
                "labels_by_source_mode": {
                    "ORIGINAL": "ORIGINAL_FICTION",
                    "USER_CASE": "INSPIRED_BY_TRUE_EVENTS",
                    "REFERENCE_INSPIRED": "INSPIRED_BY_TRUE_EVENTS",
                    "TRUE_STORY": "VERIFIED_TRUE_CASE",
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


def v2_documents() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    str,
]:
    """모든 v2 필수 정책을 만족하는 Project 문서 묶음을 만든다."""
    config: dict[str, object] = {
        "project_id": "PRJ-900",
        "channel_id": "MYSTERY_MAIN",
        "channel_content_version": "2.0.0",
        "story_source_mode": "ORIGINAL",
        "genre": "CRIME_PSYCHOLOGICAL_THRILLER",
    }
    story: dict[str, object] = {
        "project_id": "PRJ-900",
        "story_source_mode": "ORIGINAL",
        "story_dna": {
            "architecture": "ARCH-20_TRUST_BETRAYAL",
            "incident_type": "FRAUD",
            "reveal_mode": "RELATIONAL_REFRAME",
            "information_mechanism": ["TESTIMONIAL", "RELATIONAL"],
            "clue_mechanism": ["LINGUISTIC", "BEHAVIORAL"],
            "dramatic_engine": {"primary": "PSYCHOLOGICAL_PRESSURE"},
            "threat_type": "CRIME",
            "trusted_domain": "WORKPLACE",
            "safe_domain_expectation": "동료의 도움 요청은 안전하다고 믿었다.",
            "early_warning_signals": ["PRIVATE_FAVOR_ESCALATION"],
            "boundary_erosion_steps": ["PERSONAL_ACCOUNT_REQUEST"],
            "control_tactics": ["SOCIAL_ISOLATION"],
            "victim_exit_barriers": ["EMPLOYMENT_REPUTATION_RISK"],
            "harm_mechanism": "신뢰를 이용해 금전과 평판을 통제한다.",
            "responsible_agent": "CHAR-02",
            "responsible_agent_payoff": "증언과 소유관계로 책임이 특정된다.",
            "victim_agency_outcome": "피해자가 증거를 보존하고 경계를 회복한다.",
            "psychological_pressure": "도움을 거절하면 동료가 피해를 본다는 압박",
            "risk_signal_payoff": "초기 사적 부탁이 통제 패턴의 시작으로 재해석된다.",
            "source_disclosure_mode": "ORIGINAL_FICTION",
            "clinical_label_classification": [],
            "episode_theme": "TRUST_BETRAYAL",
        },
    }
    case_input: dict[str, object] = {
        "central_mystery": "누가 피해자의 신뢰를 이용해 송금을 조작했는가?"
    }
    claim_evidence: dict[str, object] = {"claims": []}
    presentation: dict[str, object] = {"modes": [], "segments": []}
    return (
        config,
        story,
        case_input,
        claim_evidence,
        presentation,
        "ORIGINAL_FICTION · 안전한 귀가 장면",
    )


def policy_codes(
    channel: dict[str, object],
    config: dict[str, object],
    story: dict[str, object],
    case_input: dict[str, object],
    claims: dict[str, object],
    presentation: dict[str, object],
    final_script: str,
) -> set[str]:
    """v2 정책 Issue Code 집합을 반환한다."""
    return {
        issue["code"]
        for issue in validate_channel_policy_v2(
            channel,
            story,
            config,
            case_input,
            claims,
            presentation,
            final_script,
        )
    }


def test_complete_v2_policy_documents_pass() -> None:
    """완전한 v2 정책 문서는 추가 Issue 없이 통과해야 한다."""
    config, story, case_input, claims, presentation, script = v2_documents()

    assert policy_codes(
        v2_channel(), config, story, case_input, claims, presentation, script
    ) == set()


def test_v1_1_project_does_not_receive_v2_rules() -> None:
    """기존 1.1.0 Project에는 활성화된 v2 정책도 소급 적용하지 않는다."""
    config: dict[str, object] = {
        "channel_content_version": "1.1.0",
        "story_source_mode": "TRUE_STORY",
    }

    assert validate_channel_policy_v2(
        v2_channel(),
        {"story_dna": {}},
        config,
        {},
        {},
        {},
        "피해자가 자초했다. 사이코패스다.",
    ) == []


def test_trusted_domain_is_required_in_v2() -> None:
    """v2에서 Trusted Domain이 없으면 실패해야 한다."""
    config, story, case_input, claims, presentation, script = v2_documents()
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna.pop("trusted_domain")

    assert "TRUSTED_DOMAIN_MISSING" in policy_codes(
        v2_channel(), config, story, case_input, claims, presentation, script
    )


def test_control_process_fields_are_required_in_v2() -> None:
    """경고 신호·경계 침식·통제 과정·이탈 장벽 누락을 각각 판정한다."""
    config, story, case_input, claims, presentation, script = v2_documents()
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    for key in (
        "early_warning_signals",
        "boundary_erosion_steps",
        "control_tactics",
        "victim_exit_barriers",
    ):
        story_dna.pop(key)

    codes = policy_codes(
        v2_channel(), config, story, case_input, claims, presentation, script
    )
    assert {
        "EARLY_WARNING_SIGNAL_MISSING",
        "BOUNDARY_EROSION_MISSING",
        "COERCIVE_CONTROL_PROCESS_MISSING",
        "VICTIM_EXIT_BARRIER_MISSING",
    }.issubset(codes)


def test_victim_blaming_language_fails() -> None:
    """피해자 비난 표현은 Final Script에서 차단해야 한다."""
    config, story, case_input, claims, presentation, _script = v2_documents()

    assert "VICTIM_BLAMING_LANGUAGE" in policy_codes(
        v2_channel(),
        config,
        story,
        case_input,
        claims,
        presentation,
        "피해자가 자초했다.",
    )


def test_true_story_requires_expert_analysis() -> None:
    """TRUE_STORY에는 전문가 분석 Segment가 필요하다."""
    config, story, case_input, claims, presentation, script = v2_documents()
    config["story_source_mode"] = "TRUE_STORY"
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna["source_disclosure_mode"] = "VERIFIED_TRUE_CASE"

    assert "EXPERT_ANALYSIS_REQUIRED" in policy_codes(
        v2_channel(), config, story, case_input, claims, presentation, script
    )


def test_inspired_story_accepts_explicit_expert_na_reason() -> None:
    """실화 모티프 Story는 전문가 분석 대신 명시적 N/A 근거를 사용할 수 있다."""
    config, story, case_input, claims, presentation, _script = v2_documents()
    config["story_source_mode"] = "INSPIRED_BY_TRUE_EVENTS"
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna["source_disclosure_mode"] = "INSPIRED_BY_TRUE_EVENTS"

    missing_codes = policy_codes(
        v2_channel(),
        config,
        story,
        case_input,
        claims,
        presentation,
        "INSPIRED_BY_TRUE_EVENTS · 재구성 장면",
    )
    assert "EXPERT_ANALYSIS_REQUIRED" in missing_codes

    story_dna["expert_debrief_plan"] = {
        "status": "NOT_APPLICABLE",
        "na_reason": "임상 판단을 다루지 않고 공개 기록의 위험 신호만 제시한다.",
    }
    accepted_codes = policy_codes(
        v2_channel(),
        config,
        story,
        case_input,
        claims,
        presentation,
        "INSPIRED_BY_TRUE_EVENTS · 재구성 장면",
    )
    assert "EXPERT_ANALYSIS_REQUIRED" not in accepted_codes
    story_schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"
    )
    definitions = story_schema["$defs"]
    assert isinstance(definitions, dict)
    assert collect_schema_errors(
        story_dna["expert_debrief_plan"],
        definitions["expertDebriefPlan"],
        "expert_debrief_plan",
    ) == []


def test_original_fiction_cannot_be_presented_as_true() -> None:
    """ORIGINAL 창작물을 실화 Label로 표시하면 실패해야 한다."""
    config, story, case_input, claims, presentation, script = v2_documents()
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna["source_disclosure_mode"] = "VERIFIED_TRUE_CASE"

    assert "FICTION_PRESENTED_AS_TRUE" in policy_codes(
        v2_channel(), config, story, case_input, claims, presentation, script
    )


def test_unsupported_clinical_diagnosis_fails() -> None:
    """통제 임상 용어를 분류와 근거 없이 사용하면 실패해야 한다."""
    config, story, case_input, claims, presentation, _script = v2_documents()

    assert "UNSUPPORTED_CLINICAL_DIAGNOSIS" in policy_codes(
        v2_channel(),
        config,
        story,
        case_input,
        claims,
        presentation,
        "그는 사이코패스다.",
    )


def test_expert_claim_requires_claim_evidence_link() -> None:
    """전문가 발화 Claim은 Evidence Source와 연결되어야 한다."""
    config, story, case_input, claims, presentation, script = v2_documents()
    config["story_source_mode"] = "TRUE_STORY"
    story_dna = story["story_dna"]
    assert isinstance(story_dna, dict)
    story_dna["source_disclosure_mode"] = "VERIFIED_TRUE_CASE"
    presentation["segments"] = [
        {
            "segment_id": "SEG-010",
            "segment_type": "EXPERT_ANALYSIS",
            "expert_analysis": {
                "expert_id": "EXPERT-01",
                "claim_ids": ["FACT-10"],
                "evidence_source_ids": ["SOURCE-10"],
            },
        }
    ]

    assert "EXPERT_ANALYSIS_UNSUPPORTED_CLAIM" in policy_codes(
        v2_channel(), config, story, case_input, claims, presentation, script
    )


def test_expert_analysis_is_supported_as_conditional_segment() -> None:
    """전문가 분석 Segment는 전문가와 Claim-Evidence 식별자를 가져야 한다."""
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
            "expert_analysis": {
                "expert_id": "EXPERT-01",
                "credentials": "임상심리전문가",
                "claim_ids": ["FACT-02"],
                "evidence_source_ids": ["SOURCE-01"],
            },
        }
    )
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "presentation_plan.schema.json"
    )

    assert collect_schema_errors(presentation, schema, "presentation_plan") == []

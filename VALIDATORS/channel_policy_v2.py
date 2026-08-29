"""Channel Content Version 2.0 이상에만 적용하는 결정론적 정책 검증."""

from collections.abc import Mapping, Sequence
from typing import TypedDict, cast

from VALIDATORS.compatibility import mapping_or_empty, parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue
from VALIDATORS.presentation_validation import (
    parse_script_segments,
    presentation_segments,
)

V2_MINIMUM_VERSION = (2, 0, 0)
EXPERT_ROLES = frozenset(
    {
        "CLINICAL_PSYCHOLOGIST",
        "FORENSIC_PSYCHOLOGIST",
        "CRIMINOLOGIST",
        "VICTIM_ADVOCATE",
        "LEGAL_EXPERT",
    }
)
CLINICAL_FACT_CLASSIFICATIONS = frozenset(
    {"CONFIRMED_DIAGNOSIS", "EXPERT_ASSESSMENT"}
)
SOURCE_LABEL_TEXTS: Mapping[str, str] = {
    "ORIGINAL_FICTION": "본 이야기는 창작입니다.",
    "VERIFIED_TRUE_CASE": "실제 사건을 바탕으로 재구성했습니다.",
    "INSPIRED_BY_TRUE_EVENTS": "실제 사건에서 모티프를 얻어 각색했습니다.",
}


class ChannelPolicyInputs(TypedDict):
    """v2 정책이 소비하는 First-class Project Artifact 묶음."""

    production_config: Mapping[str, object]
    story_document: Mapping[str, object]
    case_input: Mapping[str, object]
    crime_psychology: Mapping[str, object]
    claim_evidence: Mapping[str, object]
    source_disclosure: Mapping[str, object]
    clinical_labels: Mapping[str, object]
    characters: Mapping[str, object]
    clue_matrix: Mapping[str, object]
    scene_cards: Mapping[str, object]
    expert_segments: Mapping[str, object]
    presentation_plan: Mapping[str, object]
    expert_analysis_script: str
    production_expert_analysis_script: str
    panel_reaction_script: str
    final_script: str


def policy_mapping_artifact(
    artifacts: Mapping[str, object],
    artifact_name: str,
) -> Mapping[str, object]:
    """정책 입력에서 JSON Artifact를 읽고 누락값은 빈 객체로 유지한다."""
    value = artifacts.get(artifact_name)
    return value if isinstance(value, Mapping) else {}


def policy_text_artifact(
    artifacts: Mapping[str, object],
    artifact_name: str,
) -> str:
    """정책 입력에서 Text Artifact를 읽고 누락값은 빈 문자열로 유지한다."""
    value = artifacts.get(artifact_name)
    return value if isinstance(value, str) else ""


def build_channel_policy_inputs(
    artifacts: Mapping[str, object],
) -> ChannelPolicyInputs:
    """Project Artifact 색인에서 v2 정책 입력을 구성한다."""
    return ChannelPolicyInputs(
        production_config=policy_mapping_artifact(artifacts, "production_config"),
        story_document=policy_mapping_artifact(artifacts, "story_dna"),
        case_input=policy_mapping_artifact(artifacts, "case_input"),
        crime_psychology=policy_mapping_artifact(artifacts, "crime_psychology"),
        claim_evidence=policy_mapping_artifact(artifacts, "claim_evidence"),
        source_disclosure=policy_mapping_artifact(artifacts, "source_disclosure"),
        clinical_labels=policy_mapping_artifact(artifacts, "clinical_labels"),
        characters=policy_mapping_artifact(artifacts, "characters"),
        clue_matrix=policy_mapping_artifact(artifacts, "clue_matrix"),
        scene_cards=policy_mapping_artifact(artifacts, "scene_cards"),
        expert_segments=policy_mapping_artifact(artifacts, "expert_segments"),
        presentation_plan=policy_mapping_artifact(artifacts, "presentation_plan"),
        expert_analysis_script=policy_text_artifact(
            artifacts,
            "expert_analysis_script",
        ),
        production_expert_analysis_script=policy_text_artifact(
            artifacts,
            "production_expert_analysis_script",
        ),
        panel_reaction_script=policy_text_artifact(
            artifacts,
            "panel_reaction_script",
        ),
        final_script=policy_text_artifact(artifacts, "final_script"),
    )


def make_policy_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """v2 Channel 정책 문제를 표준 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def v2_policy_applies(production_config: Mapping[str, object]) -> bool:
    """Project가 고정한 Content Version이 2.0.0 이상인지 판정한다."""
    version = production_config.get("channel_content_version")
    if not isinstance(version, str):
        raise ConfigurationError(
            "production_config.channel_content_version 문자열이 필요합니다."
        )
    return parse_semantic_version(version) >= V2_MINIMUM_VERSION


def enabled_policy(
    capabilities: Mapping[str, object],
    capability_name: str,
) -> Mapping[str, object] | None:
    """활성화된 정책 Capability만 반환한다."""
    policy = capabilities.get(capability_name)
    if isinstance(policy, Mapping) and policy.get("enabled") is True:
        return policy
    return None


def mapping_records(
    document: Mapping[str, object],
    key: str,
) -> list[Mapping[str, object]]:
    """문서의 객체 배열만 반환한다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_values(document: Mapping[str, object], key: str) -> list[str]:
    """문서의 문자열 배열만 반환한다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def nonempty_string(document: Mapping[str, object], key: str) -> bool:
    """필드가 공백이 아닌 문자열인지 판정한다."""
    value = document.get(key)
    return isinstance(value, str) and bool(value.strip())


def missing_string_issue(
    document: Mapping[str, object],
    key: str,
    code: str,
    message: str,
    artifact: str,
) -> list[ValidationIssue]:
    """필수 문자열 누락을 Issue로 변환한다."""
    if nonempty_string(document, key):
        return []
    return [make_policy_issue(code, message, artifact, {"field": key})]


def missing_records_issue(
    document: Mapping[str, object],
    key: str,
    code: str,
    message: str,
) -> list[ValidationIssue]:
    """필수 Trace 배열 누락을 Issue로 변환한다."""
    if mapping_records(document, key):
        return []
    return [
        make_policy_issue(
            code,
            message,
            "01_CASE/crime_psychology.json",
            {"field": key},
        )
    ]


def validate_crime_policy(
    policy: Mapping[str, object],
    production_config: Mapping[str, object],
    story_dna: Mapping[str, object],
    case_input: Mapping[str, object],
    crime_psychology: Mapping[str, object],
) -> list[ValidationIssue]:
    """범죄 위협, 심리 압박, 절차물 이탈을 검증한다."""
    issues: list[ValidationIssue] = []
    primary_genres = string_values(policy, "primary_genres")
    if primary_genres and production_config.get("genre") not in primary_genres:
        issues.append(
            make_policy_issue(
                "CHANNEL_PRIMARY_GENRE_MISMATCH",
                "프로젝트 장르가 v2 Channel의 주 장르와 다릅니다.",
                "00_PROJECT/production_config.json",
                {
                    "genre": production_config.get("genre"),
                    "primary_genres": primary_genres,
                },
            )
        )
    threat_types = string_values(policy, "threat_types")
    threat_type = crime_psychology.get("threat_type")
    if (
        threat_type not in threat_types
        or not nonempty_string(crime_psychology, "harm_mechanism")
        or not nonempty_string(case_input, "central_mystery")
    ):
        issues.append(
            make_policy_issue(
                "CRIME_OR_PREDATORY_THREAT_MISSING",
                "범죄 또는 약탈적 위협과 구체적 피해 메커니즘이 필요합니다.",
                "01_CASE/crime_psychology.json",
                {"threat_type": threat_type, "allowed": threat_types},
            )
        )
    if policy.get("require_psychological_pressure") is True:
        issues.extend(
            missing_string_issue(
                crime_psychology,
                "psychological_pressure",
                "PSYCHOLOGICAL_PRESSURE_MISSING",
                "인물에게 작동하는 심리적 압박이 필요합니다.",
                "01_CASE/crime_psychology.json",
            )
        )
    procedural_markers = set(string_values(policy, "procedural_markers"))
    dramatic_engine = mapping_or_empty(story_dna, "dramatic_engine")
    candidates = {
        story_dna.get("architecture"),
        story_dna.get("reveal_mode"),
        story_dna.get("incident_type"),
        dramatic_engine.get("primary"),
    }
    collisions = sorted(
        value
        for value in candidates
        if isinstance(value, str) and value in procedural_markers
    )
    if collisions:
        issues.append(
            make_policy_issue(
                "PROCEDURAL_DRIFT",
                "범죄 심리 중심에서 절차물 중심으로 이탈했습니다.",
                "00_PROJECT/story_dna.json",
                {"markers": collisions},
            )
        )
    return issues


def validate_trust_and_control(
    trust_policy: Mapping[str, object] | None,
    control_policy: Mapping[str, object] | None,
    crime_psychology: Mapping[str, object],
) -> list[ValidationIssue]:
    """신뢰 배신과 경고·경계·통제·이탈 장벽 Trace를 검증한다."""
    issues: list[ValidationIssue] = []
    if trust_policy is not None:
        if trust_policy.get("require_trusted_domain") is True:
            issues.extend(
                missing_string_issue(
                    crime_psychology,
                    "trusted_domain",
                    "TRUSTED_DOMAIN_MISSING",
                    "피해자가 신뢰한 생활 영역이 필요합니다.",
                    "01_CASE/crime_psychology.json",
                )
            )
        if trust_policy.get("require_safe_domain_expectation") is True:
            issues.extend(
                missing_string_issue(
                    crime_psychology,
                    "safe_domain_expectation",
                    "SAFE_DOMAIN_BETRAYAL_MISSING",
                    "안전하다고 믿은 기대의 배신이 필요합니다.",
                    "01_CASE/crime_psychology.json",
                )
            )
    if control_policy is None:
        return issues
    checks: tuple[tuple[str, str, str, object], ...] = (
        (
            "early_warning_signals",
            "EARLY_WARNING_SIGNAL_MISSING",
            "초기 위험 신호가 필요합니다.",
            control_policy.get("require_warning_signals"),
        ),
        (
            "boundary_erosion_steps",
            "BOUNDARY_EROSION_MISSING",
            "경계 침식 단계가 필요합니다.",
            control_policy.get("require_boundary_erosion"),
        ),
        (
            "control_tactics",
            "COERCIVE_CONTROL_PROCESS_MISSING",
            "강압적 통제 과정이 필요합니다.",
            control_policy.get("require_control_tactics"),
        ),
        (
            "victim_exit_barriers",
            "VICTIM_EXIT_BARRIER_MISSING",
            "피해자가 즉시 벗어나기 어려운 장벽이 필요합니다.",
            control_policy.get("require_exit_barriers"),
        ),
    )
    for field, code, message, required in checks:
        if required is True:
            issues.extend(missing_records_issue(crime_psychology, field, code, message))
    return issues


def record_orders(records: Sequence[Mapping[str, object]]) -> list[int]:
    """Trace 객체의 유효한 순서 정수만 반환한다."""
    return [
        cast(int, record["order"])
        for record in records
        if isinstance(record.get("order"), int)
        and not isinstance(record.get("order"), bool)
    ]


def validate_control_order(
    crime_psychology: Mapping[str, object],
) -> list[ValidationIssue]:
    """경고→경계 침식→통제→피해 순서를 결정론적으로 검증한다."""
    warnings = record_orders(mapping_records(crime_psychology, "early_warning_signals"))
    boundaries = record_orders(mapping_records(crime_psychology, "boundary_erosion_steps"))
    controls = record_orders(mapping_records(crime_psychology, "control_tactics"))
    barriers = record_orders(mapping_records(crime_psychology, "victim_exit_barriers"))
    harm = crime_psychology.get("harm_event")
    harm_order = harm.get("order") if isinstance(harm, Mapping) else None
    if not all((warnings, boundaries, controls)) or not isinstance(harm_order, int):
        return []
    ordered = (
        max(warnings) < min(boundaries)
        and max(boundaries) < min(controls)
        and max(controls) < harm_order
        and (
            not barriers
            or (max(controls) <= min(barriers) and max(barriers) < harm_order)
        )
    )
    if ordered:
        return []
    return [
        make_policy_issue(
            "COERCIVE_CONTROL_ORDER_INVALID",
            "경고 신호, 경계 침식, 통제, 피해의 순서가 뒤집혔습니다.",
            "01_CASE/crime_psychology.json",
            {
                "warning_orders": warnings,
                "boundary_orders": boundaries,
                "control_orders": controls,
                "exit_barrier_orders": barriers,
                "harm_order": harm_order,
            },
        )
    ]


def validate_control_trace_links(
    crime_psychology: Mapping[str, object],
    characters: Mapping[str, object],
    scene_cards: Mapping[str, object],
) -> list[ValidationIssue]:
    """범죄 심리 과정의 행위자·피해자·Scene 참조를 검증한다."""
    known_characters = character_ids(characters)
    known_scenes = {
        scene_id
        for scene in mapping_records(scene_cards, "scenes")
        if isinstance((scene_id := scene.get("scene_id")), str)
    }
    records = [
        record
        for field in (
            "early_warning_signals",
            "boundary_erosion_steps",
            "control_tactics",
            "victim_exit_barriers",
        )
        for record in mapping_records(crime_psychology, field)
    ]
    harm_event = crime_psychology.get("harm_event")
    if isinstance(harm_event, Mapping):
        records.append(harm_event)
    invalid = [
        {
            "actor_id": record.get("actor_id"),
            "victim_id": record.get("victim_id"),
            "scene_id": record.get("scene_id"),
        }
        for record in records
        if record.get("actor_id") not in known_characters
        or record.get("victim_id") not in known_characters
        or record.get("scene_id") not in known_scenes
    ]
    if not invalid:
        return []
    return [
        make_policy_issue(
            "CRIME_PSYCHOLOGY_TRACE_INVALID",
            "범죄 심리 과정이 실제 Character와 Scene에 연결되지 않았습니다.",
            "01_CASE/crime_psychology.json",
            {"invalid_references": invalid},
        )
    ]


def technical_clue(
    clue: Mapping[str, object],
    technical_markers: set[str],
) -> bool:
    """실제 Clue가 기술 분류 또는 기술 Marker인지 판정한다."""
    return (
        clue.get("evidence_class") == "TECHNICAL"
        or clue.get("mechanism") in technical_markers
    )


def validate_technical_reveal(
    policy: Mapping[str, object],
    clue_matrix: Mapping[str, object],
) -> list[ValidationIssue]:
    """실제 Core Clue와 독립 Reveal 근거로 기술 퍼즐 지배를 검증한다."""
    core_clues = [
        clue
        for clue in mapping_records(clue_matrix, "clues")
        if clue.get("role") == "CORE"
    ]
    technical_markers = set(string_values(policy, "technical_markers"))
    technical_core = [
        clue for clue in core_clues if technical_clue(clue, technical_markers)
    ]
    ratio = len(technical_core) / len(core_clues) if core_clues else 1.0
    maximum = policy.get("max_technical_clue_ratio")
    reveal_clues = [
        clue for clue in core_clues if clue.get("supports_final_reveal") is True
    ]
    nontechnical_ground_ids = {
        ground_id
        for clue in reveal_clues
        if not technical_clue(clue, technical_markers)
        and isinstance((ground_id := clue.get("independent_ground_id")), str)
    }
    technical_only = bool(reveal_clues) and all(
        technical_clue(clue, technical_markers) for clue in reveal_clues
    )
    ratio_exceeded = (
        isinstance(maximum, int | float)
        and not isinstance(maximum, bool)
        and ratio > float(maximum)
    )
    if (
        core_clues
        and reveal_clues
        and not ratio_exceeded
        and not technical_only
        and len(nontechnical_ground_ids) >= 2
    ):
        return []
    return [
        make_policy_issue(
            "TECHNICAL_PUZZLE_DOMINANCE",
            "최종 Reveal은 기술 단서가 아닌 독립 근거 두 개 이상으로 지지되어야 합니다.",
            "04_MYSTERY/clue_matrix.json",
            {
                "technical_core_ratio": ratio,
                "maximum_ratio": maximum,
                "final_reveal_clue_count": len(reveal_clues),
                "nontechnical_independent_ground_ids": sorted(
                    nontechnical_ground_ids
                ),
                "technical_only_solution": technical_only,
            },
        )
    ]


def character_ids(characters: Mapping[str, object]) -> set[str]:
    """Character Artifact의 ID 집합을 반환한다."""
    return {
        character_id
        for character in mapping_records(characters, "characters")
        if isinstance((character_id := character.get("character_id")), str)
    }


def crime_victim_ids(crime_psychology: Mapping[str, object]) -> set[str]:
    """범죄 심리 Trace에서 실제 피해자로 연결된 Character ID를 반환한다."""
    victim_ids = {
        victim_id
        for field in (
            "early_warning_signals",
            "boundary_erosion_steps",
            "control_tactics",
            "victim_exit_barriers",
        )
        for record in mapping_records(crime_psychology, field)
        if isinstance((victim_id := record.get("victim_id")), str)
    }
    harm_event = crime_psychology.get("harm_event")
    if isinstance(harm_event, Mapping):
        victim_id = harm_event.get("victim_id")
        if isinstance(victim_id, str):
            victim_ids.add(victim_id)
    return victim_ids


def ending_scene_id(scene_cards: Mapping[str, object]) -> str | None:
    """가장 높은 Scene Order의 Scene ID를 반환한다."""
    scenes = [
        scene
        for scene in mapping_records(scene_cards, "scenes")
        if isinstance(scene.get("order"), int)
        and not isinstance(scene.get("order"), bool)
        and isinstance(scene.get("scene_id"), str)
    ]
    if not scenes:
        return None
    return cast(str, max(scenes, key=lambda scene: cast(int, scene["order"]))["scene_id"])


def validate_victim_policy(
    policy: Mapping[str, object],
    crime_psychology: Mapping[str, object],
    characters: Mapping[str, object],
    scene_cards: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """피해자 행위 주체성, 책임 귀결, 비난 표현을 검증한다."""
    issues: list[ValidationIssue] = []
    agency = crime_psychology.get("victim_agency_outcome")
    agency_victim_id = agency.get("victim_id") if isinstance(agency, Mapping) else None
    valid_agency = (
        isinstance(agency, Mapping)
        and agency_victim_id in character_ids(characters)
        and agency_victim_id in crime_victim_ids(crime_psychology)
        and agency.get("ending_scene_id") == ending_scene_id(scene_cards)
        and nonempty_string(agency, "outcome")
    )
    if policy.get("require_agency_outcome") is True and not valid_agency:
        issues.append(
            make_policy_issue(
                "VICTIM_AGENCY_OUTCOME_MISSING",
                "피해자의 선택 결과는 피해자 Character와 Ending Scene에 연결되어야 합니다.",
                "01_CASE/crime_psychology.json",
                {
                    "victim_id": agency.get("victim_id") if isinstance(agency, Mapping) else None,
                    "ending_scene_id": (
                        agency.get("ending_scene_id") if isinstance(agency, Mapping) else None
                    ),
                    "expected_ending_scene_id": ending_scene_id(scene_cards),
                },
            )
        )
    if policy.get("require_responsible_agent_payoff") is True and (
        crime_psychology.get("responsible_agent") not in character_ids(characters)
        or not nonempty_string(crime_psychology, "responsible_agent_payoff")
    ):
        issues.append(
            make_policy_issue(
                "RESPONSIBLE_AGENT_PAYOFF_MISSING",
                "가해 책임 주체와 서사적 책임 귀결이 필요합니다.",
                "01_CASE/crime_psychology.json",
                {"responsible_agent": crime_psychology.get("responsible_agent")},
            )
        )
    prohibited = [
        phrase
        for phrase in string_values(policy, "prohibited_phrases")
        if phrase.casefold() in final_script.casefold()
    ]
    if prohibited:
        issues.append(
            make_policy_issue(
                "VICTIM_BLAMING_LANGUAGE",
                "피해자에게 범죄 책임을 전가하는 금지 표현이 있습니다.",
                "07_SCRIPT/final_script.md",
                {"phrases": prohibited},
            )
        )
    return issues


def claim_sources(claim_evidence: Mapping[str, object]) -> dict[str, set[str]]:
    """Claim ID를 Evidence Source ID 집합에 대응한다."""
    result: dict[str, set[str]] = {}
    for claim in mapping_records(claim_evidence, "claims"):
        claim_id = claim.get("claim_id", claim.get("fact_id"))
        if isinstance(claim_id, str):
            result[claim_id] = set(string_values(claim, "evidence_source_ids"))
    return result


def expert_required(
    policy: Mapping[str, object],
    source_truth: object,
    expert_document: Mapping[str, object],
) -> bool:
    """Source Mode와 명시적 N/A를 사용해 Expert 필요 여부를 계산한다."""
    if source_truth == "VERIFIED_TRUE_CASE":
        return policy.get("true_story_requirement") == "REQUIRED"
    if source_truth == "INSPIRED_BY_TRUE_EVENTS":
        requirement = policy.get("inspired_requirement")
        return requirement == "REQUIRED" or (
            requirement == "REQUIRED_OR_NA"
            and expert_document.get("status") != "NOT_APPLICABLE"
        )
    if source_truth == "ORIGINAL_FICTION":
        return policy.get("original_requirement") == "REQUIRED"
    return False


def validate_expert_policy(
    policy: Mapping[str, object],
    source_truth: object,
    claim_evidence: Mapping[str, object],
    expert_document: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    expert_script: str,
    production_expert_script: str,
    panel_script: str,
) -> list[ValidationIssue]:
    """Expert/Panel 분리, Script 정합성, Claim-Evidence를 검증한다."""
    records = mapping_records(expert_document, "segments")
    presentation = [
        segment
        for segment in presentation_segments(presentation_plan)
        if segment.get("segment_type") == "EXPERT_ANALYSIS"
    ]
    issues: list[ValidationIssue] = []
    if expert_required(policy, source_truth, expert_document) and not records:
        issues.append(
            make_policy_issue(
                "EXPERT_ANALYSIS_REQUIRED",
                "Source Mode 정책상 전문가 분석 Segment가 필요합니다.",
                "06_SCENE/expert_segments.json",
                {"source_truth_classification": source_truth},
            )
        )
    invalid_roles = sorted(
        {
            str(record.get("expert_role"))
            for record in records
            if record.get("expert_role") not in EXPERT_ROLES
        }
    )
    if invalid_roles:
        issues.append(
            make_policy_issue(
                "EXPERT_ROLE_INVALID",
                "허용되지 않은 Expert Role이 있습니다.",
                "06_SCENE/expert_segments.json",
                {"roles": invalid_roles},
            )
        )
    presentation_ids = {
        cast(str, segment["segment_id"])
        for segment in presentation
        if isinstance(segment.get("segment_id"), str)
    }
    record_ids = {
        cast(str, record["segment_id"])
        for record in records
        if isinstance(record.get("segment_id"), str)
    }
    parsed, malformed = parse_script_segments(expert_script)
    script_ids = {
        segment["segment_id"]
        for segment in parsed
        if segment["segment_type"] == "EXPERT_ANALYSIS"
    }
    production_script_ids: set[str] | None = None
    production_malformed = False
    if production_expert_script.strip():
        production_parsed, production_malformed = parse_script_segments(
            production_expert_script
        )
        production_script_ids = {
            segment["segment_id"]
            for segment in production_parsed
            if segment["segment_type"] == "EXPERT_ANALYSIS"
        }
    bad_sources = sorted(
        cast(str, segment.get("segment_id"))
        for segment in presentation
        if segment.get("source_artifact") != "expert_analysis_script"
        and isinstance(segment.get("segment_id"), str)
    )
    if (
        presentation_ids != record_ids
        or presentation_ids != script_ids
        or malformed
        or (
            production_script_ids is not None
            and production_script_ids != presentation_ids
        )
        or production_malformed
        or bad_sources
    ):
        issues.append(
            make_policy_issue(
                "EXPERT_SCRIPT_SEGMENT_MISMATCH",
                "Presentation, Expert Segment, Expert Script ID와 Source가 일치해야 합니다.",
                "07_SCRIPT/expert_analysis_script.md",
                {
                    "presentation_ids": sorted(presentation_ids),
                    "record_ids": sorted(record_ids),
                    "script_ids": sorted(script_ids),
                    "production_script_ids": (
                        sorted(production_script_ids)
                        if production_script_ids is not None
                        else None
                    ),
                    "bad_source_segment_ids": bad_sources,
                    "malformed_script": malformed,
                    "malformed_production_script": production_malformed,
                },
            )
        )
    spoken_lines = [
        cast(str, record["spoken_line"])
        for record in records
        if isinstance(record.get("spoken_line"), str)
    ]
    if "EXPERT_ANALYSIS" in panel_script or "[EXPERT-" in panel_script or any(
        line in panel_script for line in spoken_lines
    ):
        issues.append(
            make_policy_issue(
                "PANEL_OPINION_USED_AS_EXPERT_FACT",
                "Expert 발화를 Panel Reaction Script에 둘 수 없습니다.",
                "07_SCRIPT/panel_reaction_script.md",
                {},
            )
        )
    if policy.get("require_claim_evidence") is not True:
        return issues
    sources_by_claim = claim_sources(claim_evidence)
    unsupported: list[dict[str, object]] = []
    for record in records:
        declared_sources = set(string_values(record, "evidence_source_ids"))
        for claim_id in string_values(record, "claim_ids"):
            expected_sources = sources_by_claim.get(claim_id, set())
            if not expected_sources or not expected_sources.issubset(declared_sources):
                unsupported.append(
                    {"segment_id": record.get("segment_id"), "claim_id": claim_id}
                )
    if unsupported:
        issues.append(
            make_policy_issue(
                "EXPERT_ANALYSIS_UNSUPPORTED_CLAIM",
                "전문가 발화 Claim이 검증된 Evidence와 연결되지 않았습니다.",
                "06_SCENE/expert_segments.json",
                {"claims": unsupported},
            )
        )
    return issues


def validate_source_disclosure(
    policy: Mapping[str, object],
    source_truth: object,
    disclosure: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """Source Truth와 정확한 Audience Label 문구를 검증한다."""
    labels = policy.get("labels_by_source_truth")
    expected_mode = labels.get(source_truth) if isinstance(labels, Mapping) else None
    if expected_mode is None:
        expected_mode = source_truth
    actual_mode = disclosure.get("internal_mode")
    label_text = disclosure.get("audience_label_text")
    if source_truth == "ORIGINAL_FICTION" and actual_mode != "ORIGINAL_FICTION":
        return [
            make_policy_issue(
                "FICTION_PRESENTED_AS_TRUE",
                "창작 Story를 실화 또는 실화 기반으로 표시할 수 없습니다.",
                "01_CASE/source_disclosure.json",
                {"expected": "ORIGINAL_FICTION", "actual": actual_mode},
            )
        ]
    expected_text = SOURCE_LABEL_TEXTS.get(str(expected_mode))
    if (
        actual_mode != expected_mode
        or label_text != expected_text
        or not isinstance(label_text, str)
        or label_text not in final_script
    ):
        return [
            make_policy_issue(
                "SOURCE_DISCLOSURE_MISSING",
                "Source Mode에 맞는 정확한 Audience-facing Label 문구가 필요합니다.",
                "01_CASE/source_disclosure.json",
                {
                    "expected_mode": expected_mode,
                    "actual_mode": actual_mode,
                    "expected_text": expected_text,
                    "actual_text": label_text,
                    "present_in_final_script": (
                        isinstance(label_text, str) and label_text in final_script
                    ),
                },
            )
        ]
    return []


def validate_clinical_labels(
    policy: Mapping[str, object],
    clinical_document: Mapping[str, object],
    claim_evidence: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """임상 용어의 분류, 출처, 전문가 평가 여부를 분리 검증한다."""
    labels = mapping_records(clinical_document, "labels")
    labels_by_term = {
        term.casefold(): label
        for label in labels
        if isinstance((term := label.get("term")), str)
    }
    issues: list[ValidationIssue] = []
    missing_terms = [
        term
        for term in string_values(policy, "controlled_terms")
        if term.casefold() in final_script.casefold()
        and term.casefold() not in labels_by_term
    ]
    if missing_terms:
        issues.append(
            make_policy_issue(
                "UNSUPPORTED_CLINICAL_DIAGNOSIS",
                "임상 용어가 분류 없이 사용되었습니다.",
                "01_CASE/clinical_labels.json",
                {"terms": missing_terms},
            )
        )
    evidence = claim_sources(claim_evidence)
    missing_sources: list[dict[str, object]] = []
    unsupported: list[dict[str, object]] = []
    criminal_only: list[str] = []
    allowed = set(string_values(policy, "allowed_classifications"))
    for label in labels:
        term = label.get("term")
        classification = label.get("classification")
        source_claim_ids = string_values(label, "source_claim_ids")
        if not source_claim_ids or any(not evidence.get(claim_id) for claim_id in source_claim_ids):
            missing_sources.append(
                {"term": term, "source_claim_ids": source_claim_ids}
            )
        if classification not in allowed:
            unsupported.append({"term": term, "reason": "CLASSIFICATION_INVALID"})
            continue
        if classification not in CLINICAL_FACT_CLASSIFICATIONS:
            continue
        if (
            label.get("documented_assessment") is not True
            and isinstance(term, str)
        ):
            criminal_only.append(term)
        if (
            policy.get("diagnosis_requires_expert") is True
            and label.get("qualified_expert") is not True
        ) or (
            policy.get("diagnosis_requires_evidence") is True
            and (
                label.get("documented_assessment") is not True
                or not source_claim_ids
            )
        ):
            unsupported.append(
                {"term": term, "reason": "EXPERT_OR_ASSESSMENT_MISSING"}
            )
    if missing_sources:
        issues.append(
            make_policy_issue(
                "CLINICAL_LABEL_SOURCE_MISSING",
                "임상 용어 분류에 검증된 Source Claim이 없습니다.",
                "01_CASE/clinical_labels.json",
                {"labels": missing_sources},
            )
        )
    if criminal_only:
        issues.append(
            make_policy_issue(
                "CRIMINAL_ACT_TREATED_AS_DIAGNOSIS",
                "범죄 행위만으로 임상 진단을 확정할 수 없습니다.",
                "01_CASE/clinical_labels.json",
                {"terms": sorted(criminal_only)},
            )
        )
    if unsupported:
        issues.append(
            make_policy_issue(
                "UNSUPPORTED_CLINICAL_DIAGNOSIS",
                "임상 용어가 적절한 전문가 평가와 문서 근거 없이 사용되었습니다.",
                "01_CASE/clinical_labels.json",
                {"labels": unsupported},
            )
        )
    return issues


def validate_episode_theme(
    policy: Mapping[str, object],
    story_dna: Mapping[str, object],
    crime_psychology: Mapping[str, object],
) -> list[ValidationIssue]:
    """Episode Theme 존재와 Case Trace 일치를 검증한다."""
    case_theme = crime_psychology.get("episode_theme")
    story_theme = story_dna.get("episode_theme")
    if policy.get("require_episode_theme") is True and not isinstance(case_theme, str):
        return [
            make_policy_issue(
                "EPISODE_THEME_MISSING",
                "v2 Episode Theme이 필요합니다.",
                "01_CASE/crime_psychology.json",
                {},
            )
        ]
    allowed = set(string_values(policy, "allowed_themes"))
    if (
        isinstance(case_theme, str)
        and (case_theme not in allowed or story_theme != case_theme)
    ):
        return [
            make_policy_issue(
                "EPISODE_THEME_CASE_MISMATCH",
                "Episode Theme이 Channel 허용값 또는 Story DNA와 일치하지 않습니다.",
                "01_CASE/crime_psychology.json",
                {
                    "case_theme": case_theme,
                    "story_theme": story_theme,
                    "allowed_themes": sorted(allowed),
                },
            )
        ]
    return []


def validate_channel_policy_v2(
    channel: Mapping[str, object],
    inputs: ChannelPolicyInputs,
) -> list[ValidationIssue]:
    """활성 v2 Capability를 First-class Artifact에 적용한다."""
    production_config = inputs["production_config"]
    if not v2_policy_applies(production_config):
        return []
    capabilities = mapping_or_empty(channel, "capabilities")
    story_dna = mapping_or_empty(inputs["story_document"], "story_dna")
    crime = inputs["crime_psychology"]
    source_truth = production_config.get("source_truth_classification")
    issues: list[ValidationIssue] = []
    crime_policy = enabled_policy(capabilities, "CRIME_PSYCHOLOGY_POLICY")
    if crime_policy is not None:
        issues.extend(
            validate_crime_policy(
                crime_policy,
                production_config,
                story_dna,
                inputs["case_input"],
                crime,
            )
        )
        issues.extend(validate_technical_reveal(crime_policy, inputs["clue_matrix"]))
    issues.extend(
        validate_trust_and_control(
            enabled_policy(capabilities, "TRUST_AND_SAFETY_BETRAYAL_POLICY"),
            enabled_policy(capabilities, "COERCIVE_CONTROL_POLICY"),
            crime,
        )
    )
    if enabled_policy(capabilities, "COERCIVE_CONTROL_POLICY") is not None:
        issues.extend(validate_control_order(crime))
        issues.extend(
            validate_control_trace_links(
                crime,
                inputs["characters"],
                inputs["scene_cards"],
            )
        )
    victim_policy = enabled_policy(capabilities, "VICTIM_CENTERED_POLICY")
    if victim_policy is not None:
        issues.extend(
            validate_victim_policy(
                victim_policy,
                crime,
                inputs["characters"],
                inputs["scene_cards"],
                inputs["final_script"],
            )
        )
    risk_policy = enabled_policy(
        capabilities,
        "RISK_SIGNAL_AND_PUBLIC_VALUE_POLICY",
    )
    if risk_policy is not None and risk_policy.get("require_risk_signal_payoff") is True:
        issues.extend(
            missing_string_issue(
                crime,
                "risk_signal_payoff",
                "RISK_SIGNAL_PAYOFF_MISSING",
                "초기 위험 신호가 후반에 의미 있게 회수되어야 합니다.",
                "01_CASE/crime_psychology.json",
            )
        )
    expert_policy = enabled_policy(capabilities, "EXPERT_ANALYSIS_POLICY")
    if expert_policy is not None:
        issues.extend(
            validate_expert_policy(
                expert_policy,
                source_truth,
                inputs["claim_evidence"],
                inputs["expert_segments"],
                inputs["presentation_plan"],
                inputs["expert_analysis_script"],
                inputs["production_expert_analysis_script"],
                inputs["panel_reaction_script"],
            )
        )
    source_policy = enabled_policy(capabilities, "SOURCE_DISCLOSURE_POLICY")
    if source_policy is not None:
        issues.extend(
            validate_source_disclosure(
                source_policy,
                source_truth,
                inputs["source_disclosure"],
                inputs["final_script"],
            )
        )
    clinical_policy = enabled_policy(capabilities, "CLINICAL_LABEL_POLICY")
    if clinical_policy is not None:
        issues.extend(
            validate_clinical_labels(
                clinical_policy,
                inputs["clinical_labels"],
                inputs["claim_evidence"],
                inputs["final_script"],
            )
        )
    theme_policy = enabled_policy(capabilities, "EPISODE_THEME_POLICY")
    if theme_policy is not None:
        issues.extend(validate_episode_theme(theme_policy, story_dna, crime))
    return issues

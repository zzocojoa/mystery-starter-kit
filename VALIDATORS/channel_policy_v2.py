"""Channel Content Version 2.0 이상에만 적용하는 정책 검증."""

from collections.abc import Mapping, Sequence

from VALIDATORS.compatibility import mapping_or_empty, parse_semantic_version
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

V2_MINIMUM_VERSION = (2, 0, 0)
TRUE_PRESENTATION_LABELS = frozenset(
    {"VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"}
)
CLINICAL_FACT_CLASSIFICATIONS = frozenset(
    {"CONFIRMED_DIAGNOSIS", "EXPERT_ASSESSMENT"}
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


def nonempty_string(document: Mapping[str, object], key: str) -> bool:
    """필드가 공백이 아닌 문자열인지 판정한다."""
    value = document.get(key)
    return isinstance(value, str) and bool(value.strip())


def nonempty_sequence(document: Mapping[str, object], key: str) -> bool:
    """필드가 하나 이상의 항목을 가진 배열인지 판정한다."""
    value = document.get(key)
    return isinstance(value, list) and bool(value)


def string_sequence(document: Mapping[str, object], key: str) -> list[str]:
    """문서의 문자열 배열만 복사해 반환한다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def mapping_sequence(
    document: Mapping[str, object],
    key: str,
) -> list[Mapping[str, object]]:
    """문서의 객체 배열만 복사해 반환한다."""
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def required_string_issue(
    document: Mapping[str, object],
    key: str,
    code: str,
    message: str,
) -> list[ValidationIssue]:
    """필수 문자열 누락을 한 건의 정책 Issue로 변환한다."""
    if nonempty_string(document, key):
        return []
    return [
        make_policy_issue(
            code,
            message,
            "00_PROJECT/story_dna.json",
            {"field": key},
        )
    ]


def required_sequence_issue(
    document: Mapping[str, object],
    key: str,
    code: str,
    message: str,
) -> list[ValidationIssue]:
    """필수 배열 누락을 한 건의 정책 Issue로 변환한다."""
    if nonempty_sequence(document, key):
        return []
    return [
        make_policy_issue(
            code,
            message,
            "00_PROJECT/story_dna.json",
            {"field": key},
        )
    ]


def validate_crime_psychology_policy(
    policy: Mapping[str, object],
    production_config: Mapping[str, object],
    story_dna: Mapping[str, object],
    case_input: Mapping[str, object],
) -> list[ValidationIssue]:
    """범죄 위협, 심리 압박, 기술·절차 편향을 검증한다."""
    issues: list[ValidationIssue] = []
    primary_genres = string_sequence(policy, "primary_genres")
    genre = production_config.get("genre")
    if primary_genres and genre not in primary_genres:
        issues.append(
            make_policy_issue(
                "CHANNEL_PRIMARY_GENRE_MISMATCH",
                "프로젝트 장르가 v2 Channel의 주 장르와 다릅니다.",
                "00_PROJECT/production_config.json",
                {"genre": genre, "primary_genres": primary_genres},
            )
        )

    threat_types = string_sequence(policy, "threat_types")
    threat_type = story_dna.get("threat_type")
    if (
        threat_type not in threat_types
        or not nonempty_string(story_dna, "harm_mechanism")
        or not nonempty_string(case_input, "central_mystery")
    ):
        issues.append(
            make_policy_issue(
                "CRIME_OR_PREDATORY_THREAT_MISSING",
                "범죄 또는 약탈적 위협과 구체적 피해 메커니즘이 필요합니다.",
                "00_PROJECT/story_dna.json",
                {"threat_type": threat_type, "allowed": threat_types},
            )
        )

    if policy.get("require_psychological_pressure") is True:
        issues.extend(
            required_string_issue(
                story_dna,
                "psychological_pressure",
                "PSYCHOLOGICAL_PRESSURE_MISSING",
                "인물에게 작동하는 심리적 압박이 필요합니다.",
            )
        )

    mechanisms = [
        *string_sequence(story_dna, "information_mechanism"),
        *string_sequence(story_dna, "clue_mechanism"),
    ]
    technical_markers = set(string_sequence(policy, "technical_markers"))
    maximum_ratio = policy.get("max_technical_clue_ratio")
    technical_count = sum(item in technical_markers for item in mechanisms)
    technical_ratio = technical_count / len(mechanisms) if mechanisms else 0.0
    if (
        isinstance(maximum_ratio, int | float)
        and not isinstance(maximum_ratio, bool)
        and technical_ratio > float(maximum_ratio)
    ):
        issues.append(
            make_policy_issue(
                "TECHNICAL_PUZZLE_DOMINANCE",
                "기술 단서 비중이 Channel 정책 상한을 초과합니다.",
                "00_PROJECT/story_dna.json",
                {"actual_ratio": technical_ratio, "maximum_ratio": maximum_ratio},
            )
        )

    procedural_markers = set(string_sequence(policy, "procedural_markers"))
    dramatic_engine = mapping_or_empty(story_dna, "dramatic_engine")
    procedural_values = {
        story_dna.get("architecture"),
        story_dna.get("reveal_mode"),
        story_dna.get("incident_type"),
        dramatic_engine.get("primary"),
    }
    collisions = sorted(
        value
        for value in procedural_values
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


def validate_trust_policy(
    policy: Mapping[str, object],
    story_dna: Mapping[str, object],
) -> list[ValidationIssue]:
    """신뢰 영역과 안전 기대의 배신 구조를 검증한다."""
    issues: list[ValidationIssue] = []
    if policy.get("require_trusted_domain") is True:
        issues.extend(
            required_string_issue(
                story_dna,
                "trusted_domain",
                "TRUSTED_DOMAIN_MISSING",
                "피해자가 신뢰한 생활 영역이 필요합니다.",
            )
        )
    if policy.get("require_safe_domain_expectation") is True:
        issues.extend(
            required_string_issue(
                story_dna,
                "safe_domain_expectation",
                "SAFE_DOMAIN_BETRAYAL_MISSING",
                "안전하다고 믿은 기대가 어떻게 배신되는지 필요합니다.",
            )
        )
    return issues


def validate_coercive_control_policy(
    policy: Mapping[str, object],
    story_dna: Mapping[str, object],
) -> list[ValidationIssue]:
    """경고 신호부터 이탈 장벽까지의 통제 과정을 검증한다."""
    checks: tuple[tuple[str, str, str, object], ...] = (
        (
            "early_warning_signals",
            "EARLY_WARNING_SIGNAL_MISSING",
            "초기 위험 신호가 필요합니다.",
            policy.get("require_warning_signals"),
        ),
        (
            "boundary_erosion_steps",
            "BOUNDARY_EROSION_MISSING",
            "경계가 침식되는 단계가 필요합니다.",
            policy.get("require_boundary_erosion"),
        ),
        (
            "control_tactics",
            "COERCIVE_CONTROL_PROCESS_MISSING",
            "강압적 통제 과정이 필요합니다.",
            policy.get("require_control_tactics"),
        ),
        (
            "victim_exit_barriers",
            "VICTIM_EXIT_BARRIER_MISSING",
            "피해자가 즉시 벗어나기 어려운 장벽이 필요합니다.",
            policy.get("require_exit_barriers"),
        ),
    )
    issues: list[ValidationIssue] = []
    for field, code, message, required in checks:
        if required is True:
            issues.extend(required_sequence_issue(story_dna, field, code, message))
    return issues


def validate_victim_centered_policy(
    policy: Mapping[str, object],
    story_dna: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """피해자 행위 주체성, 책임 귀속, 비난 표현을 검증한다."""
    issues: list[ValidationIssue] = []
    if policy.get("require_agency_outcome") is True:
        issues.extend(
            required_string_issue(
                story_dna,
                "victim_agency_outcome",
                "VICTIM_AGENCY_OUTCOME_MISSING",
                "피해자의 선택과 회복 결과가 필요합니다.",
            )
        )
    if policy.get("require_responsible_agent_payoff") is True and (
        not nonempty_string(story_dna, "responsible_agent")
        or not nonempty_string(story_dna, "responsible_agent_payoff")
    ):
        issues.append(
            make_policy_issue(
                "RESPONSIBLE_AGENT_PAYOFF_MISSING",
                "가해 책임 주체와 서사적 책임 귀결이 필요합니다.",
                "00_PROJECT/story_dna.json",
                {
                    "responsible_agent": story_dna.get("responsible_agent"),
                    "responsible_agent_payoff": story_dna.get(
                        "responsible_agent_payoff"
                    ),
                },
            )
        )
    lowered_script = final_script.casefold()
    prohibited = [
        phrase
        for phrase in string_sequence(policy, "prohibited_phrases")
        if phrase.casefold() in lowered_script
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


def expert_segments(
    presentation_plan: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Presentation Plan의 전문가 분석 Segment를 반환한다."""
    return [
        segment
        for segment in mapping_sequence(presentation_plan, "segments")
        if segment.get("segment_type") == "EXPERT_ANALYSIS"
    ]


def claim_evidence_map(
    claim_evidence: Mapping[str, object],
) -> dict[str, set[str]]:
    """Claim ID를 근거 Source ID 집합에 대응한다."""
    result: dict[str, set[str]] = {}
    for claim in mapping_sequence(claim_evidence, "claims"):
        claim_id = claim.get("claim_id", claim.get("fact_id"))
        if not isinstance(claim_id, str):
            continue
        result[claim_id] = set(string_sequence(claim, "evidence_source_ids"))
    return result


def explicit_expert_na(story_dna: Mapping[str, object]) -> bool:
    """전문가 분석 N/A 근거가 명시됐는지 판정한다."""
    plan = story_dna.get("expert_debrief_plan")
    return (
        isinstance(plan, Mapping)
        and plan.get("status") == "NOT_APPLICABLE"
        and nonempty_string(plan, "na_reason")
    )


def expert_is_required(
    policy: Mapping[str, object],
    source_mode: object,
    story_dna: Mapping[str, object],
) -> bool:
    """Source Mode와 정책에 따라 전문가 Segment 필요 여부를 계산한다."""
    if source_mode == "TRUE_STORY":
        return policy.get("true_story_requirement") == "REQUIRED"
    if source_mode == "INSPIRED_BY_TRUE_EVENTS":
        requirement = policy.get("inspired_requirement")
        if requirement == "REQUIRED":
            return True
        if requirement == "REQUIRED_OR_NA":
            return not explicit_expert_na(story_dna)
        return False
    if source_mode == "ORIGINAL":
        return policy.get("original_requirement") == "REQUIRED"
    return False


def validate_expert_analysis_policy(
    policy: Mapping[str, object],
    source_mode: object,
    story_dna: Mapping[str, object],
    claim_evidence: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """전문가 Segment 요구와 Claim-Evidence 연결을 검증한다."""
    segments = expert_segments(presentation_plan)
    issues: list[ValidationIssue] = []
    if expert_is_required(policy, source_mode, story_dna) and not segments:
        issues.append(
            make_policy_issue(
                "EXPERT_ANALYSIS_REQUIRED",
                "Source Mode 정책상 전문가 분석 Segment가 필요합니다.",
                "06_SCENE/presentation_plan.json",
                {"story_source_mode": source_mode},
            )
        )
    if policy.get("require_claim_evidence") is not True:
        return issues

    evidence_by_claim = claim_evidence_map(claim_evidence)
    unsupported: list[dict[str, object]] = []
    for segment in segments:
        segment_id = segment.get("segment_id")
        analysis = segment.get("expert_analysis")
        if not isinstance(analysis, Mapping):
            unsupported.append({"segment_id": segment_id, "claim_ids": []})
            continue
        declared_sources = set(string_sequence(analysis, "evidence_source_ids"))
        for claim_id in string_sequence(analysis, "claim_ids"):
            evidence_sources = evidence_by_claim.get(claim_id, set())
            if not evidence_sources or not evidence_sources.issubset(declared_sources):
                unsupported.append(
                    {"segment_id": segment_id, "claim_id": claim_id}
                )
    if unsupported:
        issues.append(
            make_policy_issue(
                "EXPERT_ANALYSIS_UNSUPPORTED_CLAIM",
                "전문가 발화 Claim이 검증된 Evidence와 연결되지 않았습니다.",
                "06_SCENE/presentation_plan.json",
                {"claims": unsupported},
            )
        )
    return issues


def validate_source_disclosure_policy(
    policy: Mapping[str, object],
    source_mode: object,
    story_dna: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """Audience-facing 출처 Label과 Story Source Mode를 교차 검증한다."""
    labels = policy.get("labels_by_source_mode")
    expected = labels.get(source_mode) if isinstance(labels, Mapping) else None
    actual = story_dna.get("source_disclosure_mode")
    if source_mode == "ORIGINAL" and actual in TRUE_PRESENTATION_LABELS:
        return [
            make_policy_issue(
                "FICTION_PRESENTED_AS_TRUE",
                "창작 Story를 실화 또는 실화 기반으로 표시할 수 없습니다.",
                "00_PROJECT/story_dna.json",
                {"expected": expected, "actual": actual},
            )
        ]
    if (
        not isinstance(actual, str)
        or actual != expected
        or actual not in final_script
    ):
        return [
            make_policy_issue(
                "SOURCE_DISCLOSURE_MISSING",
                "Story Source Mode와 일치하는 Audience-facing Label이 필요합니다.",
                "00_PROJECT/story_dna.json",
                {
                    "expected": expected,
                    "actual": actual,
                    "label_present_in_script": (
                        isinstance(actual, str) and actual in final_script
                    ),
                },
            )
        ]
    return []


def matching_expert_claim(
    segments: Sequence[Mapping[str, object]],
    expert_id: str,
    claim_id: str,
) -> bool:
    """지정 전문가와 Claim이 같은 전문가 Segment에 있는지 판정한다."""
    for segment in segments:
        analysis = segment.get("expert_analysis")
        if not isinstance(analysis, Mapping):
            continue
        if analysis.get("expert_id") != expert_id:
            continue
        if claim_id in string_sequence(analysis, "claim_ids"):
            return True
    return False


def validate_clinical_label_policy(
    policy: Mapping[str, object],
    story_dna: Mapping[str, object],
    claim_evidence: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """임상 용어의 분류, 전문가 귀속, 근거 연결을 검증한다."""
    entries = mapping_sequence(story_dna, "clinical_label_classification")
    entries_by_term = {
        term.casefold(): entry
        for entry in entries
        if isinstance((term := entry.get("term")), str)
    }
    controlled_terms = string_sequence(policy, "controlled_terms")
    allowed = set(string_sequence(policy, "allowed_classifications"))
    evidence_by_claim = claim_evidence_map(claim_evidence)
    segments = expert_segments(presentation_plan)
    unsupported: list[dict[str, object]] = []

    for term in controlled_terms:
        if term.casefold() in final_script.casefold() and term.casefold() not in entries_by_term:
            unsupported.append({"term": term, "reason": "CLASSIFICATION_MISSING"})

    for entry in entries:
        term = entry.get("term")
        classification = entry.get("classification")
        if not isinstance(term, str) or classification not in allowed:
            unsupported.append({"term": term, "reason": "CLASSIFICATION_INVALID"})
            continue
        if entry.get("asserted_as_fact") is True and classification not in (
            "CONFIRMED_DIAGNOSIS",
            "EXPERT_ASSESSMENT",
        ):
            unsupported.append({"term": term, "reason": "UNVERIFIED_AS_FACT"})
        if classification not in CLINICAL_FACT_CLASSIFICATIONS:
            continue
        claim_id = entry.get("claim_id")
        expert_id = entry.get("expert_id")
        if (
            policy.get("diagnosis_requires_evidence") is True
            and (
                not isinstance(claim_id, str)
                or not evidence_by_claim.get(claim_id)
            )
        ):
            unsupported.append({"term": term, "reason": "EVIDENCE_MISSING"})
        if (
            policy.get("diagnosis_requires_expert") is True
            and (
                not isinstance(expert_id, str)
                or not isinstance(claim_id, str)
                or not matching_expert_claim(segments, expert_id, claim_id)
            )
        ):
            unsupported.append({"term": term, "reason": "EXPERT_LINK_MISSING"})

    if not unsupported:
        return []
    return [
        make_policy_issue(
            "UNSUPPORTED_CLINICAL_DIAGNOSIS",
            "임상 용어가 적절한 분류·전문가·근거 없이 사용되었습니다.",
            "00_PROJECT/story_dna.json",
            {"labels": unsupported},
        )
    ]


def validate_channel_policy_v2(
    channel: Mapping[str, object],
    story_document: Mapping[str, object],
    production_config: Mapping[str, object],
    case_input: Mapping[str, object],
    claim_evidence: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """활성 v2 Capability만 조합해 Project 정책 준수 여부를 판정한다."""
    if not v2_policy_applies(production_config):
        return []
    capabilities = mapping_or_empty(channel, "capabilities")
    story_dna = mapping_or_empty(story_document, "story_dna")
    source_mode = production_config.get("story_source_mode")
    issues: list[ValidationIssue] = []

    crime_policy = enabled_policy(capabilities, "CRIME_PSYCHOLOGY_POLICY")
    if crime_policy is not None:
        issues.extend(
            validate_crime_psychology_policy(
                crime_policy,
                production_config,
                story_dna,
                case_input,
            )
        )
    trust_policy = enabled_policy(
        capabilities,
        "TRUST_AND_SAFETY_BETRAYAL_POLICY",
    )
    if trust_policy is not None:
        issues.extend(validate_trust_policy(trust_policy, story_dna))
    control_policy = enabled_policy(capabilities, "COERCIVE_CONTROL_POLICY")
    if control_policy is not None:
        issues.extend(validate_coercive_control_policy(control_policy, story_dna))
    victim_policy = enabled_policy(capabilities, "VICTIM_CENTERED_POLICY")
    if victim_policy is not None:
        issues.extend(
            validate_victim_centered_policy(victim_policy, story_dna, final_script)
        )
    risk_policy = enabled_policy(
        capabilities,
        "RISK_SIGNAL_AND_PUBLIC_VALUE_POLICY",
    )
    if risk_policy is not None and risk_policy.get("require_risk_signal_payoff") is True:
        issues.extend(
            required_string_issue(
                story_dna,
                "risk_signal_payoff",
                "RISK_SIGNAL_PAYOFF_MISSING",
                "초기 위험 신호가 후반에 의미 있게 회수되어야 합니다.",
            )
        )
    expert_policy = enabled_policy(capabilities, "EXPERT_ANALYSIS_POLICY")
    if expert_policy is not None:
        issues.extend(
            validate_expert_analysis_policy(
                expert_policy,
                source_mode,
                story_dna,
                claim_evidence,
                presentation_plan,
            )
        )
    source_policy = enabled_policy(capabilities, "SOURCE_DISCLOSURE_POLICY")
    if source_policy is not None:
        issues.extend(
            validate_source_disclosure_policy(
                source_policy,
                source_mode,
                story_dna,
                final_script,
            )
        )
    clinical_policy = enabled_policy(capabilities, "CLINICAL_LABEL_POLICY")
    if clinical_policy is not None:
        issues.extend(
            validate_clinical_label_policy(
                clinical_policy,
                story_dna,
                claim_evidence,
                presentation_plan,
                final_script,
            )
        )

    return issues

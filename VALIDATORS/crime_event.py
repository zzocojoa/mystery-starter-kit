"""구체적 대인범죄 사건을 Candidate부터 Final Script까지 추적한다."""

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import cast

from VALIDATORS.models import ValidationIssue
from VALIDATORS.presentation_validation import (
    canonical_mode,
    parse_script_segments,
    presentation_segments,
)

CORE_CRIMES = frozenset(
    {
        "MURDER",
        "KIDNAPPING",
        "CONFINEMENT",
        "ASSAULT",
        "STALKING",
        "HOME_INVASION",
        "DATING_VIOLENCE",
        "DOMESTIC_VIOLENCE",
    }
)
CRIME_ACTIONS = frozenset(
    {
        "MURDER",
        "KIDNAPPING",
        "CONFINEMENT",
        "ASSAULT",
        "STALKING",
        "HOME_INVASION",
    }
)
RELATIONSHIP_CRIMES = frozenset({"DATING_VIOLENCE", "DOMESTIC_VIOLENCE"})
ACTION_HARM_REQUIREMENTS: Mapping[str, frozenset[str]] = {
    "MURDER": frozenset({"FATALITY"}),
    "KIDNAPPING": frozenset({"LIBERTY_DEPRIVATION", "COMPOUND_HARM"}),
    "CONFINEMENT": frozenset({"LIBERTY_DEPRIVATION", "COMPOUND_HARM"}),
    "ASSAULT": frozenset({"BODILY_INJURY", "THREAT_OR_TRAUMA", "COMPOUND_HARM"}),
    "STALKING": frozenset({"SAFETY_COLLAPSE", "THREAT_OR_TRAUMA", "COMPOUND_HARM"}),
    "HOME_INVASION": frozenset(
        {"SAFETY_COLLAPSE", "THREAT_OR_TRAUMA", "BODILY_INJURY", "COMPOUND_HARM"}
    ),
}
DEFAULT_DEVELOPMENT_FUNCTIONS: Mapping[str, tuple[str, ...]] = {
    "MURDER": (
        "HARM_OR_DANGER_RECOGNITION",
        "INVOLVEMENT_OR_SUSPICION",
        "MOTIVE_AND_RESPONSIBILITY",
        "EVENT_RECONSTRUCTION",
    ),
    "LIBERTY_CRIME": (
        "LIBERTY_DEPRIVATION",
        "THREAT_AND_CHOICE_CONSTRAINT",
        "RESPONSE_OR_DISCOVERY",
        "HARM_OUTCOME",
    ),
    "RELATIONAL_VIOLENCE": (
        "VIOLENCE_OR_THREAT",
        "RELATIONSHIP_AND_POWER",
        "RESPONSE_BARRIER",
        "VIOLENCE_OUTCOME",
    ),
    "ACCESS_CRIME": (
        "REPEATED_ACCESS_OR_INTRUSION",
        "SAFETY_COLLAPSE",
        "SAFETY_RESPONSE",
        "OFFENDER_RESPONSIBILITY",
    ),
}
REQUIRED_REVEAL_TYPES = frozenset({"CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"})
SUBJECTIVE_NARRATION_FUNCTIONS = frozenset(
    {
        "CHARACTER_ANCHOR",
        "SUBJECTIVE_EXPERIENCE",
        "EMOTIONAL_CONTINUITY",
        "MEMORY",
        "MISUNDERSTANDING",
        "TIME_COMPRESSION",
    }
)
FORBIDDEN_NARRATION_FUNCTIONS = frozenset(
    {"CLUE_EXPLANATION", "EVIDENCE_ANALYSIS", "SOLUTION_EXPOSITION", "ANSWER_DIRECTIVE"}
)
PANEL_PURSUIT_FUNCTIONS = frozenset(
    {
        "ANOMALY_DETECTION",
        "HYPOTHESIS_GENERATION",
        "SUSPECT_DISCUSSION",
        "HYPOTHESIS_REVISION",
        "CONTRADICTION_DETECTION",
        "BELIEF_CORRECTION",
    }
)
CRIME_EVENT_TAG = re.compile(r"\[CRIME_EVENT:(EVENT-[0-9]{2,})\]")
CRIME_ACTION_TAG = re.compile(r"\[CRIME_ACTION:([A-Z][A-Z0-9_]*)\]")
HARM_TAG = re.compile(r"\[HARM:(HARM-[0-9]{2,})\]")
CAUSE_TAG = re.compile(r"\[CAUSES:(EVENT-[0-9]{2,})>(HARM-[0-9]{2,})\]")


def mapping_records(document: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    """객체 배열 필드를 안전하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_values(document: Mapping[str, object], field: str) -> list[str]:
    """문자열 배열 필드를 안전하게 읽는다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def canonical_json_hash(value: object) -> str:
    """JSON 값을 정규 직렬화한 SHA-256을 반환한다."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def explicit_crime_policy(
    channel: Mapping[str, object],
) -> Mapping[str, object] | None:
    """활성화된 구체 대인범죄 정책만 반환한다."""
    capabilities = channel.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return None
    policy = capabilities.get("EXPLICIT_CRIME_EVENT_POLICY")
    if not isinstance(policy, Mapping) or policy.get("enabled") is not True:
        return None
    return policy


def crime_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """구체 범죄 사건 문제를 공통 Issue 형식으로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def development_families(primary_crime: object, action_type: object) -> set[str]:
    """중첩 가능한 범죄 분류를 서사 기능 Family 집합으로 변환한다."""
    families: set[str] = set()
    if primary_crime == "MURDER" or action_type == "MURDER":
        families.add("MURDER")
    if primary_crime in {"KIDNAPPING", "CONFINEMENT"} or action_type in {
        "KIDNAPPING",
        "CONFINEMENT",
    }:
        families.add("LIBERTY_CRIME")
    if primary_crime in {"ASSAULT", *RELATIONSHIP_CRIMES} or action_type == "ASSAULT":
        families.add("RELATIONAL_VIOLENCE")
    if primary_crime in {"STALKING", "HOME_INVASION"} or action_type in {
        "STALKING",
        "HOME_INVASION",
    }:
        families.add("ACCESS_CRIME")
    return families


def policy_development_functions(
    policy: Mapping[str, object],
    primary_crime: object,
    action_type: object,
) -> set[str]:
    """범죄 유형에 필요한 비순차 서사 기능을 반환한다."""
    definitions = policy.get("development_functions_by_family")
    required: set[str] = set()
    for family in development_families(primary_crime, action_type):
        values = definitions.get(family) if isinstance(definitions, Mapping) else None
        if isinstance(values, list) and all(isinstance(item, str) for item in values):
            required.update(cast(list[str], values))
        else:
            required.update(DEFAULT_DEVELOPMENT_FUNCTIONS[family])
    return required


def event_semantic_shape_issues(
    policy: Mapping[str, object],
    event: Mapping[str, object],
    artifact: str,
) -> list[ValidationIssue]:
    """태그가 아닌 행위·관계·피해 구조로 중심 사건을 검증한다."""
    primary = event.get("primary_crime")
    action_type = event.get("core_action_type")
    related = set(string_values(event, "related_crimes"))
    harms = set(string_values(event, "harm_classifications"))
    actors = set(string_values(event, "actor_ids"))
    victims = set(string_values(event, "victim_ids"))
    functions = set(string_values(event, "development_functions"))
    reveal_types = {
        target.get("target_type")
        for target in mapping_records(event, "reveal_targets")
        if isinstance(target.get("target_type"), str)
    }
    allowed_crimes = set(string_values(policy, "core_crimes")) or set(CORE_CRIMES)
    issues: list[ValidationIssue] = []
    if primary not in allowed_crimes or primary not in CORE_CRIMES:
        issues.append(
            crime_issue(
                "EXPLICIT_CORE_CRIME_MISSING",
                "중심 사건은 허용된 구체 대인범죄여야 합니다.",
                artifact,
                {"primary_crime": primary, "allowed": sorted(allowed_crimes)},
            )
        )
    if action_type not in CRIME_ACTIONS:
        issues.append(
            crime_issue(
                "EXPLICIT_CRIME_ACTION_MISSING",
                "장르 태그와 별도로 실제 대인범죄 행위 유형이 필요합니다.",
                artifact,
                {"core_action_type": action_type},
            )
        )
    if (
        primary in CRIME_ACTIONS
        and action_type in CRIME_ACTIONS
        and primary != action_type
        and primary not in related
    ):
        issues.append(
            crime_issue(
                "CRIME_TAG_ACTION_MISMATCH",
                "중심 범죄 분류와 실제 행위가 연결되지 않았습니다.",
                artifact,
                {"primary_crime": primary, "core_action_type": action_type},
            )
        )
    required_harms = ACTION_HARM_REQUIREMENTS.get(str(action_type), frozenset())
    if not harms.intersection(required_harms):
        issues.append(
            crime_issue(
                "CONCRETE_HARM_RESULT_MISSING",
                "실제 범죄 행위에 인과적으로 맞는 구체 피해 결과가 필요합니다.",
                artifact,
                {
                    "core_action_type": action_type,
                    "harm_classifications": sorted(harms),
                    "required_any_of": sorted(required_harms),
                },
            )
        )
    if not actors or not victims or actors.intersection(victims):
        issues.append(
            crime_issue(
                "CRIME_PARTICIPANT_ROLES_INVALID",
                "행위자와 피해자는 분리된 비어 있지 않은 ID 집합이어야 합니다.",
                artifact,
                {"actor_ids": sorted(actors), "victim_ids": sorted(victims)},
            )
        )
    if event.get("centrality") not in {None, "CENTRAL"}:
        issues.append(
            crime_issue(
                "CRIME_EVENT_NOT_CENTRAL",
                "구체 대인범죄는 배경 태그가 아니라 중심 사건이어야 합니다.",
                artifact,
                {"centrality": event.get("centrality")},
            )
        )
    required_functions = policy_development_functions(policy, primary, action_type)
    if not required_functions.issubset(functions):
        issues.append(
            crime_issue(
                "CRIME_DEVELOPMENT_FUNCTION_MISSING",
                "범죄 유형별 서사 기능이 누락되었습니다. 기능의 순서는 강제하지 않습니다.",
                artifact,
                {"missing_functions": sorted(required_functions - functions)},
            )
        )
    required_reveals = set(string_values(policy, "required_reveal_targets"))
    required_reveals = required_reveals or set(REQUIRED_REVEAL_TYPES)
    if not required_reveals.issubset(reveal_types):
        issues.append(
            crime_issue(
                "CRIME_REVEAL_TARGET_MISSING",
                "후반에 공개할 범인·동기·방식·피해 결과가 모두 계획되어야 합니다.",
                artifact,
                {"missing_target_types": sorted(required_reveals - reveal_types)},
            )
        )
    if event.get("method_detail_level") != "NON_ACTIONABLE_SUMMARY_ONLY":
        issues.append(
            crime_issue(
                "CRIME_METHOD_DETAIL_UNSAFE",
                "범행 방식은 비실행적 고수준 요약으로만 기록해야 합니다.",
                artifact,
                {"method_detail_level": event.get("method_detail_level")},
            )
        )
    return issues


def validate_candidate_crime_event(
    channel: Mapping[str, object],
    candidate: Mapping[str, object],
) -> list[ValidationIssue]:
    """Candidate가 태그가 아닌 실제 중심 대인범죄 개요를 갖는지 검증한다."""
    policy = explicit_crime_policy(channel)
    if policy is None:
        return []
    event = candidate.get("crime_event")
    if not isinstance(event, Mapping):
        return [
            crime_issue(
                "CANDIDATE_CRIME_EVENT_MISSING",
                "Candidate에 인과적인 구체 범죄 사건 개요가 필요합니다.",
                "00_PROJECT/variation_candidates.json",
                {"candidate_id": candidate.get("candidate_id")},
            )
        ]
    return event_semantic_shape_issues(
        policy,
        event,
        "00_PROJECT/variation_candidates.json",
    )


def approved_candidate(
    variations: Mapping[str, object],
) -> Mapping[str, object] | None:
    """승인된 Candidate 객체를 반환한다."""
    approved_id = variations.get("approved_candidate_id")
    return next(
        (
            candidate
            for candidate in mapping_records(variations, "candidates")
            if candidate.get("candidate_id") == approved_id
        ),
        None,
    )


def validate_truth_basis(
    production_config: Mapping[str, object],
    contract: Mapping[str, object],
    facts: Mapping[str, object],
) -> list[ValidationIssue]:
    """실화 사건의 범행·피해·동기 정보가 Evidence Lock을 우회하지 않는지 검사한다."""
    source_truth = production_config.get("source_truth_classification")
    truth_basis = contract.get("truth_basis")
    if not isinstance(truth_basis, Mapping):
        return [
            crime_issue(
                "CRIME_TRUTH_BASIS_MISSING",
                "사건 계약에 Source Truth 근거가 필요합니다.",
                "01_CASE/crime_event_contract.json",
                {},
            )
        ]
    issues: list[ValidationIssue] = []
    if truth_basis.get("source_truth_classification") != source_truth:
        issues.append(
            crime_issue(
                "CRIME_TRUTH_CLASSIFICATION_MISMATCH",
                "사건 계약의 Source Truth 분류가 Project와 다릅니다.",
                "01_CASE/crime_event_contract.json",
                {
                    "expected": source_truth,
                    "actual": truth_basis.get("source_truth_classification"),
                },
            )
        )
    fact_records = mapping_records(facts, "facts")
    factual_ids = {
        fact.get("fact_id")
        for fact in fact_records
        if fact.get("classification") == "FACT" and isinstance(fact.get("fact_id"), str)
    }
    source_fact_ids = set(string_values(truth_basis, "source_fact_ids"))
    if source_truth == "ORIGINAL_FICTION":
        if truth_basis.get("status") != "ORIGINAL_FICTION" or source_fact_ids:
            issues.append(
                crime_issue(
                    "FICTION_CRIME_TRUTH_BASIS_INVALID",
                    "창작 사건은 실화 Evidence Lock을 주장할 수 없습니다.",
                    "01_CASE/crime_event_contract.json",
                    {"status": truth_basis.get("status")},
                )
            )
        return issues
    if (
        truth_basis.get("status") != "EVIDENCE_LOCKED"
        or not source_fact_ids
        or not source_fact_ids.issubset(factual_ids)
    ):
        issues.append(
            crime_issue(
                "TRUE_CRIME_EVENT_NOT_EVIDENCE_LOCKED",
                "실화 사건의 범행·피해·동기 계약은 검증된 FACT 범위에 결속되어야 합니다.",
                "01_CASE/crime_event_contract.json",
                {
                    "status": truth_basis.get("status"),
                    "source_fact_ids": sorted(source_fact_ids),
                    "verified_fact_ids": sorted(cast(set[str], factual_ids)),
                },
            )
        )
    return issues


def validate_crime_event_contract(
    channel: Mapping[str, object],
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    contract: Mapping[str, object],
    facts: Mapping[str, object],
) -> list[ValidationIssue]:
    """승인 Candidate와 Case 사건 계약의 중심 범죄·Truth Lock을 검증한다."""
    policy = explicit_crime_policy(channel)
    if policy is None:
        return []
    candidate = approved_candidate(variations)
    event = candidate.get("crime_event") if isinstance(candidate, Mapping) else None
    if not isinstance(candidate, Mapping) or not isinstance(event, Mapping):
        return [
            crime_issue(
                "APPROVED_CRIME_EVENT_MISSING",
                "승인 Candidate의 사건 개요를 찾을 수 없습니다.",
                "01_CASE/crime_event_contract.json",
                {},
            )
        ]
    issues = event_semantic_shape_issues(
        policy,
        contract,
        "01_CASE/crime_event_contract.json",
    )
    bound_fields = (
        "event_id",
        "primary_crime",
        "related_crimes",
        "core_action_type",
        "relationship_context",
        "actor_ids",
        "victim_ids",
        "motive",
        "act_summary",
        "harm_ids",
        "harm_result",
        "harm_classifications",
        "protagonist_goal",
        "protagonist_risk",
        "depiction_mode",
        "development_functions",
        "reveal_targets",
        "method_detail_level",
    )
    mismatches = {
        field: {"expected": event.get(field), "actual": contract.get(field)}
        for field in bound_fields
        if contract.get(field) != event.get(field)
    }
    expected_id = candidate.get("candidate_id")
    if (
        contract.get("approved_candidate_id") != expected_id
        or contract.get("candidate_event_sha256") != canonical_json_hash(event)
        or mismatches
    ):
        issues.append(
            crime_issue(
                "CRIME_EVENT_CONTRACT_PROJECTION_MISMATCH",
                "Case 사건 계약이 승인 Candidate의 인과 사건 개요와 다릅니다.",
                "01_CASE/crime_event_contract.json",
                {
                    "expected_candidate_id": expected_id,
                    "actual_candidate_id": contract.get("approved_candidate_id"),
                    "mismatches": mismatches,
                },
            )
        )
    issues.extend(validate_truth_basis(production_config, contract, facts))
    return issues


def crime_scene_records(
    scene_cards: Mapping[str, object],
) -> list[tuple[Mapping[str, object], Mapping[str, object]]]:
    """Scene과 그 안의 범죄 실현 기록을 평탄화한다."""
    return [
        (scene, realization)
        for scene in mapping_records(scene_cards, "scenes")
        for realization in mapping_records(scene, "crime_realization")
    ]


def validate_scene_crime_realization(
    channel: Mapping[str, object],
    contract: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
) -> list[ValidationIssue]:
    """Scene Card가 사건·피해·행동·변화와 예정 Segment를 실제로 연결하는지 검사한다."""
    if explicit_crime_policy(channel) is None:
        return []
    event_id = contract.get("event_id")
    harm_ids = set(string_values(contract, "harm_ids"))
    actor_ids = set(string_values(contract, "actor_ids"))
    victim_ids = set(string_values(contract, "victim_ids"))
    records = [
        (scene, realization)
        for scene, realization in crime_scene_records(scene_cards)
        if realization.get("event_id") == event_id
    ]
    issues: list[ValidationIssue] = []
    if not records:
        return [
            crime_issue(
                "SCENE_CRIME_EVENT_UNREALIZED",
                "Scene ID만으로는 충분하지 않으며 중심 범죄 행동 실현 기록이 필요합니다.",
                "06_SCENE/scene_cards.json",
                {"event_id": event_id},
            )
        ]
    planned_segments = {
        cast(str, segment.get("segment_id")): segment
        for segment in presentation_segments(presentation_plan)
        if isinstance(segment.get("segment_id"), str)
    }
    for scene, realization in records:
        scene_id = scene.get("scene_id")
        realization_harms = set(string_values(realization, "harm_ids"))
        realization_actors = set(string_values(realization, "actor_ids"))
        realization_victims = set(string_values(realization, "victim_ids"))
        empty_fields = [
            field
            for field in (
                "action_evidence",
                "dialogue_or_behavior_evidence",
                "choice_or_emotion_change",
                "result_change",
                "expected_excerpt_anchor",
            )
            if not isinstance(realization.get(field), str)
            or not cast(str, realization.get(field)).strip()
        ]
        segment_ids = string_values(realization, "planned_segment_ids")
        invalid_segments = [
            segment_id
            for segment_id in segment_ids
            if segment_id not in planned_segments
            or planned_segments[segment_id].get("scene_id") != scene_id
            or canonical_mode(planned_segments[segment_id].get("segment_type")) != "DRAMA"
        ]
        if (
            not harm_ids.intersection(realization_harms)
            or not realization_actors.issubset(actor_ids)
            or not realization_victims.issubset(victim_ids)
            or not realization_actors
            or not realization_victims
            or empty_fields
            or not segment_ids
            or invalid_segments
        ):
            issues.append(
                crime_issue(
                    "SCENE_CRIME_ACTION_EVIDENCE_INVALID",
                    "범죄 Scene은 사건·피해·행위자·피해자·행동·변화와 "
                    "Drama Segment를 모두 연결해야 합니다.",
                    "06_SCENE/scene_cards.json",
                    {
                        "scene_id": scene_id,
                        "event_id": event_id,
                        "empty_fields": empty_fields,
                        "invalid_segment_ids": invalid_segments,
                    },
                )
            )
    return issues


def script_segments_by_id(final_script: str) -> dict[str, Mapping[str, object]]:
    """정상 Final Script Segment를 ID로 색인한다."""
    parsed, malformed = parse_script_segments(final_script)
    if malformed:
        return {}
    return {segment["segment_id"]: segment for segment in parsed}


def segment_has_crime_action(
    segment: Mapping[str, object],
    contract: Mapping[str, object],
) -> bool:
    """Segment 본문이 사건·행위·피해·인과 Marker를 함께 보존하는지 판정한다."""
    body = segment.get("body")
    event_id = contract.get("event_id")
    action_type = contract.get("core_action_type")
    harm_ids = set(string_values(contract, "harm_ids"))
    if not isinstance(body, str) or not isinstance(event_id, str):
        return False
    tagged_events = set(CRIME_EVENT_TAG.findall(body))
    tagged_actions = set(CRIME_ACTION_TAG.findall(body))
    tagged_harms = set(HARM_TAG.findall(body))
    causal_pairs = set(CAUSE_TAG.findall(body))
    return (
        event_id in tagged_events
        and action_type in tagged_actions
        and bool(harm_ids.intersection(tagged_harms))
        and any(
            causal_event == event_id and causal_harm in harm_ids
            for causal_event, causal_harm in causal_pairs
        )
    )


def crime_script_bindings(
    contract: Mapping[str, object],
    scene_cards: Mapping[str, object],
    final_script: str,
) -> list[dict[str, object]]:
    """Scene 계획을 실제 Final Script의 범죄 행동 Segment와 결합한다."""
    segments = script_segments_by_id(final_script)
    bindings: list[dict[str, object]] = []
    for scene, realization in crime_scene_records(scene_cards):
        if realization.get("event_id") != contract.get("event_id"):
            continue
        for segment_id in string_values(realization, "planned_segment_ids"):
            segment = segments.get(segment_id)
            if (
                segment is None
                or segment.get("scene_id") != scene.get("scene_id")
                or canonical_mode(segment.get("segment_type")) != "DRAMA"
                or not segment_has_crime_action(segment, contract)
            ):
                continue
            bindings.append(
                {
                    "scene_id": scene.get("scene_id"),
                    "segment_id": segment_id,
                    "excerpt_hash": canonical_json_hash(segment),
                    "realization_mode": realization.get("realization_mode"),
                }
            )
    return bindings


def reveal_timing_issues(
    contract: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
) -> list[ValidationIssue]:
    """모든 Layer에서 범인·동기·방식·피해 결과의 조기 누설을 검사한다."""
    segments = presentation_segments(presentation_plan)
    segment_order = {
        segment.get("segment_id"): index
        for index, segment in enumerate(segments)
        if isinstance(segment.get("segment_id"), str)
    }
    planned_targets = {
        cast(str, target.get("reveal_target_id")): target
        for target in mapping_records(contract, "reveal_targets")
        if isinstance(target.get("reveal_target_id"), str)
    }
    viewer_prereveals = {
        (
            reveal.get("reveal_target_id"),
            reveal.get("scene_id"),
        )
        for reveal in mapping_records(viewer_timeline, "reveals")
        if reveal.get("intentional_prereveal") is True
    }
    issues: list[ValidationIssue] = []
    for target_id, target in planned_targets.items():
        revealed_positions = [
            index
            for index, segment in enumerate(segments)
            if target_id in string_values(segment, "revealed_reveal_target_ids")
        ]
        if len(revealed_positions) != 1:
            issues.append(
                crime_issue(
                    "CRIME_REVEAL_PLACEMENT_INVALID",
                    "각 Reveal Target은 Presentation에서 정확히 한 번 공개되어야 합니다.",
                    "06_SCENE/presentation_plan.json",
                    {"reveal_target_id": target_id, "positions": revealed_positions},
                )
            )
            continue
        reveal_position = revealed_positions[0]
        planned_segment_id = target.get("planned_segment_id")
        planned_phase = target.get("planned_phase")
        if isinstance(planned_segment_id, str):
            expected_position = segment_order.get(planned_segment_id)
            placement_valid = expected_position == reveal_position
        elif planned_phase == "LATE":
            placement_valid = reveal_position >= max(0, (len(segments) * 2) // 3)
        elif planned_phase == "MIDDLE":
            placement_valid = len(segments) // 3 <= reveal_position < (len(segments) * 2) // 3
        else:
            placement_valid = reveal_position < max(1, len(segments) // 3)
        if not placement_valid:
            issues.append(
                crime_issue(
                    "CRIME_REVEAL_PHASE_MISMATCH",
                    "Reveal Target이 Viewer Plan의 예정 시점과 다르게 공개되었습니다.",
                    "06_SCENE/presentation_plan.json",
                    {
                        "reveal_target_id": target_id,
                        "planned_phase": planned_phase,
                        "planned_segment_id": planned_segment_id,
                        "actual_position": reveal_position,
                    },
                )
            )
        for index, segment in enumerate(segments[:reveal_position]):
            referenced = target_id in string_values(
                segment,
                "referenced_reveal_target_ids",
            )
            revealed_early = target_id in string_values(
                segment,
                "revealed_reveal_target_ids",
            )
            if not referenced and not revealed_early:
                continue
            intentional = target_id in string_values(segment, "intentional_prereveal_ids")
            viewer_recorded = (
                target_id,
                segment.get("scene_id"),
            ) in viewer_prereveals
            if intentional and viewer_recorded:
                continue
            issues.append(
                crime_issue(
                    "PREMATURE_CRIME_ANSWER_REVEAL",
                    "예정 시점 이전의 범인·결백·동기·방식·피해 결과 언급은 "
                    "Viewer Plan 근거가 필요합니다.",
                    "06_SCENE/presentation_plan.json",
                    {
                        "reveal_target_id": target_id,
                        "segment_id": segment.get("segment_id"),
                        "segment_type": segment.get("segment_type"),
                        "position": index,
                    },
                )
            )
    return issues


def layer_function_issues(
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
) -> list[ValidationIssue]:
    """Narration과 Panel의 기능 Metadata가 각 Layer 경계를 지키는지 검사한다."""
    narration = [
        segment
        for segment in presentation_segments(presentation_plan)
        if canonical_mode(segment.get("segment_type")) == "NARRATION"
    ]
    narration_invalid = [
        segment.get("segment_id")
        for segment in narration
        if segment.get("narration_function") in FORBIDDEN_NARRATION_FUNCTIONS
        or segment.get("narration_function") not in SUBJECTIVE_NARRATION_FUNCTIONS
        or not isinstance(segment.get("narrator_character_id"), str)
    ]
    turns = [
        turn
        for reaction in mapping_records(reaction_segments, "reaction_segments")
        for turn in mapping_records(reaction, "turns")
    ]
    functions = {turn.get("function") for turn in turns if isinstance(turn.get("function"), str)}
    issues: list[ValidationIssue] = []
    if not narration or narration_invalid:
        issues.append(
            crime_issue(
                "NARRATION_SUBJECTIVE_FUNCTION_INVALID",
                "Narration은 사건 내부 인물의 감정·오해·기억 기능과 화자 ID를 가져야 합니다.",
                "06_SCENE/presentation_plan.json",
                {"invalid_segment_ids": narration_invalid},
            )
        )
    if "EMOTIONAL_REACTION" not in functions or not functions.intersection(PANEL_PURSUIT_FUNCTIONS):
        issues.append(
            crime_issue(
                "PANEL_CRIME_PURSUIT_FUNCTION_MISSING",
                "Panel은 감정 반응과 수상 행동·용의자 추적·의견 수정 중 "
                "하나를 함께 수행해야 합니다.",
                "06_SCENE/reaction_segments.json",
                {"functions": sorted(cast(set[str], functions))},
            )
        )
    return issues


def validate_script_crime_realization(
    channel: Mapping[str, object],
    contract: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    final_script: str,
) -> list[ValidationIssue]:
    """실제 Final Script의 사건 행동, Layer 기능과 Reveal 시점을 결정론적으로 검사한다."""
    if explicit_crime_policy(channel) is None:
        return []
    issues = [
        *validate_scene_crime_realization(
            channel,
            contract,
            scene_cards,
            presentation_plan,
        ),
        *reveal_timing_issues(contract, presentation_plan, viewer_timeline),
        *layer_function_issues(presentation_plan, reaction_segments),
    ]
    bindings = crime_script_bindings(contract, scene_cards, final_script)
    if not bindings:
        issues.append(
            crime_issue(
                "SCRIPT_CRIME_ACTION_UNREALIZED",
                "Scene ID나 범죄 장르 태그만으로는 충분하지 않으며 실제 "
                "Drama Segment에 사건·행위·피해 인과가 필요합니다.",
                "07_SCRIPT/final_script.md",
                {"event_id": contract.get("event_id")},
            )
        )
    return issues


def build_crime_script_realization_report(
    project_id: str,
    channel: Mapping[str, object],
    contract: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    final_script: str,
) -> dict[str, object]:
    """CORE 근거와 의미 Critic 대기 상태를 분리한 Script 실현 보고서를 만든다."""
    if explicit_crime_policy(channel) is None:
        return {
            "schema_family": "script-realization-report",
            "schema_version": "2.0.0",
            "project_id": project_id,
            "applicable": False,
            "result": "NOT_APPLICABLE",
            "event_results": [],
            "reveal_results": [],
            "layer_results": [],
            "issues": [],
        }
    issues = validate_script_crime_realization(
        channel,
        contract,
        scene_cards,
        presentation_plan,
        reaction_segments,
        viewer_timeline,
        final_script,
    )
    bindings = crime_script_bindings(contract, scene_cards, final_script)
    first_binding = bindings[0] if bindings else {}
    event_status = "NEEDS_REVIEW" if bindings else "MISSING"
    event_results = [
        {
            "event_id": contract.get("event_id"),
            "harm_ids": string_values(contract, "harm_ids"),
            "status": event_status,
            "scene_id": first_binding.get("scene_id"),
            "segment_id": first_binding.get("segment_id"),
            "selector_type": "SEGMENT_ID",
            "excerpt_hash": first_binding.get("excerpt_hash"),
            "realization_mode": first_binding.get("realization_mode"),
        }
    ]
    segments = presentation_segments(presentation_plan)
    parsed_segments = script_segments_by_id(final_script)
    reveal_issues = reveal_timing_issues(contract, presentation_plan, viewer_timeline)
    reveal_issue_ids = {
        target_id
        for issue in reveal_issues
        for target_id in [issue["context"].get("reveal_target_id")]
        if isinstance(target_id, str)
    }
    reveal_results: list[dict[str, object]] = []
    for target in mapping_records(contract, "reveal_targets"):
        target_id = target.get("reveal_target_id")
        reveal_segment = next(
            (
                segment
                for segment in segments
                if isinstance(target_id, str)
                and target_id in string_values(segment, "revealed_reveal_target_ids")
            ),
            None,
        )
        segment_id = reveal_segment.get("segment_id") if reveal_segment is not None else None
        excerpt = parsed_segments.get(segment_id) if isinstance(segment_id, str) else None
        reveal_results.append(
            {
                "reveal_target_id": target_id,
                "target_type": target.get("target_type"),
                "status": (
                    "NEEDS_REVIEW"
                    if reveal_segment is not None and target_id not in reveal_issue_ids
                    else "MISSING"
                ),
                "segment_id": segment_id,
                "selector_type": "SEGMENT_ID",
                "excerpt_hash": canonical_json_hash(excerpt) if excerpt is not None else None,
            }
        )
    layer_results = []
    for layer in ("DRAMA", "NARRATION", "PANEL_REACTION"):
        layer_segments = [
            segment for segment in segments if canonical_mode(segment.get("segment_type")) == layer
        ]
        layer_results.append(
            {
                "layer": layer,
                "status": "NEEDS_REVIEW" if layer_segments else "MISSING",
                "segment_ids": [
                    segment.get("segment_id")
                    for segment in layer_segments
                    if isinstance(segment.get("segment_id"), str)
                ],
            }
        )
    return {
        "schema_family": "script-realization-report",
        "schema_version": "2.0.0",
        "project_id": project_id,
        "applicable": True,
        "input_hashes": {
            "crime_event_contract": canonical_json_hash(contract),
            "scene_cards": canonical_json_hash(scene_cards),
            "presentation_plan": canonical_json_hash(presentation_plan),
            "reaction_segments": canonical_json_hash(reaction_segments),
            "viewer_timeline": canonical_json_hash(viewer_timeline),
            "final_script": sha256(final_script.encode("utf-8")).hexdigest(),
        },
        "result": "MISSING" if issues else "NEEDS_REVIEW",
        "event_results": event_results,
        "reveal_results": reveal_results,
        "layer_results": layer_results,
        "issues": issues,
    }


def validate_crime_script_realization_report(
    channel: Mapping[str, object],
    project_id: str,
    contract: Mapping[str, object],
    scene_cards: Mapping[str, object],
    presentation_plan: Mapping[str, object],
    reaction_segments: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
    final_script: str,
    report: Mapping[str, object],
) -> list[ValidationIssue]:
    """CORE Report를 재계산하되 의미 충족으로 승격하지 않는다."""
    if explicit_crime_policy(channel) is None:
        return []
    expected = build_crime_script_realization_report(
        project_id,
        channel,
        contract,
        scene_cards,
        presentation_plan,
        reaction_segments,
        viewer_timeline,
        final_script,
    )
    if dict(report) != expected:
        return [
            crime_issue(
                "CRIME_SCRIPT_REALIZATION_REPORT_STALE",
                "Script Realization Report가 현재 사건·Scene·Final Script "
                "근거와 일치하지 않습니다.",
                "08_QA/script_realization_report.json",
                {
                    "expected_input_hashes": expected.get("input_hashes"),
                    "actual_input_hashes": report.get("input_hashes"),
                },
            )
        ]
    if expected.get("result") == "MISSING":
        raw_issues = expected.get("issues")
        return list(raw_issues) if isinstance(raw_issues, list) else []
    if any(
        result.get("status") != "NEEDS_REVIEW"
        for field in ("event_results", "reveal_results", "layer_results")
        for result in mapping_records(expected, field)
    ):
        return [
            crime_issue(
                "CRIME_SCRIPT_EVIDENCE_MISSING",
                "의미 검토 전에 필요한 Script 근거가 누락되었습니다.",
                "08_QA/script_realization_report.json",
                {},
            )
        ]
    return []


def crime_channel_evidence(report: Mapping[str, object]) -> list[dict[str, object]]:
    """Channel QA에 보존할 사건·Reveal CORE 근거를 반환한다."""
    evidence: list[dict[str, object]] = []
    for result in mapping_records(report, "event_results"):
        evidence.append(
            {
                "target_type": "EVENT",
                "target_id": result.get("event_id"),
                "status": result.get("status"),
                "scene_id": result.get("scene_id"),
                "segment_id": result.get("segment_id"),
                "excerpt_hash": result.get("excerpt_hash"),
            }
        )
    for result in mapping_records(report, "reveal_results"):
        evidence.append(
            {
                "target_type": "REVEAL",
                "target_id": result.get("reveal_target_id"),
                "status": result.get("status"),
                "scene_id": None,
                "segment_id": result.get("segment_id"),
                "excerpt_hash": result.get("excerpt_hash"),
            }
        )
    return evidence


def validate_channel_crime_evidence(
    channel: Mapping[str, object],
    report: Mapping[str, object],
    channel_report: Mapping[str, object],
) -> list[ValidationIssue]:
    """GATE-12 Channel Report가 CORE 사건 근거를 그대로 보존하는지 검사한다."""
    if explicit_crime_policy(channel) is None:
        return []
    expected = crime_channel_evidence(report)
    actual = channel_report.get("crime_realization_evidence")
    if actual == expected and expected:
        return []
    return [
        crime_issue(
            "CHANNEL_CRIME_REALIZATION_EVIDENCE_MISSING",
            "Channel Consistency Report에 사건·Reveal Script 근거가 없습니다.",
            "08_QA/channel_consistency_report.json",
            {"expected": expected, "actual": actual},
        )
    ]


def required_semantic_subjects(
    contract: Mapping[str, object],
) -> set[tuple[str, str]]:
    """Editorial Critic이 실제 발췌로 판단해야 할 대상 집합을 반환한다."""
    subjects = {
        ("CRIME_EVENT_REALIZATION", cast(str, contract.get("event_id"))),
        ("NARRATION_FUNCTION", "NARRATION"),
        ("PANEL_FUNCTION", "PANEL_REACTION"),
        ("CLUE_AND_EVIDENCE_COHERENCE", "FINAL_REVEAL_EVIDENCE"),
    }
    subjects.update(
        ("REVEAL_TIMING", cast(str, target.get("reveal_target_id")))
        for target in mapping_records(contract, "reveal_targets")
        if isinstance(target.get("reveal_target_id"), str)
    )
    return subjects

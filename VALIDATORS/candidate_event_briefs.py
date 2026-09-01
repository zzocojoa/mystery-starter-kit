"""2.1 Candidate 사건 Brief와 최종 역할 결속 계약을 검증한다."""

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha256

from VALIDATORS.crime_functions import development_function_issues
from VALIDATORS.models import ValidationIssue

PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"CHAR-[0-9]+의\s+[A-Z_]+\s+행위", re.IGNORECASE),
    re.compile(r"HARM-[0-9]+의\s+피해\s*결과", re.IGNORECASE),
    re.compile(r"\bCHAR-[0-9]+\b", re.IGNORECASE),
    re.compile(r"\bHARM-[0-9]+\b", re.IGNORECASE),
    re.compile(r"^책임\s*행위자\s*공개$"),
    re.compile(r"^범행\s*방식\s*공개$"),
    re.compile(r"^피해\s*결과\s*공개$"),
    re.compile(r"UNKNOWN_UNLESS_EVIDENCED", re.IGNORECASE),
)
CAUSAL_FIELDS: tuple[str, ...] = (
    "target_selection_reason",
    "trigger_event",
    "non_actionable_method_summary",
    "immediate_harm",
    "lasting_harm",
    "concealment_or_denial",
    "discovery_path",
    "responsibility_path",
)
FIELD_EVIDENCE_KEYS: tuple[str, ...] = (
    "PRIMARY_CRIME",
    "CULPRIT",
    "MOTIVE",
    "METHOD",
    "HARM_RESULT",
    "LEGAL_OUTCOME",
)
OFFENDER_COUNTS: Mapping[str, int] = {
    "SINGLE_AGENT": 1,
    "DUAL_AGENTS": 2,
    "COMPLICIT_GROUP": 3,
}
VICTIM_COUNTS: Mapping[str, int] = {
    "SINGLE_VICTIM": 1,
    "MULTIPLE_VICTIMS": 2,
}


def canonical_json_hash(value: object) -> str:
    """JSON 값의 정규 SHA-256을 반환한다."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def candidate_event_brief_hashes(
    document: Mapping[str, object],
) -> dict[str, str]:
    """Candidate ID별 Event Brief 정규 Hash를 반환한다."""
    return {
        str(brief["candidate_id"]): canonical_json_hash(brief)
        for brief in mapping_records(document, "briefs")
        if isinstance(brief.get("candidate_id"), str)
    }


def brief_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Candidate Event Brief 문제를 표준 Issue로 만든다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def mapping_records(document: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    """객체 배열만 반환한다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def string_values(document: Mapping[str, object], field: str) -> list[str]:
    """문자열 배열만 반환한다."""
    value = document.get(field)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def candidate_by_id(
    variations: Mapping[str, object],
    candidate_id: object,
) -> Mapping[str, object] | None:
    """Candidate ID와 일치하는 구조 후보를 반환한다."""
    return next(
        (
            candidate
            for candidate in mapping_records(variations, "candidates")
            if candidate.get("candidate_id") == candidate_id
        ),
        None,
    )


def cardinality_issues(brief: Mapping[str, object]) -> list[ValidationIssue]:
    """가해자·피해자 Role Slot 수를 SSOT 구조와 비교한다."""
    offender_slots = string_values(brief, "offender_role_slots")
    victim_slots = string_values(brief, "victim_role_slots")
    offender_structure = brief.get("responsible_agent_structure")
    victim_structure = brief.get("victim_structure")
    issues: list[ValidationIssue] = []
    expected_offenders = OFFENDER_COUNTS.get(str(offender_structure))
    offender_valid = (
        len(offender_slots) >= expected_offenders
        if offender_structure == "COMPLICIT_GROUP" and expected_offenders is not None
        else len(offender_slots) == expected_offenders
    ) and all(slot.startswith("OFFENDER-") for slot in offender_slots)
    if not offender_valid:
        issues.append(
            brief_issue(
                "OFFENDER_CARDINALITY_MISMATCH",
                "가해자 Role Slot 수가 responsible_agent_structure와 다릅니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {
                    "candidate_id": brief.get("candidate_id"),
                    "structure": offender_structure,
                    "actual_count": len(offender_slots),
                    "required_count": expected_offenders,
                },
            )
        )
    expected_victims = VICTIM_COUNTS.get(str(victim_structure))
    victim_valid = (
        len(victim_slots) >= expected_victims
        if victim_structure == "MULTIPLE_VICTIMS" and expected_victims is not None
        else len(victim_slots) == expected_victims
    ) and all(slot.startswith("VICTIM-") for slot in victim_slots)
    if not victim_valid:
        issues.append(
            brief_issue(
                "VICTIM_CARDINALITY_MISMATCH",
                "피해자 Role Slot 수가 victim_structure와 다릅니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {
                    "candidate_id": brief.get("candidate_id"),
                    "structure": victim_structure,
                    "actual_count": len(victim_slots),
                    "required_count": expected_victims,
                },
            )
        )
    return issues


def placeholder_issues(brief: Mapping[str, object]) -> list[ValidationIssue]:
    """사건별 의미를 제공하지 않는 임시 문구를 차단한다."""
    issues: list[ValidationIssue] = []
    text_fields = (
        *CAUSAL_FIELDS,
        "initiating_context",
        "motive_summary",
        "central_pursuit_question",
    )
    for field in text_fields:
        value = brief.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                brief_issue(
                    "CANDIDATE_EVENT_FIELD_EMPTY",
                    "Candidate Event Brief의 구체 사건 필드는 공백일 수 없습니다.",
                    "00_PROJECT/candidate_event_briefs.json",
                    {"candidate_id": brief.get("candidate_id"), "field": field},
                )
            )
            continue
        if any(pattern.search(value.strip()) for pattern in PLACEHOLDER_PATTERNS):
            issues.append(
                brief_issue(
                    "CANDIDATE_EVENT_PLACEHOLDER_FORBIDDEN",
                    "Candidate Event Brief에 임시 사건 문구를 사용할 수 없습니다.",
                    "00_PROJECT/candidate_event_briefs.json",
                    {"candidate_id": brief.get("candidate_id"), "field": field},
                )
            )
    for reveal in mapping_records(brief, "reveal_targets"):
        summary = reveal.get("summary")
        if isinstance(summary, str) and any(
            pattern.search(summary.strip()) for pattern in PLACEHOLDER_PATTERNS
        ):
            issues.append(
                brief_issue(
                    "CANDIDATE_EVENT_PLACEHOLDER_FORBIDDEN",
                    "Reveal Target은 사건별로 구체적인 공개 내용을 가져야 합니다.",
                    "00_PROJECT/candidate_event_briefs.json",
                    {
                        "candidate_id": brief.get("candidate_id"),
                        "reveal_target_id": reveal.get("reveal_target_id"),
                    },
                )
            )
    return issues


def normalized_causal_text(brief: Mapping[str, object]) -> str:
    """ID·숫자 차이를 제거한 인과 사건 비교 문자열을 만든다."""
    values = [str(brief.get(field, "")) for field in CAUSAL_FIELDS]
    normalized = " | ".join(values).casefold()
    normalized = re.sub(r"(?:char|harm|offender|victim|var)-?\d+", "<role>", normalized)
    normalized = re.sub(r"\d+", "<n>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def causal_collision_issues(briefs: list[Mapping[str, object]]) -> list[ValidationIssue]:
    """이름·장소만 바꾼 동일 인과 사건 Brief 쌍을 차단한다."""
    issues: list[ValidationIssue] = []
    for index, left in enumerate(briefs):
        left_text = normalized_causal_text(left)
        for right in briefs[index + 1 :]:
            right_text = normalized_causal_text(right)
            similarity = SequenceMatcher(None, left_text, right_text, autojunk=False).ratio()
            if similarity >= 0.88:
                issues.append(
                    brief_issue(
                        "CANDIDATE_EVENT_CAUSAL_COLLISION",
                        "Candidate Event Brief가 장소나 이름만 다른 동일 인과 사건입니다.",
                        "00_PROJECT/candidate_event_briefs.json",
                        {
                            "candidate_ids": [left.get("candidate_id"), right.get("candidate_id")],
                            "similarity": round(similarity, 4),
                        },
                    )
                )
    return issues


def fiction_resolution_issues(brief: Mapping[str, object]) -> list[ValidationIssue]:
    """Original Fiction의 동기·방식·피해·해결 경로를 UNKNOWN으로 남기지 못하게 한다."""
    truth_basis = brief.get("truth_basis")
    if (
        not isinstance(truth_basis, Mapping)
        or truth_basis.get("source_truth_classification") != "ORIGINAL_FICTION"
    ):
        return []
    checks = (
        ("motive_summary", "FICTION_MOTIVE_UNRESOLVED"),
        ("non_actionable_method_summary", "FICTION_METHOD_UNRESOLVED"),
        ("immediate_harm", "FICTION_HARM_RESULT_UNRESOLVED"),
        ("lasting_harm", "FICTION_HARM_RESULT_UNRESOLVED"),
        ("discovery_path", "FICTION_DISCOVERY_PATH_UNRESOLVED"),
        ("responsibility_path", "FICTION_RESPONSIBILITY_PATH_UNRESOLVED"),
    )
    issues: list[ValidationIssue] = []
    if brief.get("motive_category") == "UNKNOWN_UNLESS_EVIDENCED":
        issues.append(
            brief_issue(
                "FICTION_MOTIVE_UNRESOLVED",
                "Original Fiction의 동기 Category는 구체적으로 확정해야 합니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {"candidate_id": brief.get("candidate_id")},
            )
        )
    for field, code in checks:
        value = brief.get(field)
        if not isinstance(value, str) or "UNKNOWN" in value.upper():
            issues.append(
                brief_issue(
                    code,
                    "Original Fiction의 사건 결과를 UNKNOWN으로 남길 수 없습니다.",
                    "00_PROJECT/candidate_event_briefs.json",
                    {"candidate_id": brief.get("candidate_id"), "field": field},
                )
            )
    return issues


def validate_candidate_event_briefs(
    variations: Mapping[str, object],
    document: Mapping[str, object],
    explicit_crime_policy: Mapping[str, object] | None,
) -> list[ValidationIssue]:
    """구조 후보와 Event Brief의 전단사·Hash·구체성·Cardinality를 검증한다."""
    candidates = mapping_records(variations, "candidates")
    briefs = mapping_records(document, "briefs")
    candidate_ids = [candidate.get("candidate_id") for candidate in candidates]
    brief_ids = [brief.get("candidate_id") for brief in briefs]
    issues: list[ValidationIssue] = []
    if len(briefs) != len(candidates) or sorted(str(value) for value in brief_ids) != sorted(
        str(value) for value in candidate_ids
    ):
        issues.append(
            brief_issue(
                "CANDIDATE_EVENT_BRIEF_COVERAGE_MISMATCH",
                "모든 Candidate는 정확히 하나의 Event Brief와 대응해야 합니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {"candidate_ids": candidate_ids, "brief_candidate_ids": brief_ids},
            )
        )
    duplicate_ids = sorted({str(value) for value in brief_ids if brief_ids.count(value) > 1})
    if duplicate_ids:
        issues.append(
            brief_issue(
                "CANDIDATE_EVENT_BRIEF_ID_DUPLICATED",
                "Candidate Event Brief ID는 중복될 수 없습니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {"candidate_ids": duplicate_ids},
            )
        )
    for brief in briefs:
        candidate = candidate_by_id(variations, brief.get("candidate_id"))
        selection = candidate.get("selection") if candidate is not None else None
        if not isinstance(selection, Mapping) or brief.get(
            "candidate_selection_sha256"
        ) != canonical_json_hash(selection):
            issues.append(
                brief_issue(
                    "CANDIDATE_EVENT_SELECTION_HASH_MISMATCH",
                    "Event Brief가 현재 Candidate Selection Hash와 다릅니다.",
                    "00_PROJECT/candidate_event_briefs.json",
                    {"candidate_id": brief.get("candidate_id")},
                )
            )
        if isinstance(selection, Mapping):
            mismatched = sorted(
                field
                for field in (
                    "primary_crime",
                    "core_action_type",
                    "responsible_agent_structure",
                    "victim_structure",
                    "relationship_context",
                    "motive_category",
                )
                if brief.get(field) != selection.get(field)
            )
            if mismatched:
                issues.append(
                    brief_issue(
                        "CANDIDATE_EVENT_STRUCTURE_MISMATCH",
                        "Event Brief가 Candidate의 잠긴 사건 구조를 변경했습니다.",
                        "00_PROJECT/candidate_event_briefs.json",
                        {"candidate_id": brief.get("candidate_id"), "fields": mismatched},
                    )
                )
        issues.extend(cardinality_issues(brief))
        issues.extend(placeholder_issues(brief))
        issues.extend(fiction_resolution_issues(brief))
        if explicit_crime_policy is not None:
            issues.extend(
                development_function_issues(
                    explicit_crime_policy,
                    brief,
                    "00_PROJECT/candidate_event_briefs.json",
                )
            )
    issues.extend(causal_collision_issues(briefs))
    return issues


def approved_event_brief(
    variations: Mapping[str, object],
    briefs_document: Mapping[str, object],
) -> Mapping[str, object] | None:
    """승인 Candidate와 연결된 Event Brief를 반환한다."""
    approved_id = variations.get("approved_candidate_id")
    return next(
        (
            brief
            for brief in mapping_records(briefs_document, "briefs")
            if brief.get("candidate_id") == approved_id
        ),
        None,
    )


def validate_candidate_event_case_projection(
    variations: Mapping[str, object],
    briefs_document: Mapping[str, object],
    case_input: Mapping[str, object],
    facts: Mapping[str, object],
) -> list[ValidationIssue]:
    """승인 Event Brief의 사건 내용이 GATE-03 Case와 Facts에 유지되는지 검사한다."""
    brief = approved_event_brief(variations, briefs_document)
    if brief is None:
        return []
    expected_case = {
        "primary_crime": brief.get("primary_crime"),
        "motive_summary": brief.get("motive_summary"),
        "crime_method_summary": brief.get("non_actionable_method_summary"),
        "harm_result": f"{brief.get('immediate_harm')} / {brief.get('lasting_harm')}",
        "final_case_truth": brief.get("responsibility_path"),
    }
    mismatches = {
        field: {"expected": expected, "actual": case_input.get(field)}
        for field, expected in expected_case.items()
        if case_input.get(field) != expected
    }
    issues: list[ValidationIssue] = []
    if mismatches:
        issues.append(
            brief_issue(
                "CRIME_CASE_TRACE_MISMATCH",
                "Case Input이 승인 Candidate Event Brief의 핵심 사건을 변경했습니다.",
                "01_CASE/case_input.json",
                {"mismatches": mismatches},
            )
        )
    required_fact_types = {
        "CRIME_ACTION",
        "HARM_RESULT",
        "MOTIVE_STATUS",
        "RESPONSIBILITY",
    }
    actual_fact_types = {
        str(fact.get("crime_fact_type"))
        for fact in mapping_records(facts, "facts")
        if isinstance(fact.get("crime_fact_type"), str)
    }
    actual_fact_types.update(
        fact_type
        for fact in mapping_records(facts, "facts")
        for fact_type in string_values(fact, "crime_fact_types")
    )
    known_fact_ids = {
        str(fact.get("fact_id"))
        for fact in mapping_records(facts, "facts")
        if isinstance(fact.get("fact_id"), str)
    }
    actual_fact_types.update(
        str(trace.get("crime_fact_type"))
        for trace in mapping_records(facts, "crime_fact_trace")
        if isinstance(trace.get("crime_fact_type"), str)
        and bool(string_values(trace, "fact_ids"))
        and set(string_values(trace, "fact_ids")).issubset(known_fact_ids)
    )
    missing_fact_types = sorted(required_fact_types - actual_fact_types)
    if missing_fact_types:
        issues.append(
            brief_issue(
                "CRIME_FACT_TRACE_MISMATCH",
                "Case Facts에 범죄 행위·피해·동기 상태·책임 주체가 모두 필요합니다.",
                "01_CASE/facts.json",
                {"missing_crime_fact_types": missing_fact_types},
            )
        )
    return issues


def role_bindings(
    characters: Mapping[str, object],
    required_slots: set[str],
) -> tuple[list[dict[str, str]], list[ValidationIssue]]:
    """Character가 선언한 Role Slot을 명시적 Binding 목록으로 정규화한다."""
    bindings: list[dict[str, str]] = []
    character_ids: set[str] = set()
    for character in mapping_records(characters, "characters"):
        character_id = character.get("character_id")
        if not isinstance(character_id, str):
            continue
        character_ids.add(character_id)
        for role_slot in string_values(character, "crime_role_slots"):
            if role_slot in required_slots:
                bindings.append(
                    {
                        "role_slot": role_slot,
                        "character_id": character_id,
                        "role_type": role_slot.partition("-")[0],
                    }
                )
    issues: list[ValidationIssue] = []
    bound_slots = [binding["role_slot"] for binding in bindings]
    missing = sorted(required_slots - set(bound_slots))
    if missing:
        issues.append(
            brief_issue(
                "CRIME_ROLE_BINDING_MISSING",
                "필수 Crime Role Slot의 Character Binding이 없습니다.",
                "02_CHARACTER/characters.json",
                {"role_slots": missing},
            )
        )
    duplicated = sorted({slot for slot in bound_slots if bound_slots.count(slot) > 1})
    if duplicated:
        issues.append(
            brief_issue(
                "CRIME_ROLE_BINDING_DUPLICATED",
                "하나의 Crime Role Slot이 여러 Character에 결속됐습니다.",
                "02_CHARACTER/characters.json",
                {"role_slots": duplicated},
            )
        )
    missing_characters = sorted(
        {
            binding["character_id"]
            for binding in bindings
            if binding["character_id"] not in character_ids
        }
    )
    if missing_characters:
        issues.append(
            brief_issue(
                "CRIME_ROLE_CHARACTER_NOT_FOUND",
                "Crime Role Binding의 Character ID가 존재하지 않습니다.",
                "02_CHARACTER/characters.json",
                {"character_ids": missing_characters},
            )
        )
    offender_ids = {
        binding["character_id"] for binding in bindings if binding["role_type"] == "OFFENDER"
    }
    victim_ids = {
        binding["character_id"] for binding in bindings if binding["role_type"] == "VICTIM"
    }
    required_offender_slots = {slot for slot in required_slots if slot.startswith("OFFENDER-")}
    required_victim_slots = {slot for slot in required_slots if slot.startswith("VICTIM-")}
    if len(offender_ids) != len(required_offender_slots):
        issues.append(
            brief_issue(
                "OFFENDER_CARDINALITY_MISMATCH",
                "각 가해자 Role Slot은 서로 다른 Character에 결속해야 합니다.",
                "02_CHARACTER/characters.json",
                {
                    "required_count": len(required_offender_slots),
                    "distinct_character_count": len(offender_ids),
                },
            )
        )
    if len(victim_ids) != len(required_victim_slots):
        issues.append(
            brief_issue(
                "VICTIM_CARDINALITY_MISMATCH",
                "각 피해자 Role Slot은 서로 다른 Character에 결속해야 합니다.",
                "02_CHARACTER/characters.json",
                {
                    "required_count": len(required_victim_slots),
                    "distinct_character_count": len(victim_ids),
                },
            )
        )
    overlap = sorted(offender_ids & victim_ids)
    if overlap:
        issues.append(
            brief_issue(
                "OFFENDER_VICTIM_ROLE_OVERLAP",
                "같은 Character를 가해자와 피해자로 동시에 결속할 수 없습니다.",
                "02_CHARACTER/characters.json",
                {"character_ids": overlap},
            )
        )
    return bindings, issues


def build_bound_crime_event_contract(
    project_id: str,
    variations: Mapping[str, object],
    briefs_document: Mapping[str, object],
    case_input: Mapping[str, object],
    facts: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
    source_truth_contract: Mapping[str, object],
) -> tuple[dict[str, object] | None, list[ValidationIssue]]:
    """승인 Brief를 재창작하지 않고 Role Slot만 Character ID에 결속한다."""
    brief = approved_event_brief(variations, briefs_document)
    candidate = candidate_by_id(variations, variations.get("approved_candidate_id"))
    selection = candidate.get("selection") if candidate is not None else None
    if brief is None or not isinstance(selection, Mapping):
        return None, [
            brief_issue(
                "CANDIDATE_EVENT_BRIEF_APPROVED_MISSING",
                "승인 Candidate의 Event Brief가 없습니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {"approved_candidate_id": variations.get("approved_candidate_id")},
            )
        ]
    projection_issues = validate_candidate_event_case_projection(
        variations,
        briefs_document,
        case_input,
        facts,
    )
    if projection_issues:
        return None, projection_issues
    offender_slots = string_values(brief, "offender_role_slots")
    victim_slots = string_values(brief, "victim_role_slots")
    protagonist_slot = brief.get("protagonist_role_slot")
    required_slots = set(offender_slots) | set(victim_slots)
    if isinstance(protagonist_slot, str):
        required_slots.add(protagonist_slot)
    bindings, issues = role_bindings(characters, required_slots)
    if issues:
        return None, issues
    slot_map = {binding["role_slot"]: binding["character_id"] for binding in bindings}
    actor_ids = [slot_map[slot] for slot in offender_slots]
    victim_ids = [slot_map[slot] for slot in victim_slots]
    protagonist_id = slot_map.get(str(protagonist_slot))
    relationship_pairs = {
        (relationship.get("from"), relationship.get("to"))
        for relationship in mapping_records(relationships, "relationships")
    }
    if not any(
        (actor_id, victim_id) in relationship_pairs or (victim_id, actor_id) in relationship_pairs
        for actor_id in actor_ids
        for victim_id in victim_ids
    ):
        return None, [
            brief_issue(
                "CRIME_CHARACTER_TRACE_MISMATCH",
                "가해자와 피해자의 명시적 Relationship 결속이 없습니다.",
                "02_CHARACTER/relationships.json",
                {"actor_ids": actor_ids, "victim_ids": victim_ids},
            )
        ]
    source_classification = source_truth_contract.get("source_truth_classification")
    truth_basis = brief.get("truth_basis")
    if (
        isinstance(source_classification, str)
        and isinstance(truth_basis, Mapping)
        and truth_basis.get("source_truth_classification") != source_classification
    ):
        return None, [
            brief_issue(
                "CRIME_TRUTH_CLASSIFICATION_MISMATCH",
                "Event Brief의 Source Truth 분류가 Source Truth Contract와 다릅니다.",
                "00_PROJECT/candidate_event_briefs.json",
                {
                    "expected": source_classification,
                    "actual": truth_basis.get("source_truth_classification"),
                },
            )
        ]
    primary = brief.get("primary_crime")
    action = brief.get("core_action_type")
    related = [action] if primary != action else []
    harm_classification = selection.get("harm_classification")
    contract: dict[str, object] = {
        "$schema": "../../../STANDARD/schemas/crime_event_contract.schema.json",
        "schema_family": "crime-event-contract",
        "schema_version": "1.1.0",
        "project_id": project_id,
        "approved_candidate_id": variations.get("approved_candidate_id"),
        "candidate_selection_sha256": canonical_json_hash(selection),
        "candidate_event_brief_sha256": canonical_json_hash(brief),
        "event_id": "EVENT-01",
        "primary_crime": primary,
        "related_crimes": related,
        "core_action_type": action,
        "responsible_agent_structure": brief.get("responsible_agent_structure"),
        "victim_structure": brief.get("victim_structure"),
        "offender_role_slots": offender_slots,
        "victim_role_slots": victim_slots,
        "protagonist_role_slot": protagonist_slot,
        "role_bindings": bindings,
        "actor_ids": actor_ids,
        "victim_ids": victim_ids,
        "protagonist_id": protagonist_id,
        "relationship_context": brief.get("relationship_context"),
        "target_selection_reason": brief.get("target_selection_reason"),
        "initiating_context": brief.get("initiating_context"),
        "trigger_event": brief.get("trigger_event"),
        "motive_category": brief.get("motive_category"),
        "motive_summary": brief.get("motive_summary"),
        "non_actionable_method_summary": brief.get("non_actionable_method_summary"),
        "immediate_harm": brief.get("immediate_harm"),
        "lasting_harm": brief.get("lasting_harm"),
        "concealment_or_denial": brief.get("concealment_or_denial"),
        "discovery_path": brief.get("discovery_path"),
        "responsibility_path": brief.get("responsibility_path"),
        "central_pursuit_question": brief.get("central_pursuit_question"),
        "harm_ids": ["HARM-01"],
        "harm_classifications": [harm_classification],
        "protagonist_goal": selection.get("protagonist_goal"),
        "protagonist_risk": selection.get("protagonist_risk"),
        "depiction_mode": selection.get("depiction_mode"),
        "development_functions": deepcopy(brief.get("development_functions")),
        "reveal_targets": deepcopy(brief.get("reveal_targets")),
        "method_detail_level": "NON_ACTIONABLE_SUMMARY_ONLY",
        "truth_basis": deepcopy(brief.get("truth_basis")),
    }
    return contract, []

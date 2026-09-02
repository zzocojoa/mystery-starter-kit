"""구체적 대인범죄 사건을 Candidate부터 Final Script까지 추적한다."""

import json
import re
from collections.abc import Mapping
from hashlib import sha256
from typing import cast

from VALIDATORS.candidate_event_briefs import (
    FIELD_EVIDENCE_KEYS,
    approved_event_brief,
    cardinality_issues,
)
from VALIDATORS.candidate_event_briefs import (
    canonical_json_hash as candidate_json_hash,
)
from VALIDATORS.crime_functions import (
    development_function_issues,
    required_development_function_map,
)
from VALIDATORS.crime_harms import (
    ACTION_HARM_REQUIREMENTS,
    bind_harm_records,
    structured_harm_issues,
)
from VALIDATORS.crime_harms import (
    mapping_records as harm_records,
)
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
REQUIRED_REVEAL_TYPES = frozenset({"CULPRIT", "MOTIVE", "METHOD", "HARM_RESULT"})
SUBJECTIVE_NARRATION_FUNCTIONS = frozenset(
    {
        "SUBJECTIVE_EXPERIENCE",
        "EMOTIONAL_CONTINUITY",
        "MEMORY",
        "MISUNDERSTANDING",
        "SELF_DOUBT",
        "FEAR",
        "TIME_COMPRESSION",
        "RETROSPECTIVE_REFLECTION",
    }
)
FORBIDDEN_NARRATION_FUNCTIONS = frozenset(
    {
        "CLUE_EXPLANATION",
        "EVIDENCE_WEIGHTING",
        "SOLUTION_EXPOSITION",
        "ANSWER_DIRECTIVE",
        "UNPLANNED_PREMATURE_REVEAL",
    }
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
CRIME_TRACE_BLOCK = re.compile(r"<!--\s*CRIME_TRACE(?P<body>.*?)-->", re.DOTALL)
CRIME_TRACE_FIELD = re.compile(r"(?m)^\s*(EVENT|ACTION|HARM|DEV)\s*=\s*([^\n]+?)\s*$")
SCRIPT_WORD = re.compile(r"[0-9A-Za-z가-힣]+")


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
    issues.extend(development_function_issues(policy, event, artifact))
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
    if candidate.get("variation_engine_version") == "2.1.0" and event is None:
        return []
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
    """핵심 범죄 필드별 Evidence Classification과 Claim 결속을 검사한다."""
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
    field_evidence = truth_basis.get("field_evidence")
    if not isinstance(field_evidence, Mapping):
        source_fact_ids = set(string_values(truth_basis, "source_fact_ids"))
        if "status" in truth_basis:
            factual_ids = {
                fact.get("fact_id")
                for fact in mapping_records(facts, "facts")
                if fact.get("classification") == "FACT" and isinstance(fact.get("fact_id"), str)
            }
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
                truth_basis.get("status") == "EVIDENCE_LOCKED"
                and source_fact_ids
                and source_fact_ids.issubset(factual_ids)
            ):
                return issues
        return [
            *issues,
            crime_issue(
                "CRIME_FIELD_EVIDENCE_MISSING",
                "범인·동기·방식·피해 결과별 Evidence가 필요합니다.",
                "01_CASE/crime_event_contract.json",
                {"missing_fields": list(FIELD_EVIDENCE_KEYS)},
            ),
        ]
    fact_records = {
        cast(str, fact.get("fact_id")): fact
        for fact in mapping_records(facts, "facts")
        if isinstance(fact.get("fact_id"), str)
    }
    for field in FIELD_EVIDENCE_KEYS:
        evidence = field_evidence.get(field)
        if not isinstance(evidence, Mapping):
            issues.append(
                crime_issue(
                    "CRIME_FIELD_EVIDENCE_MISSING",
                    "핵심 범죄 필드의 Evidence 항목이 없습니다.",
                    "01_CASE/crime_event_contract.json",
                    {"field": field},
                )
            )
            continue
        classification = evidence.get("classification")
        claim_ids = set(string_values(evidence, "claim_ids"))
        if source_truth == "ORIGINAL_FICTION":
            if classification != "ORIGINAL_FICTION" or claim_ids:
                issues.append(
                    crime_issue(
                        "FICTION_CRIME_TRUTH_BASIS_INVALID",
                        "Original Fiction은 Source Claim 없이 "
                        "ORIGINAL_FICTION으로 분류해야 합니다.",
                        "01_CASE/crime_event_contract.json",
                        {"field": field, "classification": classification},
                    )
                )
            continue
        if classification == "FACT":
            unsupported = sorted(
                claim_id
                for claim_id in claim_ids
                if fact_records.get(claim_id, {}).get("classification") != "FACT"
            )
            if not claim_ids or unsupported:
                issues.append(
                    crime_issue(
                        "CRIME_FIELD_FACT_UNSUPPORTED",
                        "FACT 분류에는 검증된 FACT Claim이 필요합니다.",
                        "01_CASE/crime_event_contract.json",
                        {
                            "field": field,
                            "claim_ids": sorted(claim_ids),
                            "unsupported": unsupported,
                        },
                    )
                )
        elif classification == "INFERENCE":
            ungrounded = sorted(
                claim_id
                for claim_id in claim_ids
                if not isinstance(fact_records.get(claim_id), Mapping)
                or not string_values(fact_records[claim_id], "basis_fact_ids")
            )
            if not claim_ids or ungrounded:
                issues.append(
                    crime_issue(
                        "CRIME_FIELD_INFERENCE_UNGROUNDED",
                        "INFERENCE 분류에는 Basis FACT가 필요합니다.",
                        "01_CASE/crime_event_contract.json",
                        {"field": field, "claim_ids": sorted(claim_ids), "ungrounded": ungrounded},
                    )
                )
        elif classification == "DRAMATIZATION":
            promoted = sorted(
                claim_id
                for claim_id in claim_ids
                if fact_records.get(claim_id, {}).get("presented_as_fact") is True
            )
            if promoted:
                issues.append(
                    crime_issue(
                        "CRIME_DRAMATIZATION_PRESENTED_AS_FACT",
                        "DRAMATIZATION은 사실처럼 제시할 수 없습니다.",
                        "01_CASE/crime_event_contract.json",
                        {"field": field, "claim_ids": promoted},
                    )
                )
        elif classification == "UNKNOWN":
            if claim_ids:
                issues.append(
                    crime_issue(
                        "CRIME_UNKNOWN_PROMOTED_TO_FACT",
                        "UNKNOWN 필드에 근거 Claim을 붙여 확정 사실처럼 승격할 수 없습니다.",
                        "01_CASE/crime_event_contract.json",
                        {"field": field, "claim_ids": sorted(claim_ids)},
                    )
                )
            if field == "MOTIVE":
                motive_summary = contract.get("motive_summary")
                honest_unknown = isinstance(motive_summary, str) and any(
                    token in motive_summary for token in ("확인되지", "공개되지", "알 수 없")
                )
                if not honest_unknown:
                    issues.append(
                        crime_issue(
                            "CRIME_UNKNOWN_PROMOTED_TO_FACT",
                            "확인되지 않은 실화 동기는 UNKNOWN 상태를 정직하게 밝혀야 합니다.",
                            "01_CASE/crime_event_contract.json",
                            {"field": field, "motive_summary": motive_summary},
                        )
                    )
        else:
            issues.append(
                crime_issue(
                    "CRIME_FIELD_EVIDENCE_MISSING",
                    "실화 핵심 필드의 Evidence Classification이 올바르지 않습니다.",
                    "01_CASE/crime_event_contract.json",
                    {"field": field, "classification": classification},
                )
            )
    return issues


def validate_crime_event_contract(
    channel: Mapping[str, object],
    production_config: Mapping[str, object],
    variations: Mapping[str, object],
    contract: Mapping[str, object],
    facts: Mapping[str, object],
    candidate_event_briefs: Mapping[str, object] | None = None,
) -> list[ValidationIssue]:
    """승인 Event Brief와 최종 역할 결속 계약의 내용·Hash·Evidence를 검증한다."""
    policy = explicit_crime_policy(channel)
    if policy is None:
        return []
    candidate = approved_candidate(variations)
    event = candidate.get("crime_event") if isinstance(candidate, Mapping) else None
    brief = (
        approved_event_brief(variations, candidate_event_briefs)
        if candidate_event_briefs is not None
        else None
    )
    if not isinstance(candidate, Mapping) or (not isinstance(event, Mapping) and brief is None):
        return [
            crime_issue(
                "APPROVED_CRIME_EVENT_MISSING",
                "승인 Candidate의 Event Brief를 찾을 수 없습니다.",
                "01_CASE/crime_event_contract.json",
                {},
            )
        ]
    issues = event_semantic_shape_issues(
        policy,
        contract,
        "01_CASE/crime_event_contract.json",
    )
    issues.extend(
        structured_harm_issues(
            contract,
            "01_CASE/crime_event_contract.json",
            "victim_ids",
            set(string_values(contract, "victim_ids")),
            contract.get("schema_version") == "1.2.0",
        )
    )
    if brief is not None:
        selection = candidate.get("selection")
        if not isinstance(selection, Mapping):
            return [
                crime_issue(
                    "CRIME_EVENT_CONTRACT_PROJECTION_MISMATCH",
                    "승인 Candidate Selection이 없습니다.",
                    "01_CASE/crime_event_contract.json",
                    {},
                )
            ]
        brief_fields = (
            "primary_crime",
            "core_action_type",
            "responsible_agent_structure",
            "victim_structure",
            "offender_role_slots",
            "victim_role_slots",
            "relationship_context",
            "target_selection_reason",
            "initiating_context",
            "trigger_event",
            "motive_category",
            "motive_summary",
            "non_actionable_method_summary",
            "immediate_harm",
            "lasting_harm",
            "concealment_or_denial",
            "discovery_path",
            "responsibility_path",
            "central_pursuit_question",
            "development_functions",
            "reveal_targets",
            "truth_basis",
        )
        mismatches = {
            field: {"expected": brief.get(field), "actual": contract.get(field)}
            for field in brief_fields
            if contract.get(field) != brief.get(field)
        }
        expected_related_crimes = string_values(brief, "related_crimes")
        primary_crime = brief.get("primary_crime")
        core_action_type = brief.get("core_action_type")
        if (
            primary_crime != core_action_type
            and isinstance(core_action_type, str)
            and core_action_type not in expected_related_crimes
        ):
            expected_related_crimes.append(core_action_type)
        if contract.get("related_crimes") != expected_related_crimes:
            mismatches["related_crimes"] = {
                "expected": expected_related_crimes,
                "actual": contract.get("related_crimes"),
            }
        expected_id = candidate.get("candidate_id")
        if (
            contract.get("approved_candidate_id") != expected_id
            or contract.get("candidate_selection_sha256") != candidate_json_hash(selection)
            or contract.get("candidate_event_brief_sha256") != candidate_json_hash(brief)
            or mismatches
        ):
            issues.append(
                crime_issue(
                    "CRIME_EVENT_CONTRACT_PROJECTION_MISMATCH",
                    "최종 사건 계약이 승인 Candidate Event Brief와 다릅니다.",
                    "01_CASE/crime_event_contract.json",
                    {
                        "expected_candidate_id": expected_id,
                        "actual_candidate_id": contract.get("approved_candidate_id"),
                        "mismatches": mismatches,
                    },
                )
            )
        issues.extend(cardinality_issues(contract))
        actors = string_values(contract, "actor_ids")
        victims = string_values(contract, "victim_ids")
        offender_slots = string_values(brief, "offender_role_slots")
        victim_slots = string_values(brief, "victim_role_slots")
        bindings = mapping_records(contract, "role_bindings")
        binding_slots = [binding.get("role_slot") for binding in bindings]
        missing_slots = sorted(
            set(offender_slots + victim_slots) - {str(slot) for slot in binding_slots}
        )
        duplicated_slots = sorted(
            {str(slot) for slot in binding_slots if binding_slots.count(slot) > 1}
        )
        offender_bound_ids = [
            binding.get("character_id")
            for binding in bindings
            if binding.get("role_slot") in offender_slots
        ]
        victim_bound_ids = [
            binding.get("character_id")
            for binding in bindings
            if binding.get("role_slot") in victim_slots
        ]
        if missing_slots:
            issues.append(
                crime_issue(
                    "CRIME_ROLE_BINDING_MISSING",
                    "필수 Crime Role Slot Binding이 없습니다.",
                    "01_CASE/crime_event_contract.json",
                    {"role_slots": missing_slots},
                )
            )
        if duplicated_slots:
            issues.append(
                crime_issue(
                    "CRIME_ROLE_BINDING_DUPLICATED",
                    "Crime Role Slot 또는 Character Binding이 중복됐습니다.",
                    "01_CASE/crime_event_contract.json",
                    {"role_slots": duplicated_slots},
                )
            )
        if actors != offender_bound_ids or victims != victim_bound_ids:
            issues.append(
                crime_issue(
                    "CRIME_CHARACTER_TRACE_MISMATCH",
                    "actor_ids와 victim_ids가 명시적 Role Binding과 다릅니다.",
                    "01_CASE/crime_event_contract.json",
                    {
                        "actor_ids": actors,
                        "offender_binding_ids": offender_bound_ids,
                        "victim_ids": victims,
                        "victim_binding_ids": victim_bound_ids,
                    },
                )
            )
        brief_harms = harm_records(brief, "harms")
        if brief_harms:
            slot_map = {
                cast(str, binding["role_slot"]): cast(str, binding["character_id"])
                for binding in bindings
                if isinstance(binding.get("role_slot"), str)
                and isinstance(binding.get("character_id"), str)
            }
            expected_harms = bind_harm_records(brief_harms, slot_map)
            if contract.get("harms") != expected_harms:
                issues.append(
                    crime_issue(
                        "CRIME_HARM_PROJECTION_MISMATCH",
                        "최종 피해 계약이 Event Brief의 피해자 Role 결속과 다릅니다.",
                        "01_CASE/crime_event_contract.json",
                        {
                            "expected_harms": expected_harms,
                            "actual_harms": contract.get("harms"),
                        },
                    )
                )
        issues.extend(validate_truth_basis(production_config, contract, facts))
        return issues
    assert isinstance(event, Mapping)
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


def validate_crime_role_bindings(
    contract: Mapping[str, object],
    characters: Mapping[str, object],
) -> list[ValidationIssue]:
    """최종 Role Binding이 실제 Character의 선언된 Slot과 일치하는지 검사한다."""
    if not isinstance(contract.get("responsible_agent_structure"), str):
        return []
    character_records = {
        cast(str, character.get("character_id")): character
        for character in mapping_records(characters, "characters")
        if isinstance(character.get("character_id"), str)
    }
    bindings = mapping_records(contract, "role_bindings")
    issues = cardinality_issues(contract)
    actor_ids = string_values(contract, "actor_ids")
    victim_ids = string_values(contract, "victim_ids")
    offender_slots = string_values(contract, "offender_role_slots")
    victim_slots = string_values(contract, "victim_role_slots")
    if len(actor_ids) != len(offender_slots) or len(set(actor_ids)) != len(offender_slots):
        issues.append(
            crime_issue(
                "OFFENDER_CARDINALITY_MISMATCH",
                "각 가해자 Role Slot은 서로 다른 actor_id에 결속해야 합니다.",
                "01_CASE/crime_event_contract.json",
                {
                    "role_slot_count": len(offender_slots),
                    "actor_count": len(actor_ids),
                    "distinct_actor_count": len(set(actor_ids)),
                },
            )
        )
    if len(victim_ids) != len(victim_slots) or len(set(victim_ids)) != len(victim_slots):
        issues.append(
            crime_issue(
                "VICTIM_CARDINALITY_MISMATCH",
                "각 피해자 Role Slot은 서로 다른 victim_id에 결속해야 합니다.",
                "01_CASE/crime_event_contract.json",
                {
                    "role_slot_count": len(victim_slots),
                    "victim_count": len(victim_ids),
                    "distinct_victim_count": len(set(victim_ids)),
                },
            )
        )
    participant_ids = set(actor_ids + victim_ids)
    binding_character_ids = {
        str(binding.get("character_id"))
        for binding in bindings
        if isinstance(binding.get("character_id"), str)
    }
    missing_characters = sorted((participant_ids | binding_character_ids) - set(character_records))
    if missing_characters:
        issues.append(
            crime_issue(
                "CRIME_ROLE_CHARACTER_NOT_FOUND",
                "Crime Role Binding의 Character ID가 존재하지 않습니다.",
                "01_CASE/crime_event_contract.json",
                {"character_ids": missing_characters},
            )
        )
    mismatched_bindings = [
        {
            "role_slot": binding.get("role_slot"),
            "character_id": binding.get("character_id"),
        }
        for binding in bindings
        if isinstance(binding.get("character_id"), str)
        and binding.get("character_id") in character_records
        and binding.get("role_slot")
        not in string_values(
            character_records[cast(str, binding.get("character_id"))],
            "crime_role_slots",
        )
    ]
    if mismatched_bindings:
        issues.append(
            crime_issue(
                "CRIME_CHARACTER_TRACE_MISMATCH",
                "Crime Role Binding과 Character의 선언된 Role Slot이 다릅니다.",
                "02_CHARACTER/characters.json",
                {"bindings": mismatched_bindings},
            )
        )
    return issues


def crime_case_trace_issues(
    contract: Mapping[str, object],
    case_input: Mapping[str, object],
    facts: Mapping[str, object],
) -> list[ValidationIssue]:
    """최종 사건 계약이 Case와 네 종류 Crime Fact에 투영됐는지 검사한다."""
    expected_case = {
        "primary_crime": contract.get("primary_crime"),
        "responsible_actor_ids": string_values(contract, "actor_ids"),
        "victim_ids": string_values(contract, "victim_ids"),
        "motive_summary": contract.get("motive_summary"),
        "crime_method_summary": contract.get("non_actionable_method_summary"),
        "harm_result": (f"{contract.get('immediate_harm')} / {contract.get('lasting_harm')}"),
        "final_case_truth": contract.get("responsibility_path"),
    }
    mismatches = {
        field: {"expected": expected, "actual": case_input.get(field)}
        for field, expected in expected_case.items()
        if case_input.get(field) != expected
    }
    issues: list[ValidationIssue] = []
    if mismatches:
        issues.append(
            crime_issue(
                "CRIME_CASE_TRACE_MISMATCH",
                "Case Input의 범죄 핵심 필드가 최종 사건 계약과 다릅니다.",
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
        cast(str, fact.get("crime_fact_type"))
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
            crime_issue(
                "CRIME_FACT_TRACE_MISMATCH",
                "범죄 행위·피해·동기 상태·책임 주체 Fact가 모두 필요합니다.",
                "01_CASE/facts.json",
                {"missing_crime_fact_types": missing_fact_types},
            )
        )
    return issues


def reachable_node(
    start_ids: set[str],
    target_ids: set[str],
    edges: set[tuple[str, str]],
) -> bool:
    """유향 Causal Graph에서 목표 Node까지 경로가 존재하는지 판정한다."""
    pending = list(start_ids)
    visited = set(start_ids)
    while pending:
        current = pending.pop()
        if current in target_ids:
            return True
        next_ids = {target for source, target in edges if source == current} - visited
        visited.update(next_ids)
        pending.extend(next_ids)
    return False


def validate_crime_event_traceability(
    contract: Mapping[str, object],
    characters: Mapping[str, object],
    case_input: Mapping[str, object],
    facts: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    causal_graph: Mapping[str, object],
    viewer_timeline: Mapping[str, object],
) -> list[ValidationIssue]:
    """승인 사건을 Character부터 Viewer Reveal까지 교차 검증한다."""
    if not isinstance(contract.get("event_id"), str):
        return []
    issues = [
        *validate_crime_role_bindings(contract, characters),
        *crime_case_trace_issues(contract, case_input, facts),
    ]
    event_id = contract.get("event_id")
    actor_ids = set(string_values(contract, "actor_ids"))
    victim_ids = set(string_values(contract, "victim_ids"))
    harm_ids = set(string_values(contract, "harm_ids"))
    timeline_events = mapping_records(actual_timeline, "events")
    crime_events = [
        event
        for event in timeline_events
        if event.get("crime_event_id") == event_id and event.get("event_type") == "CRIME_EVENT"
    ]
    harm_events = [
        event
        for event in timeline_events
        if event.get("crime_event_id") == event_id and event.get("event_type") == "HARM_RESULT"
    ]
    crime_event_valid = any(
        set(string_values(event, "actor_ids")) == actor_ids
        and set(string_values(event, "victim_ids")) == victim_ids
        and harm_ids.issubset(set(string_values(event, "harm_ids")))
        for event in crime_events
    )
    timeline_harm_ids = {
        harm_id
        for event in harm_events
        for harm_id in string_values(event, "harm_ids")
    }
    harm_event_valid = harm_ids.issubset(timeline_harm_ids) and all(
        bool(set(string_values(event, "actor_ids")))
        and set(string_values(event, "actor_ids")).issubset(actor_ids)
        and bool(set(string_values(event, "victim_ids")))
        and set(string_values(event, "victim_ids")).issubset(victim_ids)
        for event in harm_events
    )
    if not crime_event_valid or not harm_event_valid:
        issues.append(
            crime_issue(
                "CRIME_TIMELINE_TRACE_MISMATCH",
                "Actual Timeline에 결속된 범죄 Event와 피해 결과 Event가 필요합니다.",
                "03_TIMELINE/actual_timeline.json",
                {
                    "crime_event_found": crime_event_valid,
                    "harm_event_found": harm_event_valid,
                    "crime_event_id": event_id,
                },
            )
        )
    nodes = mapping_records(causal_graph, "nodes")
    trace_nodes = [node for node in nodes if node.get("crime_event_id") == event_id]
    node_ids_by_type: dict[str, set[str]] = {}
    for node in trace_nodes:
        node_id = node.get("node_id")
        node_type = node.get("type")
        if isinstance(node_id, str) and isinstance(node_type, str):
            node_ids_by_type.setdefault(node_type, set()).add(node_id)
    edges = {
        (cast(str, edge.get("from")), cast(str, edge.get("to")))
        for edge in mapping_records(causal_graph, "edges")
        if isinstance(edge.get("from"), str) and isinstance(edge.get("to"), str)
    }
    crime_node_valid = any(
        node.get("type") == "CRIME_EVENT"
        and set(string_values(node, "actor_ids")) == actor_ids
        and set(string_values(node, "victim_ids")) == victim_ids
        and harm_ids.issubset(set(string_values(node, "harm_ids")))
        for node in trace_nodes
    )
    causal_harm_ids = {
        harm_id
        for node in trace_nodes
        if node.get("type") == "HARM_RESULT"
        for harm_id in string_values(node, "harm_ids")
    }
    harm_node_valid = harm_ids.issubset(causal_harm_ids)
    core_path_valid = reachable_node(
        node_ids_by_type.get("MOTIVE_OR_TRIGGER", set()),
        node_ids_by_type.get("CRIME_EVENT", set()),
        edges,
    ) and reachable_node(
        node_ids_by_type.get("CRIME_EVENT", set()),
        node_ids_by_type.get("HARM_RESULT", set()),
        edges,
    )
    responsibility_path_valid = reachable_node(
        node_ids_by_type.get("CONCEALMENT_OR_DENIAL", set()),
        node_ids_by_type.get("DISCOVERY_PATH", set()),
        edges,
    ) and reachable_node(
        node_ids_by_type.get("DISCOVERY_PATH", set()),
        node_ids_by_type.get("RESPONSIBILITY_CONFIRMATION", set()),
        edges,
    )
    if (
        not core_path_valid
        or not responsibility_path_valid
        or not crime_node_valid
        or not harm_node_valid
    ):
        issues.append(
            crime_issue(
                "CRIME_CAUSAL_TRACE_MISMATCH",
                "Causal Graph에 동기/촉발→범죄→피해와 은폐→발견→책임 경로가 필요합니다.",
                "04_MYSTERY/causal_graph.json",
                {
                    "core_path_valid": core_path_valid,
                    "responsibility_path_valid": responsibility_path_valid,
                    "crime_node_valid": crime_node_valid,
                    "harm_node_valid": harm_node_valid,
                },
            )
        )
    expected_targets = [
        (target.get("reveal_target_id"), target.get("target_type"))
        for target in mapping_records(contract, "reveal_targets")
    ]
    actual_targets = [
        (reveal.get("reveal_target_id"), reveal.get("target_type"))
        for reveal in mapping_records(viewer_timeline, "reveals")
        if isinstance(reveal.get("reveal_target_id"), str)
    ]
    if actual_targets != expected_targets:
        issues.append(
            crime_issue(
                "CRIME_REVEAL_TRACE_MISMATCH",
                "Viewer Timeline이 사건 계약의 Reveal Target과 공개 순서를 보존하지 않았습니다.",
                "03_TIMELINE/viewer_timeline.json",
                {"expected": expected_targets, "actual": actual_targets},
            )
        )
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


def required_development_function_ids(
    channel: Mapping[str, object],
    contract: Mapping[str, object],
) -> set[str]:
    """Channel Policy에서 계산한 필수 Development Function ID를 반환한다."""
    policy = explicit_crime_policy(channel)
    if policy is None:
        return set()
    return set(required_development_function_map(policy, contract))


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
    required_function_ids = required_development_function_ids(channel, contract)
    declared_function_ids = {
        cast(str, function.get("development_function_id"))
        for function in mapping_records(contract, "development_functions")
        if isinstance(function.get("development_function_id"), str)
    }
    mapped_function_ids: set[str] = set()
    mapped_harm_ids: set[str] = set()
    for scene, realization in records:
        scene_id = scene.get("scene_id")
        realization_harms = set(string_values(realization, "harm_ids"))
        mapped_harm_ids.update(realization_harms & harm_ids)
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
        function_ids = set(string_values(realization, "development_function_ids"))
        mapped_function_ids.update(function_ids)
        unknown_function_ids = sorted(function_ids - declared_function_ids)
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
            or unknown_function_ids
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
                        "unknown_development_function_ids": unknown_function_ids,
                    },
                )
            )
    unmapped_functions = sorted(required_function_ids - mapped_function_ids)
    if unmapped_functions:
        issues.append(
            crime_issue(
                "CRIME_DEVELOPMENT_FUNCTION_UNMAPPED",
                "필수 Development Function이 어떤 Scene에도 연결되지 않았습니다.",
                "06_SCENE/scene_cards.json",
                {"development_function_ids": unmapped_functions},
            )
        )
    missing_harm_ids = sorted(harm_ids - mapped_harm_ids)
    if missing_harm_ids:
        issues.append(
            crime_issue(
                "HARM_REALIZATION_MISSING",
                "모든 Contract Harm은 최소 한 개 Scene Realization에 연결되어야 합니다.",
                "06_SCENE/scene_cards.json",
                {"harm_ids": missing_harm_ids},
            )
        )
    for function_id in sorted(required_function_ids):
        segment_modes = {
            mode
            for segment in planned_segments.values()
            if isinstance((mode := canonical_mode(segment.get("segment_type"))), str)
            if function_id in string_values(segment, "crime_development_function_ids")
        }
        if "DRAMA" in segment_modes:
            continue
        if segment_modes == {"NARRATION"}:
            code = "CRIME_FUNCTION_NARRATION_ONLY"
        elif segment_modes == {"PANEL_REACTION"}:
            code = "CRIME_FUNCTION_PANEL_ONLY"
        else:
            code = "CRIME_DEVELOPMENT_FUNCTION_NOT_DRAMATIZED"
        issues.append(
            crime_issue(
                code,
                "필수 Development Function은 최소 한 개의 Drama Segment에 배치해야 합니다.",
                "06_SCENE/presentation_plan.json",
                {"development_function_id": function_id, "segment_modes": sorted(segment_modes)},
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
    """실제 방송 발췌와 사건·행위 추적 정보의 연결을 판정한다."""
    body = segment.get("body")
    event_id = contract.get("event_id")
    action_type = contract.get("core_action_type")
    if not isinstance(body, str) or not isinstance(event_id, str):
        return False
    visible_body = CRIME_TRACE_BLOCK.sub(" ", body)
    if not visible_body.strip():
        return False
    for fields in segment_trace_blocks(segment):
        if (
            event_id in fields.get("EVENT", set())
            and action_type in fields.get("ACTION", set())
        ):
            return True
    return False


def segment_trace_blocks(
    segment: Mapping[str, object],
) -> list[dict[str, set[str]]]:
    """Segment의 범죄 추적 Block을 구조화된 필드 집합으로 반환한다."""
    body = segment.get("body")
    if not isinstance(body, str):
        return []
    return [
        {
            key: {item.strip() for item in value.split(",") if item.strip()}
            for key, value in CRIME_TRACE_FIELD.findall(block.group("body"))
        }
        for block in CRIME_TRACE_BLOCK.finditer(body)
    ]


def segment_development_function_ids(segment: Mapping[str, object]) -> set[str]:
    """Segment HTML 추적 정보에서 Development Function ID를 읽는다."""
    function_ids: set[str] = set()
    for fields in segment_trace_blocks(segment):
        function_ids.update(fields.get("DEV", set()))
    return function_ids


def segment_harm_ids(segment: Mapping[str, object]) -> set[str]:
    """Segment HTML 추적 정보에서 Harm ID를 읽는다."""
    harms: set[str] = set()
    for fields in segment_trace_blocks(segment):
        harms.update(fields.get("HARM", set()))
    return harms


def segment_has_crime_evidence(
    segment: Mapping[str, object],
    contract: Mapping[str, object],
) -> bool:
    """실제 문구가 있는 Segment에 사건의 행동·피해·기능 연결이 있는지 판정한다."""
    body = segment.get("body")
    event_id = contract.get("event_id")
    action_type = contract.get("core_action_type")
    harm_ids = set(string_values(contract, "harm_ids"))
    declared_function_ids = {
        cast(str, function.get("development_function_id"))
        for function in mapping_records(contract, "development_functions")
        if isinstance(function.get("development_function_id"), str)
    }
    if not isinstance(body, str) or not isinstance(event_id, str):
        return False
    if not CRIME_TRACE_BLOCK.sub(" ", body).strip():
        return False
    return any(
        event_id in fields.get("EVENT", set())
        and (
            action_type in fields.get("ACTION", set())
            or bool(harm_ids.intersection(fields.get("HARM", set())))
            or bool(declared_function_ids.intersection(fields.get("DEV", set())))
        )
        for fields in segment_trace_blocks(segment)
    )


def realization_evidence_type(
    realization_mode: object,
    has_action: bool,
    has_harm: bool,
) -> str:
    """Scene 실현 방식을 구조적 Evidence Type으로 변환한다."""
    if realization_mode == "DIRECT_ACTION":
        return "ACTION"
    if realization_mode == "AFTERMATH_CAUSAL" or (has_harm and not has_action):
        return "HARM_AFTERMATH"
    return "BEHAVIOR_OR_CHOICE"


def crime_script_bindings(
    contract: Mapping[str, object],
    scene_cards: Mapping[str, object],
    final_script: str,
) -> list[dict[str, object]]:
    """Scene 계획을 실제 Final Script의 범죄 행동 Segment와 결합한다."""
    segments = script_segments_by_id(final_script)
    script_hash = sha256(final_script.encode("utf-8")).hexdigest()
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
                or not segment_has_crime_evidence(segment, contract)
            ):
                continue
            linked_harm_ids = sorted(
                set(string_values(realization, "harm_ids"))
                & segment_harm_ids(segment)
            )
            has_action = segment_has_crime_action(segment, contract)
            bindings.append(
                {
                    "crime_event_id": contract.get("event_id"),
                    "scene_id": scene.get("scene_id"),
                    "segment_id": segment_id,
                    "selector_type": "SEGMENT_ID",
                    "selector_id": segment_id,
                    "excerpt_hash": canonical_json_hash(segment),
                    "source_script_hash": script_hash,
                    "evidence_type": realization_evidence_type(
                        realization.get("realization_mode"),
                        has_action,
                        bool(linked_harm_ids),
                    ),
                    "development_function_ids": sorted(
                        set(string_values(realization, "development_function_ids"))
                        & segment_development_function_ids(segment)
                    ),
                    "harm_ids": linked_harm_ids,
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


def script_meaning_tokens(segment: Mapping[str, object]) -> set[str]:
    """기계 추적 정보를 제거한 Segment 방송 문구의 의미 Token을 반환한다."""
    body = segment.get("body")
    if not isinstance(body, str):
        return set()
    visible = CRIME_TRACE_BLOCK.sub(" ", body)
    visible = re.sub(r"\[[A-Z][A-Z0-9_:-]*\]", " ", visible)
    return {token.casefold() for token in SCRIPT_WORD.findall(visible) if len(token) > 1}


def narration_content_issues(final_script: str) -> list[ValidationIssue]:
    """실제 Narration 문구가 Drama나 Panel 정보를 그대로 반복하는지 검사한다."""
    segments = script_segments_by_id(final_script)
    narration_segments = [
        segment
        for segment in segments.values()
        if canonical_mode(segment.get("segment_type")) == "NARRATION"
    ]
    comparison_segments = [
        segment
        for segment in segments.values()
        if canonical_mode(segment.get("segment_type")) in {"DRAMA", "PANEL_REACTION"}
    ]
    issues: list[ValidationIssue] = []
    for narration in narration_segments:
        narration_tokens = script_meaning_tokens(narration)
        if len(narration_tokens) < 4:
            continue
        for comparison in comparison_segments:
            comparison_tokens = script_meaning_tokens(comparison)
            overlap = narration_tokens.intersection(comparison_tokens)
            duplication_ratio = len(overlap) / len(narration_tokens)
            if len(overlap) < 4 or duplication_ratio < 0.65:
                continue
            comparison_mode = canonical_mode(comparison.get("segment_type"))
            code = (
                "NARRATION_PANEL_DUPLICATION"
                if comparison_mode == "PANEL_REACTION"
                else "NARRATION_VISIBLE_INFORMATION_DUPLICATION"
            )
            issues.append(
                crime_issue(
                    code,
                    "Narration은 이미 보이거나 Panel이 말한 정보를 반복하지 않아야 합니다.",
                    "07_SCRIPT/final_script.md",
                    {
                        "narration_segment_id": narration.get("segment_id"),
                        "comparison_segment_id": comparison.get("segment_id"),
                        "duplication_ratio": round(duplication_ratio, 4),
                    },
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
        *narration_content_issues(final_script),
    ]
    bindings = crime_script_bindings(contract, scene_cards, final_script)
    parsed_segments = script_segments_by_id(final_script)
    action_bindings = [
        binding
        for binding in bindings
        if isinstance(binding.get("segment_id"), str)
        and (
            segment := parsed_segments.get(cast(str, binding["segment_id"]))
        ) is not None
        and segment_has_crime_action(segment, contract)
    ]
    linked_harm_ids = {
        harm_id
        for binding in bindings
        for harm_id in string_values(binding, "harm_ids")
    }
    missing_harm_ids = sorted(
        set(string_values(contract, "harm_ids")) - linked_harm_ids
    )
    if not action_bindings or missing_harm_ids:
        issues.append(
            crime_issue(
                "SCRIPT_CRIME_ACTION_UNREALIZED",
                "Scene ID나 범죄 장르 태그만으로는 충분하지 않으며 실제 Drama "
                "발췌들이 사건 행동과 피해 결과를 구조적으로 연결해야 합니다.",
                "07_SCRIPT/final_script.md",
                {
                    "event_id": contract.get("event_id"),
                    "action_evidence_missing": not action_bindings,
                    "missing_harm_ids": missing_harm_ids,
                },
            )
        )
    required_function_ids = required_development_function_ids(channel, contract)
    declared_function_ids = {
        cast(str, function.get("development_function_id"))
        for function in mapping_records(contract, "development_functions")
        if isinstance(function.get("development_function_id"), str)
    }
    unknown_script_function_ids = sorted(
        {
            function_id
            for segment in parsed_segments.values()
            for function_id in segment_development_function_ids(segment)
            if function_id not in declared_function_ids
        }
    )
    if unknown_script_function_ids:
        issues.append(
            crime_issue(
                "CRIME_DEVELOPMENT_FUNCTION_REFERENCE_UNKNOWN",
                "Script가 사건 계약에 없는 Development Function ID를 참조합니다.",
                "07_SCRIPT/final_script.md",
                {"development_function_ids": unknown_script_function_ids},
            )
        )
    for function_id in sorted(required_function_ids):
        realized_modes = {
            mode
            for segment in parsed_segments.values()
            if isinstance((mode := canonical_mode(segment.get("segment_type"))), str)
            if function_id in segment_development_function_ids(segment)
        }
        drama_realized = any(
            function_id in string_values(binding, "development_function_ids")
            for binding in bindings
        )
        if drama_realized:
            continue
        if realized_modes == {"NARRATION"}:
            code = "CRIME_FUNCTION_NARRATION_ONLY"
        elif realized_modes == {"PANEL_REACTION"}:
            code = "CRIME_FUNCTION_PANEL_ONLY"
        else:
            code = "CRIME_DEVELOPMENT_FUNCTION_SCRIPT_MISSING"
        issues.append(
            crime_issue(
                code,
                "필수 Development Function의 실제 Drama Script 발췌가 없습니다.",
                "07_SCRIPT/final_script.md",
                {
                    "development_function_id": function_id,
                    "realized_modes": sorted(realized_modes),
                },
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
            "function_results": [],
            "evidence_links": [],
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
    parsed_script_segments = script_segments_by_id(final_script)
    action_bindings = [
        binding
        for binding in bindings
        if isinstance(binding.get("segment_id"), str)
        and (
            segment := parsed_script_segments.get(cast(str, binding["segment_id"]))
        ) is not None
        and segment_has_crime_action(segment, contract)
    ]
    linked_harm_ids = {
        harm_id
        for binding in bindings
        for harm_id in string_values(binding, "harm_ids")
    }
    event_complete = bool(action_bindings) and set(
        string_values(contract, "harm_ids")
    ).issubset(linked_harm_ids)
    first_binding = action_bindings[0] if action_bindings else {}
    event_status = "NEEDS_REVIEW" if event_complete else "MISSING"
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
    function_results = []
    required_function_map = (
        required_development_function_map(
            cast(Mapping[str, object], explicit_crime_policy(channel)),
            contract,
        )
        if explicit_crime_policy(channel) is not None
        else {}
    )
    for function_id, function_type in sorted(required_function_map.items()):
        function_bindings = [
            binding
            for binding in bindings
            if function_id in string_values(binding, "development_function_ids")
        ]
        function_results.append(
            {
                "development_function_id": function_id,
                "function_type": function_type,
                "status": "NEEDS_REVIEW" if function_bindings else "MISSING",
                "evidence_link_ids": [
                    f"CRIME-EVIDENCE-{bindings.index(binding) + 1:03d}"
                    for binding in function_bindings
                ],
            }
        )
    evidence_links = [
        {
            "evidence_link_id": f"CRIME-EVIDENCE-{index:03d}",
            **binding,
        }
        for index, binding in enumerate(bindings, 1)
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
        "function_results": function_results,
        "evidence_links": evidence_links,
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
        for field in (
            "event_results",
            "function_results",
            "reveal_results",
            "layer_results",
        )
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
    channel: Mapping[str, object],
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
        ("DEVELOPMENT_FUNCTION", function_id)
        for function_id in required_development_function_ids(channel, contract)
    )
    action_type = contract.get("core_action_type")
    if isinstance(action_type, str):
        subjects.add(("CRIME_ACTION", action_type))
    subjects.update(
        ("HARM_RESULT", harm_id)
        for harm_id in string_values(contract, "harm_ids")
    )
    subjects.update(
        ("REVEAL_TIMING", cast(str, target.get("reveal_target_id")))
        for target in mapping_records(contract, "reveal_targets")
        if isinstance(target.get("reveal_target_id"), str)
    )
    subjects.update(
        ("PREMATURE_DISCLOSURE_SCAN", cast(str, target.get("reveal_target_id")))
        for target in mapping_records(contract, "reveal_targets")
        if isinstance(target.get("reveal_target_id"), str)
    )
    return subjects

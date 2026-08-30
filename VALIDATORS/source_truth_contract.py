"""검증된 Source Truth와 생성 Story 구조의 결속을 검증한다."""

from collections.abc import Mapping
from copy import deepcopy

from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.models import ValidationIssue

TRUTH_DIMENSION_FIELDS: dict[str, str] = {
    "incident_type": "verified_incident_type",
    "setting": "verified_setting",
    "responsible_agent_structure": "verified_responsible_agent_structure",
    "legal_outcome": "verified_legal_outcome",
}


def truth_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Source Truth 오류를 표준 형식으로 반환한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def contract_payload(document: Mapping[str, object]) -> dict[str, object]:
    """자기 Hash를 제외한 Source Truth Contract Payload를 반환한다."""
    return {key: deepcopy(value) for key, value in document.items() if key != "contract_sha256"}


def source_truth_contract_sha256(document: Mapping[str, object]) -> str:
    """Source Truth Contract의 정규 SHA-256을 반환한다."""
    return document_sha256(contract_payload(document))


def truth_dimension_is_locked(
    contract: Mapping[str, object],
    dimension: str,
) -> bool:
    """분류와 잠금 목록을 사용해 Dimension의 변경 금지 여부를 반환한다."""
    if contract.get("source_truth_classification") == "VERIFIED_TRUE_CASE":
        return True
    locked = contract.get("locked_dimensions")
    return isinstance(locked, list) and dimension in locked


def source_truth_project_constraints(
    constraints: Mapping[str, object],
    contract: Mapping[str, object] | None,
    available_dimensions: set[str],
) -> dict[str, object]:
    """검증된 Truth Dimension을 Project Constraint의 IN Rule로 투영한다."""
    next_constraints = deepcopy(dict(constraints))
    if contract is None:
        return next_constraints
    raw_rules = next_constraints.get("must_use")
    rules = list(raw_rules) if isinstance(raw_rules, list) else []
    for dimension, contract_field in TRUTH_DIMENSION_FIELDS.items():
        if dimension not in available_dimensions:
            continue
        value = contract.get(contract_field)
        if not isinstance(value, str) or not truth_dimension_is_locked(contract, dimension):
            continue
        rules.append(
            {
                "field": dimension,
                "operator": "IN",
                "values": [value],
                "reason": "Source Truth Contract에서 검증된 구조입니다.",
            }
        )
    next_constraints["must_use"] = rules
    return next_constraints


def records_by_id(
    document: Mapping[str, object],
    records_key: str,
    id_key: str,
) -> dict[str, Mapping[str, object]]:
    """Artifact Record를 문자열 ID로 색인한다."""
    records = document.get(records_key)
    if not isinstance(records, list):
        return {}
    result: dict[str, Mapping[str, object]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        identifier = record.get(id_key)
        if isinstance(identifier, str):
            result[identifier] = record
    return result


def duplicate_record_ids(
    document: Mapping[str, object],
    records_key: str,
    id_key: str,
) -> list[str]:
    """Artifact 배열의 중복 Canonical ID를 반환한다."""
    records = document.get(records_key)
    if not isinstance(records, list):
        return []
    identifiers = [
        record.get(id_key)
        for record in records
        if isinstance(record, Mapping) and isinstance(record.get(id_key), str)
    ]
    return sorted(
        {
            identifier
            for identifier in identifiers
            if isinstance(identifier, str) and identifiers.count(identifier) > 1
        }
    )


def validate_source_truth_contract_integrity(
    contract: Mapping[str, object],
    source_subjects: Mapping[str, object],
    verified_events: Mapping[str, object],
    claims: Mapping[str, object],
) -> list[ValidationIssue]:
    """Source Truth Contract의 Hash와 참조 무결성을 검증한다."""
    issues: list[ValidationIssue] = []
    expected_hash = source_truth_contract_sha256(contract)
    if contract.get("contract_sha256") != expected_hash:
        issues.append(
            truth_issue(
                "SOURCE_TRUTH_CONTRACT_HASH_MISMATCH",
                "Source Truth Contract Hash가 현재 내용과 다릅니다.",
                "01_CASE/source_truth_contract.json",
                {"expected": expected_hash, "actual": contract.get("contract_sha256")},
            )
        )
    subject_ids = set(records_by_id(source_subjects, "subjects", "source_subject_id"))
    event_ids = set(records_by_id(verified_events, "events", "verified_event_id"))
    claim_records = records_by_id(claims, "claims", "fact_id")
    claim_ids = set(claim_records)
    referenced_subjects = contract.get("verified_subject_ids")
    referenced_events = contract.get("verified_event_ids")
    referenced_claims = contract.get("source_claim_ids")
    missing_subjects = (
        {
            subject_id
            for subject_id in referenced_subjects
            if isinstance(subject_id, str) and subject_id not in subject_ids
        }
        if isinstance(referenced_subjects, list)
        else set()
    )
    missing_events = (
        sorted(set(referenced_events) - event_ids) if isinstance(referenced_events, list) else []
    )
    referenced_claim_ids = (
        {claim_id for claim_id in referenced_claims if isinstance(claim_id, str)}
        if isinstance(referenced_claims, list)
        else set()
    )
    missing_claims = referenced_claim_ids - claim_ids
    source_subject_records = records_by_id(
        source_subjects,
        "subjects",
        "source_subject_id",
    )
    for source_subject in source_subject_records.values():
        related_fact_ids = source_subject.get("related_fact_ids")
        if isinstance(related_fact_ids, list):
            referenced_claim_ids.update(
                fact_id for fact_id in related_fact_ids if isinstance(fact_id, str)
            )
            missing_claims.update(
                fact_id
                for fact_id in related_fact_ids
                if isinstance(fact_id, str) and fact_id not in claim_ids
            )
    raw_relationships = contract.get("verified_relationships")
    if isinstance(raw_relationships, list):
        for relationship in raw_relationships:
            if not isinstance(relationship, Mapping):
                continue
            for field in ("from_source_subject_id", "to_source_subject_id"):
                subject_id = relationship.get(field)
                if isinstance(subject_id, str) and subject_id not in subject_ids:
                    missing_subjects.add(subject_id)
            relationship_claims = relationship.get("source_claim_ids")
            if isinstance(relationship_claims, list):
                referenced_claim_ids.update(
                    claim_id for claim_id in relationship_claims if isinstance(claim_id, str)
                )
                missing_claims.update(
                    claim_id
                    for claim_id in relationship_claims
                    if isinstance(claim_id, str) and claim_id not in claim_ids
                )
    event_records = records_by_id(verified_events, "events", "verified_event_id")
    event_sequences: list[int] = []
    for event in event_records.values():
        sequence = event.get("sequence")
        if isinstance(sequence, int):
            event_sequences.append(sequence)
        participants = event.get("participant_source_subject_ids")
        if isinstance(participants, list):
            missing_subjects.update(
                subject_id
                for subject_id in participants
                if isinstance(subject_id, str) and subject_id not in subject_ids
            )
        event_claims = event.get("source_claim_ids")
        if isinstance(event_claims, list):
            referenced_claim_ids.update(
                claim_id for claim_id in event_claims if isinstance(claim_id, str)
            )
            missing_claims.update(
                claim_id
                for claim_id in event_claims
                if isinstance(claim_id, str) and claim_id not in claim_ids
            )
    duplicate_event_sequence = len(event_sequences) != len(set(event_sequences))
    duplicate_subject_ids = duplicate_record_ids(
        source_subjects,
        "subjects",
        "source_subject_id",
    )
    duplicate_event_ids = duplicate_record_ids(
        verified_events,
        "events",
        "verified_event_id",
    )
    duplicate_claim_ids = duplicate_record_ids(
        claims,
        "claims",
        "fact_id",
    )
    non_fact_claim_ids = sorted(
        claim_id
        for claim_id in referenced_claim_ids & claim_ids
        if claim_records[claim_id].get("classification") != "FACT"
    )
    if (
        missing_subjects
        or missing_events
        or missing_claims
        or non_fact_claim_ids
        or duplicate_event_sequence
        or duplicate_subject_ids
        or duplicate_event_ids
        or duplicate_claim_ids
    ):
        issues.append(
            truth_issue(
                "SOURCE_TRUTH_CONTRACT_REFERENCE_BROKEN",
                "Source Truth Contract가 존재하지 않는 검증 Record를 참조합니다.",
                "01_CASE/source_truth_contract.json",
                {
                    "missing_subject_ids": sorted(missing_subjects),
                    "missing_event_ids": missing_events,
                    "missing_claim_ids": sorted(missing_claims),
                    "non_fact_claim_ids": non_fact_claim_ids,
                    "duplicate_event_sequence": duplicate_event_sequence,
                    "duplicate_subject_ids": duplicate_subject_ids,
                    "duplicate_event_ids": duplicate_event_ids,
                    "duplicate_claim_ids": duplicate_claim_ids,
                },
            )
        )
    locked = contract.get("locked_dimensions")
    flexible = contract.get("flexible_dimensions")
    unknown = contract.get("unknown_dimensions")
    sets = [set(value) for value in (locked, flexible, unknown) if isinstance(value, list)]
    overlap = sorted(
        {
            dimension
            for index, left in enumerate(sets)
            for right in sets[index + 1 :]
            for dimension in left & right
        }
    )
    if overlap:
        issues.append(
            truth_issue(
                "SOURCE_TRUTH_DIMENSION_CONFLICT",
                "Truth Dimension을 동시에 잠금·유연·미상으로 분류할 수 없습니다.",
                "01_CASE/source_truth_contract.json",
                {"dimensions": overlap},
            )
        )
    return issues


def story_dimension_value(
    story: Mapping[str, object],
    dimension: str,
) -> object:
    """Story DNA 내부 Dimension 값을 반환한다."""
    story_dna = story.get("story_dna")
    return story_dna.get(dimension) if isinstance(story_dna, Mapping) else None


def validate_truth_dimensions(
    contract: Mapping[str, object],
    story: Mapping[str, object] | None,
    case_input: Mapping[str, object] | None,
    crime_psychology: Mapping[str, object] | None,
) -> list[ValidationIssue]:
    """검증된 구조 Dimension과 UNKNOWN 경계를 생성 Artifact에 적용한다."""
    issues: list[ValidationIssue] = []
    targets: dict[str, tuple[object, str, bool]] = {
        "incident_type": (
            story_dimension_value(story, "incident_type") if story is not None else None,
            "VERIFIED_INCIDENT_CHANGED",
            story is not None,
        ),
        "setting": (
            story_dimension_value(story, "setting") if story is not None else None,
            "VERIFIED_SETTING_CHANGED",
            story is not None,
        ),
        "responsible_agent_structure": (
            crime_psychology.get("responsible_agent_structure")
            if crime_psychology is not None
            else case_input.get("responsible_agent_structure")
            if case_input is not None
            else None,
            "VERIFIED_SUBJECT_ROLE_CHANGED",
            crime_psychology is not None or case_input is not None,
        ),
        "legal_outcome": (
            case_input.get("legal_outcome") if case_input is not None else None,
            "VERIFIED_LEGAL_OUTCOME_CHANGED",
            case_input is not None,
        ),
    }
    for dimension, contract_field in TRUTH_DIMENSION_FIELDS.items():
        expected = contract.get(contract_field)
        actual, error_code, target_available = targets[dimension]
        if (
            isinstance(expected, str)
            and target_available
            and truth_dimension_is_locked(contract, dimension)
            and actual != expected
        ):
            issues.append(
                truth_issue(
                    error_code,
                    "검증된 Source Truth Dimension이 생성 Story에서 변경되었습니다.",
                    "01_CASE/source_truth_contract.json",
                    {"dimension": dimension, "expected": expected, "actual": actual},
                )
            )
        if case_input is not None and dimension in {"incident_type", "setting"}:
            case_actual = case_input.get(dimension)
            if (
                isinstance(expected, str)
                and truth_dimension_is_locked(contract, dimension)
                and case_actual != expected
            ):
                issues.append(
                    truth_issue(
                        error_code,
                        "검증된 Source Truth Dimension이 Case Input에서 변경되었습니다.",
                        "01_CASE/case_input.json",
                        {"dimension": dimension, "expected": expected, "actual": case_actual},
                    )
                )
    unknown = contract.get("unknown_dimensions")
    if isinstance(unknown, list):
        for dimension in unknown:
            if not isinstance(dimension, str) or dimension not in targets:
                continue
            actual, _error_code, target_available = targets[dimension]
            case_actual = case_input.get(dimension) if case_input is not None else None
            if (target_available and actual not in (None, "", "UNKNOWN")) or case_actual not in (
                None,
                "",
                "UNKNOWN",
            ):
                issues.append(
                    truth_issue(
                        "UNKNOWN_PROMOTED_TO_FACT",
                        "Source에서 미상인 Dimension을 검증된 사실처럼 보충했습니다.",
                        "01_CASE/source_truth_contract.json",
                        {"dimension": dimension, "actual": actual, "case_actual": case_actual},
                    )
                )
    return issues


def character_subject_index(
    characters: Mapping[str, object],
) -> tuple[dict[str, str], set[str]]:
    """명시적 Source Subject ID를 Character ID로 색인한다."""
    raw_characters = characters.get("characters")
    if not isinstance(raw_characters, list):
        return {}, set()
    mapping: dict[str, str] = {}
    duplicated: set[str] = set()
    for character in raw_characters:
        if not isinstance(character, Mapping):
            continue
        source_subject_id = character.get("source_subject_id")
        character_id = character.get("character_id")
        if not isinstance(source_subject_id, str) or not isinstance(character_id, str):
            continue
        if source_subject_id in mapping:
            duplicated.add(source_subject_id)
        mapping[source_subject_id] = character_id
    return mapping, duplicated


def validate_source_subject_mapping(
    source_subjects: Mapping[str, object],
    characters: Mapping[str, object],
    clinical_labels: Mapping[str, object] | None,
) -> list[ValidationIssue]:
    """Source Subject와 Character 및 Clinical Label의 명시적 ID 연결을 검증한다."""
    issues: list[ValidationIssue] = []
    source_ids = set(records_by_id(source_subjects, "subjects", "source_subject_id"))
    subject_to_character, duplicated = character_subject_index(characters)
    unknown = sorted(set(subject_to_character) - source_ids)
    if unknown:
        issues.append(
            truth_issue(
                "SOURCE_SUBJECT_UNRESOLVED",
                "Character가 존재하지 않는 Source Subject를 참조합니다.",
                "02_CHARACTER/characters.json",
                {"source_subject_ids": unknown},
            )
        )
    if duplicated:
        issues.append(
            truth_issue(
                "SOURCE_SUBJECT_DUPLICATED",
                "하나의 Source Subject를 여러 Character에 연결할 수 없습니다.",
                "02_CHARACTER/characters.json",
                {"source_subject_ids": sorted(duplicated)},
            )
        )
    labels = clinical_labels.get("labels") if clinical_labels is not None else []
    if not isinstance(labels, list):
        return issues
    for label in labels:
        if not isinstance(label, Mapping):
            continue
        source_subject_id = label.get("source_subject_id")
        subject_id = label.get("subject_id")
        if isinstance(source_subject_id, str):
            mapped = subject_to_character.get(source_subject_id)
            if mapped is None:
                issues.append(
                    truth_issue(
                        "CLINICAL_SUBJECT_MAPPING_MISSING",
                        "Clinical Label의 Source Subject에 명시적 Character Mapping이 없습니다.",
                        "01_CASE/clinical_labels.json",
                        {"source_subject_id": source_subject_id},
                    )
                )
            elif duplicated and source_subject_id in duplicated:
                issues.append(
                    truth_issue(
                        "CLINICAL_SUBJECT_MAPPING_AMBIGUOUS",
                        "Clinical Label의 Source Subject가 여러 Character와 연결됩니다.",
                        "01_CASE/clinical_labels.json",
                        {"source_subject_id": source_subject_id},
                    )
                )
            elif isinstance(subject_id, str) and subject_id != mapped:
                issues.append(
                    truth_issue(
                        "CLINICAL_SUBJECT_MAPPING_AMBIGUOUS",
                        "Clinical Label의 Character ID가 명시적 Source Subject Mapping과 다릅니다.",
                        "01_CASE/clinical_labels.json",
                        {
                            "source_subject_id": source_subject_id,
                            "expected_subject_id": mapped,
                            "actual_subject_id": subject_id,
                        },
                    )
                )
        else:
            issues.append(
                truth_issue(
                    "CLINICAL_SUBJECT_MAPPING_MISSING",
                    "사실 기반 Clinical Label에는 Source Subject ID가 필요합니다.",
                    "01_CASE/clinical_labels.json",
                    {"subject_id": subject_id},
                )
            )
    return issues


def validate_truth_characters(
    contract: Mapping[str, object],
    source_subjects: Mapping[str, object],
    characters: Mapping[str, object],
    relationships: Mapping[str, object],
) -> list[ValidationIssue]:
    """검증된 Subject Role과 Relationship이 Character Layer에서 유지되는지 검증한다."""
    issues: list[ValidationIssue] = []
    source_records = records_by_id(source_subjects, "subjects", "source_subject_id")
    character_records = records_by_id(characters, "characters", "character_id")
    subject_to_character, duplicated = character_subject_index(characters)
    if duplicated:
        return issues
    if contract.get(
        "source_truth_classification"
    ) == "VERIFIED_TRUE_CASE" or truth_dimension_is_locked(contract, "subject_roles"):
        for source_subject_id, character_id in subject_to_character.items():
            source = source_records.get(source_subject_id)
            character = character_records.get(character_id)
            if (
                source is None
                or character is None
                or source.get("source_role") == character.get("role")
            ):
                continue
            issues.append(
                truth_issue(
                    "VERIFIED_SUBJECT_ROLE_CHANGED",
                    "검증된 Source Subject 역할이 Character에서 변경되었습니다.",
                    "02_CHARACTER/characters.json",
                    {
                        "source_subject_id": source_subject_id,
                        "expected": source.get("source_role"),
                        "actual": character.get("role"),
                    },
                )
            )
    if not (
        contract.get("source_truth_classification") == "VERIFIED_TRUE_CASE"
        or truth_dimension_is_locked(contract, "relationships")
    ):
        return issues
    raw_relationships = relationships.get("relationships")
    relationship_keys = (
        {
            (item.get("from"), item.get("to"), item.get("engine"))
            for item in raw_relationships
            if isinstance(item, Mapping)
        }
        if isinstance(raw_relationships, list)
        else set()
    )
    verified = contract.get("verified_relationships")
    if isinstance(verified, list):
        for relationship in verified:
            if not isinstance(relationship, Mapping):
                continue
            expected = (
                subject_to_character.get(str(relationship.get("from_source_subject_id"))),
                subject_to_character.get(str(relationship.get("to_source_subject_id"))),
                relationship.get("relationship_type"),
            )
            if None not in expected and expected in relationship_keys:
                continue
            issues.append(
                truth_issue(
                    "VERIFIED_RELATIONSHIP_CHANGED",
                    "검증된 Source Subject 관계가 Character Relationship에서 변경되었습니다.",
                    "02_CHARACTER/relationships.json",
                    {"expected": list(expected)},
                )
            )
    return issues


def validate_truth_events(
    contract: Mapping[str, object],
    verified_event_ledger: Mapping[str, object],
    characters: Mapping[str, object],
    actual_timeline: Mapping[str, object],
    causal_graph: Mapping[str, object],
) -> list[ValidationIssue]:
    """검증된 Event가 Timeline과 Causal Graph에서 동일 ID와 내용으로 유지되는지 검증한다."""
    if not (
        contract.get("source_truth_classification") == "VERIFIED_TRUE_CASE"
        or truth_dimension_is_locked(contract, "events")
    ):
        return []
    issues: list[ValidationIssue] = []
    verified = records_by_id(verified_event_ledger, "events", "verified_event_id")
    raw_events = actual_timeline.get("events")
    actual_by_source = (
        {
            str(event.get("source_event_id")): event
            for event in raw_events
            if isinstance(event, Mapping) and isinstance(event.get("source_event_id"), str)
        }
        if isinstance(raw_events, list)
        else {}
    )
    subject_to_character, _duplicated = character_subject_index(characters)
    causal_nodes = causal_graph.get("nodes")
    causal_source_ids = (
        {
            str(node.get("source_event_id"))
            for node in causal_nodes
            if isinstance(node, Mapping) and isinstance(node.get("source_event_id"), str)
        }
        if isinstance(causal_nodes, list)
        else set()
    )
    for event_id, source_event in verified.items():
        actual = actual_by_source.get(event_id)
        raw_participants = source_event.get("participant_source_subject_ids")
        participants_resolved = (
            all(
                isinstance(source_id, str) and source_id in subject_to_character
                for source_id in raw_participants
            )
            if isinstance(raw_participants, list)
            else False
        )
        expected_participants = (
            {
                subject_to_character[source_id]
                for source_id in raw_participants
                if isinstance(source_id, str) and source_id in subject_to_character
            }
            if isinstance(raw_participants, list)
            else set()
        )
        actual_participants = (
            set(actual.get("participant_ids", []))
            if actual is not None and isinstance(actual.get("participant_ids"), list)
            else set()
        )
        setting_matches = source_event.get("setting") in (
            None,
            actual.get("location_id") if actual is not None else None,
        )
        statement_matches = actual is not None and actual.get("description") == source_event.get(
            "statement"
        )
        participants_match = participants_resolved and expected_participants == actual_participants
        if actual is None or not setting_matches or not statement_matches or not participants_match:
            issues.append(
                truth_issue(
                    "VERIFIED_EVENT_CHANGED",
                    "검증된 Event가 Actual Timeline에서 변경되거나 누락되었습니다.",
                    "03_TIMELINE/actual_timeline.json",
                    {"verified_event_id": event_id},
                )
            )
        if event_id not in causal_source_ids:
            issues.append(
                truth_issue(
                    "VERIFIED_EVENT_CHANGED",
                    "검증된 Event가 Causal Graph에 연결되지 않았습니다.",
                    "04_MYSTERY/causal_graph.json",
                    {"verified_event_id": event_id},
                )
            )
    return issues

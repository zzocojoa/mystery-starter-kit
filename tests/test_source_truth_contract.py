"""Source Truth 구조 잠금과 임상 대상 명시적 Mapping 검증."""

from copy import deepcopy

from RUNTIME.core_tasks import resolved_clinical_labels_output
from VALIDATORS.source_truth_contract import (
    validate_source_subject_mapping,
    validate_truth_dimensions,
)


def verified_contract() -> dict[str, object]:
    """사기 사건과 병원 Setting을 잠근 Source Truth Contract를 만든다."""
    return {
        "project_id": "PRJ-900",
        "source_truth_classification": "VERIFIED_TRUE_CASE",
        "locked_dimensions": ["incident_type", "setting"],
        "verified_incident_type": "FRAUD",
        "verified_setting": "HOSPITAL",
        "verified_responsible_agent_structure": None,
        "verified_legal_outcome": None,
        "flexible_dimensions": [],
        "unknown_dimensions": ["responsible_agent_structure", "legal_outcome"],
    }


def story_with_dimensions(incident_type: str, setting: str) -> dict[str, object]:
    """Truth Dimension 검증용 Story DNA를 만든다."""
    return {
        "project_id": "PRJ-900",
        "story_dna": {"incident_type": incident_type, "setting": setting},
    }


def source_subjects() -> dict[str, object]:
    """순서와 무관한 Source Subject 두 명을 만든다."""
    return {
        "project_id": "PRJ-900",
        "subjects": [
            {"source_subject_id": "SUBJECT-01"},
            {"source_subject_id": "SUBJECT-02"},
        ],
    }


def mapped_characters() -> dict[str, object]:
    """Source Subject를 역순 Character 배열에 명시적으로 연결한다."""
    return {
        "project_id": "PRJ-900",
        "characters": [
            {
                "character_id": "CHAR-02",
                "source_subject_id": "SUBJECT-02",
                "name": "두 번째",
                "role": "WITNESS",
            },
            {
                "character_id": "CHAR-01",
                "source_subject_id": "SUBJECT-01",
                "name": "첫 번째",
                "role": "VICTIM",
            },
        ],
    }


def clinical_labels() -> dict[str, object]:
    """Source Subject와 Character ID를 함께 가진 Clinical Label을 만든다."""
    return {
        "project_id": "PRJ-900",
        "labels": [
            {
                "term": "임상 용어",
                "source_subject_id": "SUBJECT-01",
                "subject_id": "CHAR-01",
                "classification": "EXPERT_ASSESSMENT",
                "source_claim_ids": ["FACT-01"],
                "qualified_expert": True,
                "documented_assessment": True,
            }
        ],
    }


def test_verified_fraud_cannot_be_changed_to_kidnapping() -> None:
    """검증된 사기 사건을 납치 사건으로 바꾼 Candidate 투영은 실패한다."""
    issues = validate_truth_dimensions(
        verified_contract(),
        story_with_dimensions("KIDNAPPING", "HOSPITAL"),
        {"incident_type": "KIDNAPPING", "setting": "HOSPITAL"},
        None,
    )
    assert "VERIFIED_INCIDENT_CHANGED" in {issue["code"] for issue in issues}


def test_verified_setting_change_fails() -> None:
    """검증된 Setting 변경은 Story와 Case 양쪽에서 실패한다."""
    issues = validate_truth_dimensions(
        verified_contract(),
        story_with_dimensions("FRAUD", "OFFICE"),
        {"incident_type": "FRAUD", "setting": "OFFICE"},
        None,
    )
    assert "VERIFIED_SETTING_CHANGED" in {issue["code"] for issue in issues}


def test_character_reordering_preserves_clinical_subject_mapping() -> None:
    """Character 배열 순서를 바꿔도 Source Subject ID Mapping은 유지된다."""
    characters = mapped_characters()
    labels = clinical_labels()

    assert validate_source_subject_mapping(source_subjects(), characters, labels) == []
    resolved = resolved_clinical_labels_output(labels, characters)
    resolved_labels = resolved["labels"]
    assert isinstance(resolved_labels, list)
    assert resolved_labels[0]["subject_id"] == "CHAR-01"

    reordered = deepcopy(characters)
    reordered_records = reordered["characters"]
    assert isinstance(reordered_records, list)
    reordered_records.reverse()
    assert validate_source_subject_mapping(source_subjects(), reordered, labels) == []
    assert resolved_clinical_labels_output(labels, reordered) == resolved


def test_subject_suffix_or_character_position_is_not_a_mapping() -> None:
    """SUBJECT 번호와 Character 배열 위치만 같은 암묵 Mapping은 실패한다."""
    characters = mapped_characters()
    records = characters["characters"]
    assert isinstance(records, list)
    for record in records:
        assert isinstance(record, dict)
        record.pop("source_subject_id")

    issues = validate_source_subject_mapping(
        source_subjects(),
        characters,
        clinical_labels(),
    )
    assert "CLINICAL_SUBJECT_MAPPING_MISSING" in {issue["code"] for issue in issues}


def test_conflicting_explicit_clinical_subject_id_fails() -> None:
    """Source Subject Mapping과 다른 Character ID를 Label에 기록할 수 없다."""
    labels = clinical_labels()
    label_records = labels["labels"]
    assert isinstance(label_records, list)
    label = label_records[0]
    assert isinstance(label, dict)
    label["subject_id"] = "CHAR-02"

    issues = validate_source_subject_mapping(
        source_subjects(),
        mapped_characters(),
        labels,
    )
    assert "CLINICAL_SUBJECT_MAPPING_AMBIGUOUS" in {issue["code"] for issue in issues}

"""Source Truth 구조 잠금과 임상 대상 명시적 Mapping 검증."""

from copy import deepcopy

from RUNTIME.core_tasks import resolved_clinical_labels_output
from VALIDATORS.models import ValidationIssue
from VALIDATORS.source_truth_contract import (
    bind_source_truth_contract,
    validate_source_subject_mapping,
    validate_source_truth_contract_integrity,
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


def source_truth_bundle() -> dict[str, dict[str, object]]:
    """정상 Source Truth Bundle과 결속된 Contract를 만든다."""
    artifacts: dict[str, dict[str, object]] = {
        "sources": {
            "project_id": "PRJ-900",
            "sources": [{"source_id": "SRC-01"}],
        },
        "claim_evidence": {
            "project_id": "PRJ-900",
            "claims": [{"fact_id": "FACT-01", "classification": "FACT"}],
        },
        "verified_fact_ledger": {
            "project_id": "PRJ-900",
            "facts": [{"fact_id": "FACT-01"}],
        },
        "source_subjects": {
            "project_id": "PRJ-900",
            "subjects": [
                {
                    "source_subject_id": "SUBJECT-01",
                    "related_fact_ids": ["FACT-01"],
                }
            ],
        },
        "verified_event_ledger": {
            "project_id": "PRJ-900",
            "events": [
                {
                    "verified_event_id": "VEVT-01",
                    "sequence": 1,
                    "participant_source_subject_ids": ["SUBJECT-01"],
                    "source_claim_ids": ["FACT-01"],
                }
            ],
        },
    }
    artifacts["source_truth_contract"] = bind_source_truth_contract(
        {
            "project_id": "PRJ-900",
            "source_truth_classification": "VERIFIED_TRUE_CASE",
            "locked_dimensions": ["incident_type"],
            "verified_subject_ids": ["SUBJECT-01"],
            "verified_event_ids": ["VEVT-01"],
            "verified_relationships": [],
            "verified_incident_type": "FRAUD",
            "verified_setting": None,
            "verified_responsible_agent_structure": None,
            "verified_legal_outcome": None,
            "flexible_dimensions": [],
            "unknown_dimensions": [],
            "source_claim_ids": ["FACT-01"],
        },
        artifacts,
    )
    return artifacts


def bundle_issues(
    artifacts: dict[str, dict[str, object]],
) -> list[ValidationIssue]:
    """Test Bundle을 무결성 Validator 인자 순서로 전달한다."""
    return validate_source_truth_contract_integrity(
        artifacts.get("source_truth_contract"),
        artifacts.get("sources"),
        artifacts.get("claim_evidence"),
        artifacts.get("verified_fact_ledger"),
        artifacts.get("source_subjects"),
        artifacts.get("verified_event_ledger"),
    )


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


def test_normal_source_truth_bundle_passes() -> None:
    """정상 Evidence Bundle은 개별 Hash와 Bundle Hash를 모두 통과한다."""
    assert bundle_issues(source_truth_bundle()) == []


def test_claim_evidence_change_breaks_bundle_hash() -> None:
    """Claim Evidence 변경은 결속 Artifact Hash에서 실패한다."""
    artifacts = source_truth_bundle()
    claims = artifacts["claim_evidence"]["claims"]
    assert isinstance(claims, list)
    claims.append({"fact_id": "FACT-02", "classification": "DRAMATIZATION"})
    codes = {issue["code"] for issue in bundle_issues(artifacts)}
    assert "SOURCE_TRUTH_BOUND_ARTIFACT_HASH_MISMATCH" in codes
    assert "SOURCE_TRUTH_BUNDLE_HASH_MISMATCH" in codes


def test_source_subject_change_breaks_bundle_hash() -> None:
    """Source Subject 변경은 결속 Artifact Hash에서 실패한다."""
    artifacts = source_truth_bundle()
    subjects = artifacts["source_subjects"]["subjects"]
    assert isinstance(subjects, list)
    subject = subjects[0]
    assert isinstance(subject, dict)
    subject["pseudonym"] = "변경된 이름"
    assert "SOURCE_TRUTH_BOUND_ARTIFACT_HASH_MISMATCH" in {
        issue["code"] for issue in bundle_issues(artifacts)
    }


def test_verified_event_change_breaks_bundle_hash() -> None:
    """Verified Event 변경은 결속 Artifact Hash에서 실패한다."""
    artifacts = source_truth_bundle()
    events = artifacts["verified_event_ledger"]["events"]
    assert isinstance(events, list)
    event = events[0]
    assert isinstance(event, dict)
    event["sequence"] = 2
    assert "SOURCE_TRUTH_BOUND_ARTIFACT_HASH_MISMATCH" in {
        issue["code"] for issue in bundle_issues(artifacts)
    }


def test_missing_source_truth_artifact_fails_closed() -> None:
    """Evidence Artifact 누락은 Bundle 불완전 오류로 실패한다."""
    artifacts = source_truth_bundle()
    del artifacts["verified_fact_ledger"]
    assert "SOURCE_TRUTH_BUNDLE_INCOMPLETE" in {
        issue["code"] for issue in bundle_issues(artifacts)
    }

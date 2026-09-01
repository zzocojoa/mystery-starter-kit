"""승인 Candidate의 전 Dimension 하위 Artifact 투영 검증."""

from pathlib import Path

from VALIDATORS.candidate_projection import (
    validate_approved_candidate_projection,
    validate_final_story_constraints,
    validate_projection_contract_coverage,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def projection_contract() -> dict[str, object]:
    """저장소 Candidate Projection Contract를 읽는다."""
    return load_json_object(ROOT / "STANDARD" / "candidate_projection_contract.json")


def approved_variation(selection: dict[str, str]) -> dict[str, object]:
    """하나의 승인 Selection을 가진 Variation 문서를 만든다."""
    return {
        "approved_candidate_id": "VAR-01",
        "candidates": [
            {
                "candidate_id": "VAR-01",
                "selection": selection,
            }
        ],
    }


def v2_config() -> dict[str, object]:
    """Candidate Genre가 고정된 v2 Config를 만든다."""
    return {
        "variation_engine_version": "2.0.0",
        "genre": "CRIME_PSYCHOLOGICAL_THRILLER",
    }


def test_candidate_projection_contract_passes_its_schema() -> None:
    """Projection 분류와 Target 구조는 자체 Schema를 통과해야 한다."""
    contract_path = ROOT / "STANDARD" / "candidate_projection_contract.json"
    schema_path = ROOT / "STANDARD" / "schemas" / "candidate_projection_contract.schema.json"

    assert (
        collect_schema_errors(
            load_json_object(contract_path),
            load_json_object(schema_path),
            str(contract_path),
        )
        == []
    )


def test_approved_trusted_domain_change_fails() -> None:
    """승인 Candidate의 Trusted Domain을 Crime Psychology가 바꾸면 실패한다."""
    issues = validate_approved_candidate_projection(
        v2_config(),
        approved_variation({"trusted_domain": "WORKPLACE"}),
        projection_contract(),
        {"crime_psychology": {"trusted_domain": "FAMILY"}},
    )
    assert "APPROVED_CANDIDATE_PROJECTION_MISMATCH" in {issue["code"] for issue in issues}


def test_responsible_agent_projection_uses_engine_specific_target() -> None:
    """2.0은 Crime Psychology를, 2.1은 Crime Event Contract를 Target으로 사용한다."""
    legacy_issues = validate_approved_candidate_projection(
        v2_config(),
        approved_variation({"responsible_agent_structure": "SINGLE_AGENT"}),
        projection_contract(),
        {"crime_psychology": {"responsible_agent_structure": "SINGLE_AGENT"}},
    )
    explicit_issues = validate_approved_candidate_projection(
        {"variation_engine_version": "2.1.0", "genre": "CRIME_EVENT_THRILLER"},
        approved_variation({"responsible_agent_structure": "DUAL_AGENTS"}),
        projection_contract(),
        {"crime_event_contract": {"responsible_agent_structure": "DUAL_AGENTS"}},
    )
    assert legacy_issues == []
    assert explicit_issues == []


def test_approved_final_proof_change_fails() -> None:
    """승인 Candidate의 Final Proof Mechanism을 Clue가 바꾸면 실패한다."""
    issues = validate_approved_candidate_projection(
        v2_config(),
        approved_variation({"final_proof_mechanism": "RELATIONAL_CONVERGENCE"}),
        projection_contract(),
        {"clue_matrix": {"final_proof_mechanism": "MACHINE_LOG"}},
    )
    assert "APPROVED_CANDIDATE_PROJECTION_MISMATCH" in {issue["code"] for issue in issues}


def test_final_story_cannot_bypass_project_constraint() -> None:
    """Candidate에서 통과한 Constraint를 최종 Story가 우회하면 실패한다."""
    constraints = {
        "must_use": [
            {
                "field": "incident_type",
                "operator": "IN",
                "values": ["FRAUD"],
            }
        ],
        "must_not_use": [],
    }
    variations = approved_variation({"incident_type": "FRAUD"})
    artifacts = {
        "story_dna": {"story_dna": {"incident_type": "KIDNAPPING"}},
        "case_input": {"incident_type": "KIDNAPPING"},
    }

    issues = validate_final_story_constraints(
        constraints,
        variations,
        projection_contract(),
        artifacts,
    )
    assert "PROJECT_CONSTRAINT_FINAL_ARTIFACT_MISMATCH" in {issue["code"] for issue in issues}


def test_final_story_rechecks_location_and_character_limits() -> None:
    """Candidate 이후 최종 Story가 제작 수량 상한을 우회하면 실패한다."""
    constraints = {
        "must_use": [],
        "must_not_use": [],
        "production_limits": {
            "max_locations": 1,
            "max_major_characters": 1,
        },
    }
    artifacts = {
        "actual_timeline": {
            "events": [
                {"location_id": "OFFICE"},
                {"location_id": "MARKET"},
            ]
        },
        "characters": {
            "characters": [
                {"character_id": "CHAR-01"},
                {"character_id": "CHAR-02"},
            ]
        },
    }

    issues = validate_final_story_constraints(
        constraints,
        approved_variation({"incident_type": "FRAUD"}),
        projection_contract(),
        artifacts,
    )
    mismatched_dimensions = {
        issue["context"].get("dimension")
        for issue in issues
        if issue["code"] == "PROJECT_CONSTRAINT_FINAL_ARTIFACT_MISMATCH"
    }
    assert mismatched_dimensions == {"location_count", "major_character_count"}


def test_catalog_dimension_without_projection_classification_fails() -> None:
    """새 Catalog Dimension을 Mapping 없이 추가하면 Fail-closed로 차단한다."""
    catalog = {"dimensions": {"mystery_type": ["WHO"], "new_dimension": ["VALUE"]}}
    issues = validate_projection_contract_coverage(catalog, projection_contract())
    assert "CANDIDATE_DIMENSION_UNMAPPED" in {issue["code"] for issue in issues}


def test_approved_unknown_dimension_fails() -> None:
    """승인 Selection의 알 수 없는 Dimension은 조용히 무시하지 않는다."""
    issues = validate_approved_candidate_projection(
        v2_config(),
        approved_variation({"new_dimension": "VALUE"}),
        projection_contract(),
        {},
    )
    assert "CANDIDATE_DIMENSION_UNMAPPED" in {issue["code"] for issue in issues}

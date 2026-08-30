"""다축 Story Variation 후보 생성 검증."""

from copy import deepcopy
from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation import (
    apply_user_case_constraints,
    approve_variation_candidate,
    generate_variation_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "STANDARD" / "variation_catalog.json"
CATALOG_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "variation_catalog.schema.json"
CANDIDATES_SCHEMA_PATH = (
    ROOT / "STANDARD" / "schemas" / "variation_candidates.schema.json"
)
STORY_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "story_dna.schema.json"
STORY_EXAMPLE_PATH = ROOT / "EXAMPLES" / "story_dna.example.json"


def test_variation_catalog_passes_schema() -> None:
    """Variation Catalog은 자체 Schema를 통과해야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    schema = load_json_object(CATALOG_SCHEMA_PATH)

    assert collect_schema_errors(catalog, schema, str(CATALOG_PATH)) == []


def test_catalog_primary_twists_pass_story_dna_schema() -> None:
    """Catalog의 모든 Primary Twist는 Story DNA의 Canonical ID여야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    dimensions = catalog.get("dimensions")
    assert isinstance(dimensions, dict)
    primary_twists = dimensions.get("primary_twist")
    assert isinstance(primary_twists, list)
    story_schema = load_json_object(STORY_SCHEMA_PATH)
    story_example = load_json_object(STORY_EXAMPLE_PATH)

    for primary_twist in primary_twists:
        story_document = deepcopy(story_example)
        story_dna = story_document.get("story_dna")
        assert isinstance(story_dna, dict)
        story_dna["primary_twist"] = primary_twist
        assert collect_schema_errors(
            story_document,
            story_schema,
            f"story_dna.primary_twist={primary_twist}",
        ) == []


def test_generator_returns_reproducible_distinct_candidates() -> None:
    """같은 Seed는 동일하고 후보끼리는 다른 다축 조합을 생성해야 한다."""
    catalog = load_json_object(CATALOG_PATH)

    first = generate_variation_candidates(
        "PRJ-001", "폐쇄된 관제실", 5, catalog, "ORIGINAL_FICTION"
    )
    second = generate_variation_candidates(
        "PRJ-001", "폐쇄된 관제실", 5, catalog, "ORIGINAL_FICTION"
    )

    assert first == second
    candidates = first["candidates"]
    assert isinstance(candidates, list)
    signatures = {candidate["signature"] for candidate in candidates}
    assert len(candidates) == len(signatures) == 5
    schema = load_json_object(CANDIDATES_SCHEMA_PATH)
    assert collect_schema_errors(first, schema, "variation_candidates") == []


def test_first_candidate_signature_changes_with_seed() -> None:
    """VAR-01도 고정 특례 없이 Seed 변화에 반응해야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    first = generate_variation_candidates(
        "PRJ-001", "첫 번째 구조 Seed", 5, catalog, "ORIGINAL_FICTION"
    )
    second = generate_variation_candidates(
        "PRJ-001", "완전히 다른 구조 Seed", 5, catalog, "ORIGINAL_FICTION"
    )
    first_candidates = first["candidates"]
    second_candidates = second["candidates"]
    assert isinstance(first_candidates, list)
    assert isinstance(second_candidates, list)
    assert first_candidates[0]["signature"] != second_candidates[0]["signature"]


def test_generator_without_channel_context_does_not_apply_v2_safe_values() -> None:
    """Channel Context가 없는 Generator에는 v2 안전 목록을 전역 적용하지 않는다."""
    catalog = load_json_object(CATALOG_PATH)
    generated = generate_variation_candidates(
        "PRJ-004", "open-city-seed", 5, catalog, "ORIGINAL_FICTION"
    )
    dimensions = catalog.get("dimensions")
    candidates = generated.get("candidates")
    assert isinstance(dimensions, dict)
    assert isinstance(candidates, list)

    for dimension, choices in dimensions.items():
        assert isinstance(dimension, str)
        assert isinstance(choices, list)
        selected = {
            candidate["selection"][dimension]
            for candidate in candidates
        }
        assert selected <= set(choices), dimension
    threat_values = {
        candidate["selection"]["threat_type"] for candidate in candidates
    }
    assert "NO_CRIME" in threat_values


def test_generator_rejects_too_few_candidates() -> None:
    """비교가 불가능한 2개 이하 후보 요청은 명시적으로 실패해야 한다."""
    catalog = load_json_object(CATALOG_PATH)

    with pytest.raises(ConfigurationError, match="3개 이상"):
        generate_variation_candidates(
            "PRJ-001", "seed", 2, catalog, "ORIGINAL_FICTION"
        )


def test_approval_marks_exactly_one_candidate_without_mutating_input() -> None:
    """후보 승인은 입력을 바꾸지 않고 정확히 하나만 APPROVED로 표시해야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    candidates = generate_variation_candidates(
        "PRJ-001", "seed", 5, catalog, "ORIGINAL_FICTION"
    )

    approved = approve_variation_candidate(candidates, "VAR-03")

    records = approved["candidates"]
    assert isinstance(records, list)
    approved_ids = [
        record["candidate_id"]
        for record in records
        if record["selection_status"] == "APPROVED"
    ]
    assert approved_ids == ["VAR-03"]
    assert candidates["approved_candidate_id"] is None


def test_user_case_locked_dimensions_are_applied_without_mutating_candidates() -> None:
    """LOCKED 사용자 입력은 모든 후보에 적용하고 원본 후보는 변경하지 않아야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    candidates = generate_variation_candidates(
        "PRJ-001", "seed", 5, catalog, "ORIGINAL_FICTION"
    )
    production_config = {
        "story_source_mode": "USER_CASE",
        "user_case_constraints": [
            {"field": "protagonist_role", "value": "REPORTER", "status": "LOCKED"},
            {"field": "incident_type", "value": "DISAPPEARANCE", "status": "LOCKED"},
            {"field": "setting", "value": "FACTORY", "status": "FLEXIBLE"},
            {"field": "primary_twist", "value": None, "status": "UNKNOWN"},
        ],
    }

    constrained = apply_user_case_constraints(candidates, production_config)
    records = constrained.get("candidates")
    original_records = candidates.get("candidates")
    assert isinstance(records, list)
    assert isinstance(original_records, list)

    assert all(
        isinstance(record, dict)
        and isinstance(record.get("selection"), dict)
        and record["selection"]["protagonist_role"] == "REPORTER"
        and record["selection"]["incident_type"] == "DISAPPEARANCE"
        for record in records
    )
    assert any(
        isinstance(record, dict)
        and isinstance(record.get("selection"), dict)
        and record["selection"]["protagonist_role"] != "REPORTER"
        for record in original_records
    )

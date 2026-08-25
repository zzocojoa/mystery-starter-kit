"""다축 Story Variation 후보 생성 검증."""

from pathlib import Path

import pytest

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.variation import approve_variation_candidate, generate_variation_candidates

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "STANDARD" / "variation_catalog.json"
CATALOG_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "variation_catalog.schema.json"
CANDIDATES_SCHEMA_PATH = (
    ROOT / "STANDARD" / "schemas" / "variation_candidates.schema.json"
)


def test_variation_catalog_passes_schema() -> None:
    """Variation Catalog은 자체 Schema를 통과해야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    schema = load_json_object(CATALOG_SCHEMA_PATH)

    assert collect_schema_errors(catalog, schema, str(CATALOG_PATH)) == []


def test_generator_returns_reproducible_distinct_candidates() -> None:
    """같은 Seed는 동일하고 후보끼리는 다른 다축 조합을 생성해야 한다."""
    catalog = load_json_object(CATALOG_PATH)

    first = generate_variation_candidates("PRJ-001", "폐쇄된 관제실", 5, catalog)
    second = generate_variation_candidates("PRJ-001", "폐쇄된 관제실", 5, catalog)

    assert first == second
    candidates = first["candidates"]
    assert isinstance(candidates, list)
    signatures = {candidate["signature"] for candidate in candidates}
    assert len(candidates) == len(signatures) == 5
    schema = load_json_object(CANDIDATES_SCHEMA_PATH)
    assert collect_schema_errors(first, schema, "variation_candidates") == []


def test_generator_rejects_too_few_candidates() -> None:
    """비교가 불가능한 2개 이하 후보 요청은 명시적으로 실패해야 한다."""
    catalog = load_json_object(CATALOG_PATH)

    with pytest.raises(ConfigurationError, match="3개 이상"):
        generate_variation_candidates("PRJ-001", "seed", 2, catalog)


def test_approval_marks_exactly_one_candidate_without_mutating_input() -> None:
    """후보 승인은 입력을 바꾸지 않고 정확히 하나만 APPROVED로 표시해야 한다."""
    catalog = load_json_object(CATALOG_PATH)
    candidates = generate_variation_candidates("PRJ-001", "seed", 5, catalog)

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

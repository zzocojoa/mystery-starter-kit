"""True Story Fact Integrity 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.fact_validation import validate_fact_integrity
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def make_fact_artifacts() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """근거가 연결된 Fact, Inference, Dramatization Artifact를 만든다."""
    facts: dict[str, object] = {
        "facts": [
            {
                "fact_id": "FACT-01",
                "classification": "FACT",
                "source_ids": ["SRC-01"],
            },
            {
                "fact_id": "FACT-02",
                "classification": "INFERENCE",
                "basis_fact_ids": ["FACT-01"],
            },
            {
                "fact_id": "FACT-03",
                "classification": "DRAMATIZATION",
                "presented_as_fact": False,
            },
        ]
    }
    sources: dict[str, object] = {
        "sources": [{"source_id": "SRC-01", "url": "https://example.com/source"}]
    }
    claims: dict[str, object] = {
        "claims": [{"fact_id": "FACT-01", "evidence_source_ids": ["SRC-01"]}]
    }
    return facts, sources, claims


def test_complete_fact_evidence_chain_passes() -> None:
    """Fact, Inference, Dramatization 경계와 Evidence가 완전하면 통과해야 한다."""
    facts, sources, claims = make_fact_artifacts()

    assert validate_fact_integrity("TRUE_STORY", facts, sources, claims) == []


def test_fact_evidence_bundle_passes_schema() -> None:
    """완전한 Fact-Evidence 묶음은 구조 Contract를 통과해야 한다."""
    facts, sources, claims = make_fact_artifacts()
    bundle = {
        "facts": facts["facts"],
        "sources": sources["sources"],
        "claims": claims["claims"],
    }
    schema = load_json_object(
        ROOT / "STANDARD" / "schemas" / "fact_evidence.schema.json"
    )

    assert collect_schema_errors(bundle, schema, "fact_evidence") == []


def test_original_story_does_not_require_external_evidence() -> None:
    """Original Fiction에는 외부 Source Ledger를 강제하지 않아야 한다."""
    assert validate_fact_integrity(
        "ORIGINAL",
        {"facts": []},
        {"sources": []},
        {"claims": []},
    ) == []


def test_missing_evidence_and_disguised_dramatization_fail() -> None:
    """Source 누락과 Fact로 위장한 Dramatization을 모두 차단해야 한다."""
    facts, sources, claims = make_fact_artifacts()
    changed_facts = deepcopy(facts)
    fact_records = changed_facts["facts"]
    assert isinstance(fact_records, list)
    factual = fact_records[0]
    dramatization = fact_records[2]
    assert isinstance(factual, dict)
    assert isinstance(dramatization, dict)
    factual["source_ids"] = ["SRC-404"]
    dramatization["presented_as_fact"] = True

    issues = validate_fact_integrity("TRUE_STORY", changed_facts, sources, claims)
    codes = {issue["code"] for issue in issues}

    assert "FACT_EVIDENCE_MISSING" in codes
    assert "DRAMATIZATION_PRESENTED_AS_FACT" in codes

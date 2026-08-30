"""True Story Fact Integrity 검증."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from VALIDATORS.fact_validation import validate_fact_integrity
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]


def statement_hash(statement: str) -> str:
    """정규화된 Test Fact Hash를 반환한다."""
    return sha256(" ".join(statement.split()).casefold().encode()).hexdigest()


def make_fact_artifacts() -> tuple[
    dict[str, object], dict[str, object], dict[str, object], dict[str, object]
]:
    """근거가 연결된 Fact, Inference, Dramatization Artifact를 만든다."""
    facts: dict[str, object] = {
        "facts": [
            {
                "fact_id": "FACT-01",
                "statement": "확인된 사실이다.",
                "classification": "FACT",
                "normalized_statement_hash": statement_hash("확인된 사실이다."),
                "source_ids": ["SRC-01"],
            },
            {
                "fact_id": "FACT-02",
                "statement": "사실에서 추론했다.",
                "classification": "INFERENCE",
                "normalized_statement_hash": statement_hash("사실에서 추론했다."),
                "basis_fact_ids": ["FACT-01"],
            },
            {
                "fact_id": "FACT-03",
                "statement": "장면을 재구성했다.",
                "classification": "DRAMATIZATION",
                "normalized_statement_hash": statement_hash("장면을 재구성했다."),
                "presented_as_fact": False,
            },
        ]
    }
    sources: dict[str, object] = {
        "sources": [{"source_id": "SRC-01", "url": "https://example.com/source"}]
    }
    claims: dict[str, object] = {
        "claims": [{
            "fact_id": "FACT-01",
            "claim": "확인된 사실이다.",
            "classification": "FACT",
            "canonical_claim_hash": statement_hash("확인된 사실이다."),
            "evidence_source_ids": ["SRC-01"],
            "basis_fact_ids": [],
            "evidence_scope": "공식 기록",
            "confidence": "HIGH",
            "presented_as_fact": True,
        }]
    }
    fact_records = facts["facts"]
    assert isinstance(fact_records, list)
    ledger: dict[str, object] = {"facts": [deepcopy(fact_records[0])]}
    return facts, sources, claims, ledger


def test_complete_fact_evidence_chain_passes() -> None:
    """Fact, Inference, Dramatization 경계와 Evidence가 완전하면 통과해야 한다."""
    facts, sources, claims, ledger = make_fact_artifacts()

    assert validate_fact_integrity(
        "VERIFIED_TRUE_CASE", facts, sources, claims, ledger
    ) == []


def test_fact_evidence_bundle_passes_schema() -> None:
    """완전한 Fact-Evidence 묶음은 구조 Contract를 통과해야 한다."""
    facts, sources, claims, _ledger = make_fact_artifacts()
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
        "ORIGINAL_FICTION",
        {"facts": []},
        {"sources": []},
        {"claims": []},
        {"facts": []},
    ) == []


def test_missing_evidence_and_disguised_dramatization_fail() -> None:
    """Source 누락과 Fact로 위장한 Dramatization을 모두 차단해야 한다."""
    facts, sources, claims, ledger = make_fact_artifacts()
    changed_facts = deepcopy(facts)
    fact_records = changed_facts["facts"]
    assert isinstance(fact_records, list)
    factual = fact_records[0]
    dramatization = fact_records[2]
    assert isinstance(factual, dict)
    assert isinstance(dramatization, dict)
    factual["source_ids"] = ["SRC-404"]
    dramatization["presented_as_fact"] = True

    issues = validate_fact_integrity(
        "VERIFIED_TRUE_CASE", changed_facts, sources, claims, ledger
    )
    codes = {issue["code"] for issue in issues}

    assert "FACT_EVIDENCE_MISSING" in codes
    assert "DRAMATIZATION_PRESENTED_AS_FACT" in codes


def test_fact_claim_classification_mismatch_fails() -> None:
    """같은 Fact ID의 Claim 분류가 다르면 의미 무결성 검증이 실패해야 한다."""
    facts, sources, claims, ledger = make_fact_artifacts()
    claim_records = claims["claims"]
    assert isinstance(claim_records, list)
    claim = claim_records[0]
    assert isinstance(claim, dict)
    claim["classification"] = "INFERENCE"
    claim["basis_fact_ids"] = ["FACT-01"]

    issues = validate_fact_integrity(
        "VERIFIED_TRUE_CASE", facts, sources, claims, ledger
    )
    assert "FACT_CLAIM_CLASSIFICATION_MISMATCH" in {
        issue["code"] for issue in issues
    }


def test_dramatization_without_source_passes() -> None:
    """Fact로 표시하지 않은 Dramatization에는 외부 Source를 강제하지 않는다."""
    facts, sources, claims, ledger = make_fact_artifacts()
    fact_records = facts["facts"]
    assert isinstance(fact_records, list)
    dramatization = fact_records[2]
    assert isinstance(dramatization, dict)
    assert "source_ids" not in dramatization
    assert validate_fact_integrity(
        "VERIFIED_TRUE_CASE", facts, sources, claims, ledger
    ) == []

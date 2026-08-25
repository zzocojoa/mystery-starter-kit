"""True Story의 Fact, Inference, Dramatization 경계 검증."""

from collections.abc import Mapping

from VALIDATORS.continuity import require_records, require_string, require_string_array
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue

FACT_BASED_MODES = {"TRUE_STORY", "INSPIRED_BY_TRUE_EVENTS"}


def make_fact_issue(
    code: str,
    message: str,
    artifact: str,
    context: dict[str, object],
) -> ValidationIssue:
    """Fact Integrity 문제를 표준 형식으로 생성한다."""
    return ValidationIssue(
        severity="ERROR",
        code=code,
        message=message,
        artifact=artifact,
        context=context,
    )


def record_ids(
    document: Mapping[str, object],
    records_key: str,
    id_key: str,
    source: str,
) -> set[str]:
    """중복 없는 Record ID 집합을 만든다."""
    records = require_records(document, records_key, source)
    identifiers = {
        require_string(record, id_key, source)
        for record in records
    }
    if len(identifiers) != len(records):
        raise ConfigurationError(f"중복 ID가 있습니다: source={source}, field={id_key}")
    return identifiers


def validate_fact_integrity(
    story_source_mode: object,
    facts_document: Mapping[str, object],
    sources_document: Mapping[str, object],
    claims_document: Mapping[str, object],
) -> list[ValidationIssue]:
    """사실 기반 Mode에서 근거와 각색 표시가 분리되어 있는지 검사한다."""
    if story_source_mode not in FACT_BASED_MODES:
        return []
    source_ids = record_ids(sources_document, "sources", "source_id", "sources")
    fact_records = require_records(facts_document, "facts", "facts")
    fact_ids = record_ids(facts_document, "facts", "fact_id", "facts")
    issues: list[ValidationIssue] = []
    factual_ids: set[str] = set()

    for fact in fact_records:
        fact_id = require_string(fact, "fact_id", "facts")
        classification = require_string(fact, "classification", fact_id)
        if classification == "FACT":
            factual_ids.add(fact_id)
            referenced_sources = require_string_array(fact, "source_ids", fact_id)
            unknown_sources = sorted(set(referenced_sources) - source_ids)
            if not referenced_sources or unknown_sources:
                issues.append(
                    make_fact_issue(
                        "FACT_EVIDENCE_MISSING",
                        "FACT에는 존재하는 Source가 하나 이상 연결되어야 합니다.",
                        "01_CASE/facts.json",
                        {"fact_id": fact_id, "unknown_source_ids": unknown_sources},
                    )
                )
        elif classification == "INFERENCE":
            basis_ids = require_string_array(fact, "basis_fact_ids", fact_id)
            unknown_facts = sorted(set(basis_ids) - fact_ids)
            if not basis_ids or unknown_facts:
                issues.append(
                    make_fact_issue(
                        "INFERENCE_BASIS_MISSING",
                        "INFERENCE에는 존재하는 근거 Fact가 하나 이상 필요합니다.",
                        "01_CASE/facts.json",
                        {"fact_id": fact_id, "unknown_fact_ids": unknown_facts},
                    )
                )
        elif classification == "DRAMATIZATION":
            if fact.get("presented_as_fact") is True:
                issues.append(
                    make_fact_issue(
                        "DRAMATIZATION_PRESENTED_AS_FACT",
                        "DRAMATIZATION을 검증된 FACT로 표시할 수 없습니다.",
                        "01_CASE/facts.json",
                        {"fact_id": fact_id},
                    )
                )
        else:
            issues.append(
                make_fact_issue(
                    "FACT_CLASSIFICATION_INVALID",
                    "Fact 분류는 FACT, INFERENCE, DRAMATIZATION 중 하나여야 합니다.",
                    "01_CASE/facts.json",
                    {"fact_id": fact_id, "classification": classification},
                )
            )

    covered_fact_ids: set[str] = set()
    for claim in require_records(claims_document, "claims", "claim_evidence"):
        fact_id = require_string(claim, "fact_id", "claim_evidence.claims")
        evidence_ids = require_string_array(
            claim,
            "evidence_source_ids",
            "claim_evidence.claims",
        )
        if fact_id not in fact_ids:
            issues.append(
                make_fact_issue(
                    "CLAIM_FACT_REFERENCE_BROKEN",
                    "Claim-Evidence가 존재하지 않는 Fact를 참조합니다.",
                    "01_CASE/claim_evidence.json",
                    {"fact_id": fact_id},
                )
            )
        unknown_sources = sorted(set(evidence_ids) - source_ids)
        if unknown_sources:
            issues.append(
                make_fact_issue(
                    "CLAIM_SOURCE_REFERENCE_BROKEN",
                    "Claim-Evidence가 존재하지 않는 Source를 참조합니다.",
                    "01_CASE/claim_evidence.json",
                    {"fact_id": fact_id, "unknown_source_ids": unknown_sources},
                )
            )
        if fact_id in factual_ids and evidence_ids:
            covered_fact_ids.add(fact_id)

    uncovered = sorted(factual_ids - covered_fact_ids)
    if uncovered:
        issues.append(
            make_fact_issue(
                "FACT_CLAIM_COVERAGE_MISSING",
                "검증된 FACT가 Claim-Evidence Ledger에 포함되지 않았습니다.",
                "01_CASE/claim_evidence.json",
                {"fact_ids": uncovered},
            )
        )
    return issues

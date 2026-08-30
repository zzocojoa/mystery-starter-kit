"""True Story의 Fact, Inference, Dramatization 경계 검증."""

from collections.abc import Mapping
from hashlib import sha256

from VALIDATORS.continuity import require_records, require_string, require_string_array
from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ValidationIssue
from VALIDATORS.source_truth import source_truth_requires_evidence


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
    identifiers = {require_string(record, id_key, source) for record in records}
    if len(identifiers) != len(records):
        raise ConfigurationError(f"중복 ID가 있습니다: source={source}, field={id_key}")
    return identifiers


def validate_fact_integrity(
    source_truth_classification: object,
    facts_document: Mapping[str, object],
    sources_document: Mapping[str, object],
    claims_document: Mapping[str, object],
    verified_fact_ledger: Mapping[str, object],
) -> list[ValidationIssue]:
    """사실 기반 Mode에서 근거와 각색 표시가 분리되어 있는지 검사한다."""
    if not source_truth_requires_evidence(source_truth_classification):
        return []
    source_ids = record_ids(sources_document, "sources", "source_id", "sources")
    source_records = require_records(sources_document, "sources", "sources")
    verified_source_ids = {
        require_string(source, "source_id", "sources")
        for source in source_records
        if source.get("verification_status") == "VERIFIED"
    }
    fact_records = require_records(facts_document, "facts", "facts")
    ledger_records = require_records(verified_fact_ledger, "facts", "verified_fact_ledger")
    fact_ids = record_ids(facts_document, "facts", "fact_id", "facts")
    issues: list[ValidationIssue] = []
    factual_ids: set[str] = set()
    fact_by_id = {require_string(fact, "fact_id", "facts"): fact for fact in fact_records}
    ledger_by_id = {
        require_string(fact, "fact_id", "verified_fact_ledger"): fact for fact in ledger_records
    }
    classification_by_id = {
        fact_id: fact.get("classification") for fact_id, fact in fact_by_id.items()
    }

    for fact in fact_records:
        fact_id = require_string(fact, "fact_id", "facts")
        classification = require_string(fact, "classification", fact_id)
        statement = require_string(fact, "statement", fact_id)
        expected_hash = sha256(" ".join(statement.split()).casefold().encode()).hexdigest()
        if fact.get("normalized_statement_hash") != expected_hash:
            issues.append(
                make_fact_issue(
                    "FACT_CLAIM_CONTENT_MISMATCH",
                    "Fact 문장 Hash가 정규화된 내용과 다릅니다.",
                    "01_CASE/facts.json",
                    {"fact_id": fact_id},
                )
            )
        if classification == "FACT":
            factual_ids.add(fact_id)
            referenced_sources = require_string_array(fact, "source_ids", fact_id)
            unknown_sources = sorted(set(referenced_sources) - source_ids)
            unverified_sources = sorted(set(referenced_sources) - verified_source_ids)
            if not referenced_sources or unknown_sources or unverified_sources:
                issues.append(
                    make_fact_issue(
                        "FACT_EVIDENCE_MISSING",
                        "FACT에는 존재하는 Source가 하나 이상 연결되어야 합니다.",
                        "01_CASE/facts.json",
                        {
                            "fact_id": fact_id,
                            "unknown_source_ids": unknown_sources,
                            "unverified_source_ids": unverified_sources,
                        },
                    )
                )
            ledger_fact = ledger_by_id.get(fact_id)
            if ledger_fact is None or ledger_fact.get("statement") != statement:
                issues.append(
                    make_fact_issue(
                        "FACT_CLAIM_CONTENT_MISMATCH",
                        "Story FACT는 검증된 Fact Ledger와 내용이 같아야 합니다.",
                        "01_CASE/facts.json",
                        {"fact_id": fact_id},
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
    claim_counts: dict[str, int] = {}
    for claim in require_records(claims_document, "claims", "claim_evidence"):
        fact_id = require_string(claim, "fact_id", "claim_evidence.claims")
        claim_counts[fact_id] = claim_counts.get(fact_id, 0) + 1
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
        current_fact = fact_by_id.get(fact_id)
        claim_classification = claim.get("classification")
        if current_fact is not None and claim_classification != current_fact.get("classification"):
            issues.append(
                make_fact_issue(
                    "FACT_CLAIM_CLASSIFICATION_MISMATCH",
                    "Claim 분류가 대응 Fact 분류와 다릅니다.",
                    "01_CASE/claim_evidence.json",
                    {"fact_id": fact_id},
                )
            )
        claim_text = claim.get("claim")
        claim_hash = (
            sha256(" ".join(claim_text.split()).casefold().encode()).hexdigest()
            if isinstance(claim_text, str)
            else None
        )
        if claim.get("canonical_claim_hash") != claim_hash or (
            current_fact is not None and current_fact.get("normalized_statement_hash") != claim_hash
        ):
            issues.append(
                make_fact_issue(
                    "FACT_CLAIM_CONTENT_MISMATCH",
                    "Claim Hash 또는 내용이 대응 Fact와 다릅니다.",
                    "01_CASE/claim_evidence.json",
                    {"fact_id": fact_id},
                )
            )
        if claim_classification == "INFERENCE" and not require_string_array(
            claim, "basis_fact_ids", "claim_evidence.claims"
        ):
            issues.append(
                make_fact_issue(
                    "INFERENCE_BASIS_MISSING",
                    "INFERENCE Claim에는 근거 Fact가 필요합니다.",
                    "01_CASE/claim_evidence.json",
                    {"fact_id": fact_id},
                )
            )
        if current_fact is not None and claim_classification == "INFERENCE":
            claim_basis = claim.get("basis_fact_ids")
            fact_basis = current_fact.get("basis_fact_ids")
            if claim_basis != fact_basis:
                issues.append(
                    make_fact_issue(
                        "FACT_CLAIM_CONTENT_MISMATCH",
                        "Inference Claim과 Fact의 Basis Graph가 다릅니다.",
                        "01_CASE/claim_evidence.json",
                        {"fact_id": fact_id},
                    )
                )
        if claim_classification == "DRAMATIZATION" and claim.get("presented_as_fact") is not False:
            issues.append(
                make_fact_issue(
                    "FACT_CLAIM_CLASSIFICATION_MISMATCH",
                    "DRAMATIZATION Claim은 사실로 제시할 수 없습니다.",
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

    duplicate_claim_ids = sorted(fact_id for fact_id, count in claim_counts.items() if count != 1)
    if duplicate_claim_ids:
        issues.append(
            make_fact_issue(
                "DUPLICATE_CANONICAL_CLAIM",
                "fact_id마다 Canonical Claim은 정확히 하나여야 합니다.",
                "01_CASE/claim_evidence.json",
                {"fact_ids": duplicate_claim_ids},
            )
        )

    missing_claim_ids = sorted(fact_ids - set(claim_counts))
    if missing_claim_ids:
        issues.append(
            make_fact_issue(
                "FACT_CLAIM_COVERAGE_MISSING",
                "Fact에 대응하는 Canonical Claim이 없습니다.",
                "01_CASE/claim_evidence.json",
                {"fact_ids": missing_claim_ids},
            )
        )

    inference_issues: list[ValidationIssue] = []
    cycle_signatures: set[tuple[str, ...]] = set()

    def reaches_verified_root(
        fact_id: str,
        path: tuple[str, ...],
    ) -> bool:
        """Inference 경로가 검증된 FACT에 도달하는지 검사한다."""
        if fact_id in path:
            cycle = (*path[path.index(fact_id) :], fact_id)
            if cycle not in cycle_signatures:
                cycle_signatures.add(cycle)
                inference_issues.append(
                    make_fact_issue(
                        "INFERENCE_CYCLE",
                        "Inference Basis Graph에 순환 참조가 있습니다.",
                        "01_CASE/facts.json",
                        {"cycle": list(cycle)},
                    )
                )
            return False
        classification = classification_by_id.get(fact_id)
        if classification == "FACT":
            return fact_id in ledger_by_id
        if classification == "DRAMATIZATION":
            inference_issues.append(
                make_fact_issue(
                    "DRAMATIZATION_USED_AS_BASIS",
                    "DRAMATIZATION은 Inference의 Basis가 될 수 없습니다.",
                    "01_CASE/facts.json",
                    {"fact_id": fact_id, "path": list(path)},
                )
            )
            return False
        fact = fact_by_id.get(fact_id)
        if classification != "INFERENCE" or fact is None:
            return False
        basis_ids = fact.get("basis_fact_ids")
        if not isinstance(basis_ids, list) or not basis_ids:
            return False
        return all(
            isinstance(basis_id, str) and reaches_verified_root(basis_id, (*path, fact_id))
            for basis_id in basis_ids
        )

    for inference_fact_id, inference_classification in classification_by_id.items():
        if inference_classification != "INFERENCE":
            continue
        if not reaches_verified_root(inference_fact_id, ()):
            inference_issues.append(
                make_fact_issue(
                    "INFERENCE_ROOT_NOT_VERIFIED",
                    "모든 Inference Chain은 검증된 FACT에 도달해야 합니다.",
                    "01_CASE/facts.json",
                    {"fact_id": inference_fact_id},
                )
            )
    issues.extend(inference_issues)

    for source in source_records:
        source_id = source.get("source_id")
        required_metadata = (
            "retrieved_at",
            "evidence_locator",
            "verification_actor",
            "verification_status",
        )
        missing_metadata = [
            field
            for field in required_metadata
            if not isinstance(source.get(field), str) or not str(source.get(field)).strip()
        ]
        has_snapshot = isinstance(source.get("source_snapshot_sha256"), str)
        has_archive = isinstance(source.get("archive_locator"), str)
        if missing_metadata or has_snapshot == has_archive:
            issues.append(
                make_fact_issue(
                    "SOURCE_PROVENANCE_MISSING",
                    "Source에는 검증 Metadata와 Snapshot 또는 Archive Locator 하나가 필요합니다.",
                    "01_CASE/sources.json",
                    {
                        "source_id": source_id,
                        "missing_fields": missing_metadata,
                        "has_snapshot": has_snapshot,
                        "has_archive": has_archive,
                    },
                )
            )

    uncovered = sorted(factual_ids - covered_fact_ids)
    invented_facts = sorted(factual_ids - set(ledger_by_id))
    if invented_facts:
        issues.append(
            make_fact_issue(
                "FACT_CLAIM_CONTENT_MISMATCH",
                "검증 Ledger에 없는 FACT를 Story가 생성했습니다.",
                "01_CASE/facts.json",
                {"fact_ids": invented_facts},
            )
        )
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

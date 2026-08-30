"""현재 Runtime 입력 Hash에 결속된 Human Evidence 입력 저장과 투영."""

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import cast

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import append_event, load_run, run_root
from RUNTIME.models import RuntimeRun
from RUNTIME.transactions import acquire_project_lock, release_project_lock
from VALIDATORS.candidate_evaluation import document_sha256
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.source_truth_contract import (
    source_truth_contract_sha256,
    validate_source_truth_contract_integrity,
)


def evidence_input_path(project_path: Path, run_id: str) -> Path:
    """Run별 Evidence Human Input의 고정 경로를 반환한다."""
    return run_root(project_path, run_id) / "human_inputs" / "reference.intake_evidence.json"


def validate_evidence_input(
    document: Mapping[str, object],
    project_id: str,
    source_truth_classification: str,
    input_hashes: Mapping[str, str],
) -> None:
    """Evidence Schema, Project, Source Truth와 현재 Input Hash를 검증한다."""
    schema = load_json_object(
        Path(__file__).resolve().parent / "schemas" / "evidence_input.schema.json"
    )
    errors = collect_schema_errors(document, schema, "evidence_input")
    if errors:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "Evidence 입력이 허용 Schema를 통과하지 못했습니다.",
            "reference.intake_evidence",
            None,
            {"errors": errors},
        )
    if document.get("project_id") != project_id:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "Evidence 입력 Project ID가 Run과 다릅니다.",
            "reference.intake_evidence",
            None,
            {"expected": project_id, "actual": document.get("project_id")},
        )
    if document.get("source_truth_classification") != source_truth_classification:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_SOURCE_TRUTH_MISMATCH",
            False,
            "HUMAN_INPUT",
            "Evidence 입력 Source Truth가 Project 고정값과 다릅니다.",
            "reference.intake_evidence",
            None,
            {
                "expected": source_truth_classification,
                "actual": document.get("source_truth_classification"),
            },
        )
    disclosure = document.get("source_disclosure")
    clinical = document.get("clinical_labels")
    source_subjects = document.get("source_subjects")
    verified_events = document.get("verified_events")
    truth_contract = document.get("source_truth_contract")
    if (
        not isinstance(disclosure, Mapping)
        or disclosure.get("project_id") != project_id
        or disclosure.get("internal_mode") != source_truth_classification
        or not isinstance(clinical, Mapping)
        or clinical.get("project_id") != project_id
        or not isinstance(source_subjects, list)
        or not isinstance(verified_events, list)
        or not isinstance(truth_contract, Mapping)
    ):
        raise RuntimeExecutionError(
            "HUMAN_INPUT_SOURCE_TRUTH_MISMATCH",
            False,
            "HUMAN_INPUT",
            "Evidence 하위 Artifact가 Project 또는 Source Truth와 다릅니다.",
            "reference.intake_evidence",
            None,
            {},
        )
    bound = document.get("bound_input_hashes")
    if not isinstance(bound, Mapping) or dict(bound) != dict(input_hashes):
        raise RuntimeExecutionError(
            "INPUT_HASH_CHANGED",
            False,
            "HUMAN_INPUT",
            "Evidence 입력이 현재 Task Input Hash에 결속되지 않았습니다.",
            "reference.intake_evidence",
            None,
            {
                "expected": dict(input_hashes),
                "actual": dict(bound) if isinstance(bound, Mapping) else {},
            },
        )
    evidence_artifact_outputs(project_id, document)


def submit_evidence_input(
    project_path: Path,
    run_id: str,
    document: Mapping[str, object],
) -> dict[str, object]:
    """Project Lock을 획득하고 검증된 Evidence 입력을 기록한다."""
    lock_run_id = f"human-input:{run_id}"
    lock_path = acquire_project_lock(project_path, lock_run_id)
    try:
        return submit_evidence_input_locked(project_path, run_id, document)
    finally:
        release_project_lock(lock_path, lock_run_id)


def submit_evidence_input_locked(
    project_path: Path,
    run_id: str,
    document: Mapping[str, object],
) -> dict[str, object]:
    """Project Lock 안에서 Evidence 입력의 멱등성과 충돌을 판정한다."""
    run: RuntimeRun = load_run(project_path, run_id)
    task_id = "reference.intake_evidence"
    task_state = run["tasks"].get(task_id)
    if (
        run["status"] != "WAITING_HUMAN"
        or run["current_task_id"] != task_id
        or task_state is None
        or task_state["status"] != "BLOCKED"
        or not task_state["input_hashes"]
    ):
        raise RuntimeExecutionError(
            "HUMAN_INPUT_NOT_EXPECTED",
            False,
            "HUMAN_INPUT",
            "현재 Run은 Evidence Human Input을 기다리지 않습니다.",
            task_id,
            None,
            {"run_id": run_id, "status": run["status"], "current_task_id": run["current_task_id"]},
        )
    config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    source_truth = config.get("source_truth_classification")
    if not isinstance(source_truth, str):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "HUMAN_INPUT",
            "Project Source Truth Classification이 없습니다.",
            task_id,
            None,
            {},
        )
    validate_evidence_input(
        document,
        run["project_id"],
        source_truth,
        task_state["input_hashes"],
    )
    path = evidence_input_path(project_path, run_id)
    if path.is_file():
        current = load_json_object(path)
        if document_sha256(current) == document_sha256(document):
            return {
                "run_id": run_id,
                "task_id": task_id,
                "input_path": str(path),
                "status": "NO_OP",
            }
        raise RuntimeExecutionError(
            "HUMAN_INPUT_CONFLICT",
            False,
            "HUMAN_INPUT",
            "동일 Run의 Evidence 입력은 명시적 Revision 없이 변경할 수 없습니다.",
            task_id,
            None,
            {"run_id": run_id, "input_path": str(path)},
        )
    write_json_object(path, document)
    append_event(
        project_path,
        run_id,
        "HUMAN_INPUT_SUBMITTED",
        task_id,
        {"actor": document.get("actor"), "bound_input_hashes": task_state["input_hashes"]},
    )
    return {"run_id": run_id, "task_id": task_id, "input_path": str(path), "status": "ACCEPTED"}


def current_evidence_input(
    project_path: Path,
    run_id: str,
    project_id: str,
    source_truth_classification: str,
    input_hashes: Mapping[str, str],
) -> Mapping[str, object] | None:
    """현재 Hash와 일치하는 Human Evidence만 반환한다."""
    path = evidence_input_path(project_path, run_id)
    if not path.is_file():
        return None
    document = load_json_object(path)
    try:
        validate_evidence_input(
            document,
            project_id,
            source_truth_classification,
            input_hashes,
        )
    except RuntimeExecutionError as error:
        if error.code == "INPUT_HASH_CHANGED":
            return None
        raise
    return cast(Mapping[str, object], document)


def evidence_artifact_outputs(
    project_id: str,
    document: Mapping[str, object],
) -> dict[str, object]:
    """검증된 Human Input을 원문 없는 Project Evidence Artifact로 투영한다."""
    sources = document.get("sources")
    claims = document.get("claims")
    disclosure = document.get("source_disclosure")
    clinical = document.get("clinical_labels")
    source_subjects = document.get("source_subjects")
    verified_events = document.get("verified_events")
    truth_contract_input = document.get("source_truth_contract")
    if (
        not isinstance(sources, list)
        or not isinstance(claims, list)
        or not isinstance(disclosure, Mapping)
        or not isinstance(clinical, Mapping)
        or not isinstance(source_subjects, list)
        or not isinstance(verified_events, list)
        or not isinstance(truth_contract_input, Mapping)
    ):
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "검증된 Evidence 입력의 Artifact Bundle이 손상되었습니다.",
            "reference.intake_evidence",
            None,
            {},
        )
    source_status_by_id: dict[str, object] = {}
    for raw_source in sources:
        if not isinstance(raw_source, Mapping) or not isinstance(raw_source.get("source_id"), str):
            raise RuntimeExecutionError(
                "HUMAN_INPUT_INVALID",
                False,
                "HUMAN_INPUT",
                "Evidence Source ID가 없습니다.",
                "reference.intake_evidence",
                None,
                {},
            )
        source_id = str(raw_source["source_id"])
        if source_id in source_status_by_id:
            raise RuntimeExecutionError(
                "HUMAN_INPUT_INVALID",
                False,
                "HUMAN_INPUT",
                "Evidence Source ID를 중복할 수 없습니다.",
                "reference.intake_evidence",
                None,
                {"source_id": source_id},
            )
        source_status_by_id[source_id] = raw_source.get("verification_status")
    normalized_claims: list[dict[str, object]] = []
    verified_facts: list[dict[str, object]] = []
    seen_fact_ids: set[str] = set()
    for raw_claim in claims:
        if not isinstance(raw_claim, Mapping):
            raise RuntimeExecutionError(
                "HUMAN_INPUT_INVALID",
                False,
                "HUMAN_INPUT",
                "Evidence Claim 객체가 손상되었습니다.",
                "reference.intake_evidence",
                None,
                {},
            )
        claim = dict(raw_claim)
        fact_id = claim.get("fact_id")
        if not isinstance(fact_id, str) or fact_id in seen_fact_ids:
            raise RuntimeExecutionError(
                "HUMAN_INPUT_INVALID",
                False,
                "HUMAN_INPUT",
                "Evidence Claim Fact ID가 없거나 중복됩니다.",
                "reference.intake_evidence",
                None,
                {"fact_id": fact_id},
            )
        seen_fact_ids.add(fact_id)
        statement = claim.get("claim")
        if not isinstance(statement, str):
            raise RuntimeExecutionError(
                "HUMAN_INPUT_INVALID",
                False,
                "HUMAN_INPUT",
                "Evidence Claim 문장이 없습니다.",
                "reference.intake_evidence",
                None,
                {},
            )
        statement_hash = sha256(" ".join(statement.split()).casefold().encode()).hexdigest()
        claim["canonical_claim_hash"] = statement_hash
        normalized_claims.append(claim)
        if claim.get("classification") == "FACT":
            evidence_ids = claim.get("evidence_source_ids")
            invalid_source_ids = (
                sorted(
                    source_id
                    for source_id in evidence_ids
                    if not isinstance(source_id, str)
                    or source_status_by_id.get(source_id) != "VERIFIED"
                )
                if isinstance(evidence_ids, list)
                else []
            )
            if not isinstance(evidence_ids, list) or not evidence_ids or invalid_source_ids:
                raise RuntimeExecutionError(
                    "HUMAN_INPUT_INVALID",
                    False,
                    "HUMAN_INPUT",
                    "FACT Claim은 검증된 Source에만 결속되어야 합니다.",
                    "reference.intake_evidence",
                    None,
                    {"fact_id": fact_id, "invalid_source_ids": invalid_source_ids},
                )
            verified_facts.append(
                {
                    "fact_id": claim["fact_id"],
                    "statement": statement,
                    "classification": "FACT",
                    "normalized_statement_hash": statement_hash,
                    "source_ids": list(evidence_ids),
                    "basis_fact_ids": [],
                    "presented_as_fact": True,
                }
            )
    if not verified_facts:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "사실 기반 Project에는 하나 이상의 FACT Claim이 필요합니다.",
            "reference.intake_evidence",
            None,
            {},
        )
    source_ids = list(source_status_by_id)
    fact_ids = [str(fact["fact_id"]) for fact in verified_facts]
    subject_ids = [
        str(subject["source_subject_id"])
        for subject in source_subjects
        if isinstance(subject, Mapping) and isinstance(subject.get("source_subject_id"), str)
    ]
    event_ids = [
        str(event["verified_event_id"])
        for event in verified_events
        if isinstance(event, Mapping) and isinstance(event.get("verified_event_id"), str)
    ]
    truth_contract: dict[str, object] = {
        "project_id": project_id,
        "source_truth_classification": document["source_truth_classification"],
        **dict(truth_contract_input),
        "verified_subject_ids": subject_ids,
        "verified_event_ids": event_ids,
    }
    truth_contract["contract_sha256"] = source_truth_contract_sha256(truth_contract)
    brief = " / ".join(str(fact["statement"]) for fact in verified_facts)
    outputs: dict[str, object] = {
        "sources": {"project_id": project_id, "sources": sources},
        "claim_evidence": {"project_id": project_id, "claims": normalized_claims},
        "source_case_brief": {
            "project_id": project_id,
            "source_truth_classification": document["source_truth_classification"],
            "source_ids": source_ids,
            "verified_fact_ids": fact_ids,
            "brief": brief,
        },
        "verified_fact_ledger": {"project_id": project_id, "facts": verified_facts},
        "source_subjects": {"project_id": project_id, "subjects": source_subjects},
        "verified_event_ledger": {"project_id": project_id, "events": verified_events},
        "source_truth_contract": truth_contract,
        "source_disclosure": dict(disclosure),
        "clinical_labels": dict(clinical),
    }
    integrity_issues = validate_source_truth_contract_integrity(
        truth_contract,
        cast(Mapping[str, object], outputs["source_subjects"]),
        cast(Mapping[str, object], outputs["verified_event_ledger"]),
        cast(Mapping[str, object], outputs["claim_evidence"]),
    )
    if integrity_issues:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "Source Truth Contract 참조 또는 Hash가 올바르지 않습니다.",
            "reference.intake_evidence",
            None,
            {"issues": integrity_issues},
        )
    return outputs

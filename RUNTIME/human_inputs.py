"""현재 Runtime 입력 Hash에 결속된 Human Evidence 입력 저장과 투영."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.event_store import append_event, load_run, run_root
from RUNTIME.models import RuntimeRun
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.schema_validation import collect_schema_errors


def evidence_input_path(project_path: Path, run_id: str) -> Path:
    """Run별 Evidence Human Input의 고정 경로를 반환한다."""
    return run_root(project_path, run_id) / "human_inputs" / "reference.build_evidence.json"


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
            "reference.build_evidence",
            None,
            {"errors": errors},
        )
    if document.get("project_id") != project_id:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "Evidence 입력 Project ID가 Run과 다릅니다.",
            "reference.build_evidence",
            None,
            {"expected": project_id, "actual": document.get("project_id")},
        )
    if document.get("source_truth_classification") != source_truth_classification:
        raise RuntimeExecutionError(
            "HUMAN_INPUT_SOURCE_TRUTH_MISMATCH",
            False,
            "HUMAN_INPUT",
            "Evidence 입력 Source Truth가 Project 고정값과 다릅니다.",
            "reference.build_evidence",
            None,
            {
                "expected": source_truth_classification,
                "actual": document.get("source_truth_classification"),
            },
        )
    disclosure = document.get("source_disclosure")
    clinical = document.get("clinical_labels")
    if (
        not isinstance(disclosure, Mapping)
        or disclosure.get("project_id") != project_id
        or disclosure.get("internal_mode") != source_truth_classification
        or not isinstance(clinical, Mapping)
        or clinical.get("project_id") != project_id
    ):
        raise RuntimeExecutionError(
            "HUMAN_INPUT_SOURCE_TRUTH_MISMATCH",
            False,
            "HUMAN_INPUT",
            "Evidence 하위 Artifact가 Project 또는 Source Truth와 다릅니다.",
            "reference.build_evidence",
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
            "reference.build_evidence",
            None,
            {
                "expected": dict(input_hashes),
                "actual": dict(bound) if isinstance(bound, Mapping) else {},
            },
        )


def submit_evidence_input(
    project_path: Path,
    run_id: str,
    document: Mapping[str, object],
) -> dict[str, object]:
    """WAITING_HUMAN Run에 검증된 Evidence 입력을 기록한다."""
    run: RuntimeRun = load_run(project_path, run_id)
    task_id = "reference.build_evidence"
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
    if (
        not isinstance(sources, list)
        or not isinstance(claims, list)
        or not isinstance(disclosure, Mapping)
        or not isinstance(clinical, Mapping)
    ):
        raise RuntimeExecutionError(
            "HUMAN_INPUT_INVALID",
            False,
            "HUMAN_INPUT",
            "검증된 Evidence 입력의 Artifact Bundle이 손상되었습니다.",
            "reference.build_evidence",
            None,
            {},
        )
    return {
        "sources": {"project_id": project_id, "sources": sources},
        "claim_evidence": {"project_id": project_id, "claims": claims},
        "source_disclosure": dict(disclosure),
        "clinical_labels": dict(clinical),
    }

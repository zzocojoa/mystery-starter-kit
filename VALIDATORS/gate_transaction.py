"""Codex App의 Gate별 격리 작성, 검증, 원자 Commit Protocol."""

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from RUNTIME.contracts import (
    load_artifact_contracts,
    load_task_catalog,
    validate_runtime_contracts,
)
from RUNTIME.core_tasks import core_task_outputs, runtime_validation_inputs, story_history
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.gate_control import validate_gate
from RUNTIME.models import ArtifactContract, RuntimeTask
from RUNTIME.output_gateway import (
    encoded_artifact,
    validate_artifact_content,
    validate_core_outputs,
)
from RUNTIME.planner import task_condition_matches, topological_task_ids
from RUNTIME.transactions import (
    acquire_project_lock,
    capture_artifact_hashes,
    commit_gate_transaction,
    create_staging_overlay,
    next_project_state,
    recover_prepared_transactions,
    release_project_lock,
    write_artifact,
)
from VALIDATORS.dependency import artifact_hash, dependency_artifacts
from VALIDATORS.exceptions import ConfigurationError, GateTransactionError
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.models import ProductionValidationReport, ProjectState
from VALIDATORS.pipeline import (
    load_project_artifacts,
    load_selected_project_artifacts,
    run_production_validation,
)
from VALIDATORS.schema_validation import collect_schema_errors
from VALIDATORS.state_machine import GATES, expected_gate, gate_index

PROCESS_TRACE_PATH = "00_PROJECT/process_trace.jsonl"
VALIDATOR_VERSION = "1.0.0"


def parse_audit_timestamp(value: object, source: str) -> datetime:
    """Audit 인과성 비교용 ISO 8601 Offset 시각을 엄격하게 파싱한다."""
    if not isinstance(value, str):
        raise ConfigurationError(f"Audit Timestamp 문자열이 필요합니다: source={source}")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ConfigurationError(
            f"Audit Timestamp가 ISO 8601 형식이 아닙니다: source={source}, value={value!r}"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConfigurationError(
            f"Audit Timestamp에 UTC Offset이 필요합니다: source={source}, value={value!r}"
        )
    return parsed


def change_log_records(project_path: Path) -> list[Mapping[str, object]]:
    """Project Change Log JSONL을 파일 순서대로 읽는다."""
    path = project_path / "00_PROJECT" / "change_log.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigurationError(
            f"Change Log를 읽지 못했습니다: path={path}, detail={error}"
        ) from error
    records: list[Mapping[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise ConfigurationError(
                f"Change Log JSON이 잘못됐습니다: path={path}, line={line_number}"
            ) from error
        if not isinstance(parsed, Mapping):
            raise ConfigurationError(
                f"Change Log Record가 객체가 아닙니다: path={path}, line={line_number}"
            )
        records.append(parsed)
    return records


def process_timestamp_issues(
    project_path: Path,
    traces: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Change Log과 Process Trace의 시간 인과성 위반을 반환한다."""
    issues: list[dict[str, object]] = []
    changes = change_log_records(project_path)
    previous_change_time: datetime | None = None
    initialized_at: datetime | None = None
    for index, record in enumerate(changes):
        occurred_at = parse_audit_timestamp(
            record.get("occurred_at"),
            f"change_log[{index}].occurred_at",
        )
        if previous_change_time is not None and occurred_at < previous_change_time:
            issues.append(
                {
                    "code": "AUDIT_EVENT_TIME_ORDER_ERROR",
                    "message": "Change Log 이벤트 시각이 파일 순서에서 역행합니다.",
                    "event_index": index,
                    "occurred_at": record.get("occurred_at"),
                }
            )
        previous_change_time = occurred_at
        if record.get("event") == "PROJECT_INITIALIZED":
            initialized_at = occurred_at

    previous_started: datetime | None = None
    previous_completed: datetime | None = None
    earliest_started: datetime | None = None
    for index, trace in enumerate(traces):
        started_at = parse_audit_timestamp(
            trace.get("started_at"),
            f"process_trace[{index}].started_at",
        )
        completed_at = parse_audit_timestamp(
            trace.get("completed_at"),
            f"process_trace[{index}].completed_at",
        )
        earliest_started = (
            started_at
            if earliest_started is None
            else min(earliest_started, started_at)
        )
        if (
            started_at > completed_at
            or (previous_started is not None and started_at < previous_started)
            or (previous_completed is not None and completed_at < previous_completed)
        ):
            issues.append(
                {
                    "code": "PROCESS_TRACE_TIME_REGRESSION",
                    "message": "Process Trace 시작·완료 시각이 인과 순서를 역행합니다.",
                    "trace_index": index,
                    "trace_id": trace.get("trace_id"),
                }
            )
        previous_started = started_at
        previous_completed = completed_at
    if (
        initialized_at is not None
        and earliest_started is not None
        and initialized_at > earliest_started
    ):
        issues.append(
            {
                "code": "PROJECT_CREATED_AFTER_GATE_ERROR",
                "message": "Project 생성 시각이 최초 Gate 시작 시각보다 늦습니다.",
                "initialized_at": initialized_at.isoformat(),
                "earliest_gate_started_at": earliest_started.isoformat(),
            }
        )
    return issues


def task_records_root(project_path: Path) -> Path:
    """Codex Gate Task 기록 Root를 반환한다."""
    return project_path / ".runtime" / "codex_tasks"


def task_record_path(project_path: Path, transaction_id: str) -> Path:
    """Gate Task 실행 기록 경로를 반환한다."""
    return task_records_root(project_path) / transaction_id / "task.json"


def project_file_hashes(project_path: Path) -> dict[str, str]:
    """Runtime 운영 파일을 제외한 Project 파일 Hash를 캡처한다."""
    hashes: dict[str, str] = {}
    for path in sorted(project_path.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(project_path)
        if relative_path.parts and relative_path.parts[0] == ".runtime":
            continue
        try:
            hashes[relative_path.as_posix()] = artifact_hash(path.read_bytes())
        except OSError as error:
            raise ConfigurationError(
                f"Project 파일 Hash를 계산하지 못했습니다: path={path}, detail={error}"
            ) from error
    return hashes


def changed_file_paths(
    baseline: Mapping[str, str],
    current: Mapping[str, str],
) -> list[str]:
    """두 Project Snapshot 사이에서 추가, 수정, 삭제된 경로를 반환한다."""
    return sorted(
        path
        for path in set(baseline) | set(current)
        if baseline.get(path) != current.get(path)
    )


def task_record_schema(repository_root: Path) -> dict[str, object]:
    """Gate Transaction 기록 Schema를 반환한다."""
    return load_json_object(
        repository_root / "STANDARD" / "schemas" / "gate_transaction.schema.json"
    )


def process_trace_schema(repository_root: Path) -> dict[str, object]:
    """Process Trace 한 줄의 Schema를 반환한다."""
    return load_json_object(
        repository_root / "STANDARD" / "schemas" / "process_trace.schema.json"
    )


def validate_task_record(
    repository_root: Path,
    record: Mapping[str, object],
    source: str,
) -> None:
    """Gate Task 기록을 Schema로 검증한다."""
    errors = collect_schema_errors(record, task_record_schema(repository_root), source)
    if errors:
        raise GateTransactionError(
            "GATE_TRANSACTION_RECORD_INVALID",
            "Gate Transaction 기록 Schema가 올바르지 않습니다.",
            {"source": source, "errors": errors},
        )


def load_task_record(
    repository_root: Path,
    path: Path,
) -> dict[str, object]:
    """Gate Task 기록을 읽고 Schema를 검증한다."""
    record = load_json_object(path)
    validate_task_record(repository_root, record, str(path))
    return record


def all_task_records(
    repository_root: Path,
    project_path: Path,
) -> list[dict[str, object]]:
    """시작 시각순 Gate Task 기록을 반환한다."""
    records = [
        load_task_record(repository_root, path)
        for path in task_records_root(project_path).glob("*/task.json")
    ]
    return sorted(records, key=lambda record: cast(str, record["started_at"]))


def open_task_record(
    repository_root: Path,
    project_path: Path,
) -> dict[str, object] | None:
    """현재 OPEN 상태인 단일 Gate Task를 반환한다."""
    records = [
        record
        for record in all_task_records(repository_root, project_path)
        if record["status"] == "OPEN"
    ]
    if len(records) > 1:
        raise GateTransactionError(
            "GATE_TRANSACTION_RECORD_INVALID",
            "동시에 둘 이상의 Gate Transaction이 OPEN 상태입니다.",
            {"transaction_ids": [record["transaction_id"] for record in records]},
        )
    return records[0] if records else None


def committed_gate_record(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
) -> dict[str, object] | None:
    """지정 Gate에서 Commit된 가장 최근 Task 기록을 반환한다."""
    records = [
        record
        for record in all_task_records(repository_root, project_path)
        if record["gate_id"] == gate_id and record["status"] == "COMMITTED"
    ]
    return records[-1] if records else None


def source_mode(project_path: Path) -> str:
    """Project의 Story Source Mode를 읽는다."""
    config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    value = config.get("story_source_mode")
    if not isinstance(value, str):
        raise ConfigurationError("production_config.story_source_mode 문자열이 필요합니다.")
    return value


def tasks_for_gate(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
) -> dict[str, RuntimeTask]:
    """현재 Source Mode에서 실행되는 Gate Task를 계약 순서로 반환한다."""
    catalog = load_task_catalog(repository_root)
    selected = {
        task_id: task
        for task_id, task in catalog.items()
        if task["target_gate"] == gate_id
        and task_condition_matches(task["condition"], source_mode(project_path))
    }
    if not selected:
        raise GateTransactionError(
            "GATE_TRANSACTION_NOT_OPEN",
            "요청 Gate에 실행 가능한 Runtime Task가 없습니다.",
            {"gate_id": gate_id},
        )
    ordered_ids = topological_task_ids(selected)
    return {task_id: selected[task_id] for task_id in ordered_ids}


def string_union(tasks: Mapping[str, RuntimeTask], field: str) -> list[str]:
    """Task 문자열 배열 필드의 정렬된 합집합을 반환한다."""
    values: set[str] = set()
    for task in tasks.values():
        raw_values = task.get(field)
        if not isinstance(raw_values, list) or not all(
            isinstance(value, str) for value in raw_values
        ):
            raise ConfigurationError(
                f"Runtime Task 문자열 배열이 필요합니다: field={field}"
            )
        values.update(cast(list[str], raw_values))
    return sorted(values)


def tasks_for_executor(
    tasks: Mapping[str, RuntimeTask],
    executor: str,
) -> dict[str, RuntimeTask]:
    """지정 Executor에 속하는 Task만 계약 순서로 반환한다."""
    return {
        task_id: task
        for task_id, task in tasks.items()
        if task["executor"] == executor
    }


def forbidden_paths(
    dependency_graph: Mapping[str, object],
    allowed_writes: Sequence[str],
) -> list[str]:
    """Task Workspace에서 수정할 수 없는 Canonical 경로를 반환한다."""
    definitions = dependency_artifacts(dependency_graph)
    forbidden = [
        cast(str, definition["path"])
        for artifact_name, definition in definitions.items()
        if artifact_name not in allowed_writes and isinstance(definition.get("path"), str)
    ]
    return sorted(
        set(forbidden)
        | {
            "00_PROJECT/project_state.json",
            PROCESS_TRACE_PATH,
            ".runtime/",
        }
    )


def project_state(project_path: Path) -> ProjectState:
    """Project State를 반환한다."""
    return cast(
        ProjectState,
        load_json_object(project_path / "00_PROJECT" / "project_state.json"),
    )


def canonical_artifact_drift(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    state: ProjectState,
    artifact_names: Sequence[str],
) -> list[dict[str, object]]:
    """Project State Hash와 Canonical Artifact의 불일치를 반환한다."""
    issues: list[dict[str, object]] = []
    definitions = dependency_artifacts(dependency_graph)
    for artifact_name in artifact_names:
        definition = definitions.get(artifact_name)
        if definition is None:
            issues.append(
                {
                    "artifact": artifact_name,
                    "path": None,
                    "reason": "DEPENDENCY_DEFINITION_MISSING",
                }
            )
            continue
        relative_path = definition.get("path")
        artifact_state = state["artifacts"].get(artifact_name)
        if not isinstance(relative_path, str) or artifact_state is None:
            issues.append(
                {
                    "artifact": artifact_name,
                    "path": relative_path,
                    "reason": "STATE_ENTRY_MISSING",
                }
            )
            continue
        expected_hash = artifact_state["content_hash"]
        if artifact_state["status"] == "CLEAN" and expected_hash is None:
            issues.append(
                {
                    "artifact": artifact_name,
                    "path": relative_path,
                    "reason": "CLEAN_HASH_MISSING",
                }
            )
            continue
        if expected_hash is None:
            continue
        path = project_path / relative_path
        try:
            actual_hash = artifact_hash(path.read_bytes())
        except OSError as error:
            issues.append(
                {
                    "artifact": artifact_name,
                    "path": relative_path,
                    "reason": "CANONICAL_FILE_MISSING",
                    "detail": str(error),
                }
            )
            continue
        if actual_hash != expected_hash:
            issues.append(
                {
                    "artifact": artifact_name,
                    "path": relative_path,
                    "reason": "CONTENT_HASH_MISMATCH",
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash,
                }
            )
    return issues


def task_open_unlocked(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    started_at: str,
) -> dict[str, object]:
    """Project Lock 안에서 격리 Workspace와 권한 Snapshot을 생성한다."""
    validate_runtime_contracts(repository_root)
    active = open_task_record(repository_root, project_path)
    if active is not None:
        raise GateTransactionError(
            "GATE_TRANSACTION_ALREADY_OPEN",
            "기존 Gate Transaction을 먼저 제출하거나 중단해야 합니다.",
            {
                "transaction_id": active["transaction_id"],
                "gate_id": active["gate_id"],
            },
        )
    state = project_state(project_path)
    dependency_graph = load_json_object(
        repository_root / "STANDARD" / "dependency_graph.json"
    )
    required_gate = expected_gate(state)["gate_id"]
    if gate_id != required_gate:
        raise GateTransactionError(
            "GATE_TRANSACTION_GATE_MISMATCH",
            "현재 Project에서 열 수 있는 Gate와 요청 Gate가 다릅니다.",
            {
                "current_gate": state["current_gate"],
                "expected_gate": required_gate,
                "actual_gate": gate_id,
            },
        )
    tasks = tasks_for_gate(repository_root, project_path, gate_id)
    catalog = load_task_catalog(repository_root)
    gate_map = artifact_gate_map(catalog)
    completed_artifacts = sorted(
        artifact_name
        for artifact_name, artifact_gate in gate_map.items()
        if gate_index(artifact_gate) < gate_index(gate_id)
    )
    drift = canonical_artifact_drift(
        project_path,
        dependency_graph,
        state,
        completed_artifacts,
    )
    if drift:
        raise GateTransactionError(
            "GATE_TRANSACTION_INPUT_DRIFT",
            "Project State와 Canonical Artifact Hash가 일치하지 않습니다.",
            {"artifacts": drift},
        )
    allowed_reads = string_union(tasks, "reads")
    gate_writes = string_union(tasks, "writes")
    allowed_writes = string_union(tasks_for_executor(tasks, "LLM"), "writes")
    external_reads = sorted(set(allowed_reads) - set(gate_writes))
    input_hashes = capture_artifact_hashes(
        project_path,
        external_reads,
        dependency_graph,
    )
    transaction_id = f"CODEX-TASK-{uuid4().hex[:16].upper()}"
    workspace = create_staging_overlay(
        project_path,
        transaction_id,
        gate_id,
        1,
        {},
        dependency_graph,
    )
    record: dict[str, object] = {
        "schema_family": "gate-transaction",
        "schema_version": "1.0.0",
        "transaction_id": transaction_id,
        "project_id": state["project_id"],
        "gate_id": gate_id,
        "process_revision": state["readiness"]["process_revision"],
        "task_ids": list(tasks),
        "agent_ids": sorted({task["agent_id"] for task in tasks.values()}),
        "allowed_reads": allowed_reads,
        "allowed_writes": allowed_writes,
        "input_hashes": input_hashes,
        "canonical_hashes": project_file_hashes(project_path),
        "workspace_hashes": project_file_hashes(workspace),
        "forbidden_paths": forbidden_paths(dependency_graph, allowed_writes),
        "workspace": str(workspace),
        "status": "OPEN",
        "changed_paths": [],
        "commit_sha": None,
        "started_at": started_at,
        "completed_at": None,
    }
    validate_task_record(repository_root, record, transaction_id)
    write_json_object(task_record_path(project_path, transaction_id), record)
    return record


def task_open(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    started_at: str,
) -> dict[str, object]:
    """단일 Writer Lock으로 현재 Gate의 Codex Task를 연다."""
    lock_owner = f"CODEX-OPEN-{uuid4().hex[:16].upper()}"
    lock_path = acquire_project_lock(project_path, lock_owner)
    try:
        return task_open_unlocked(
            repository_root,
            project_path,
            gate_id,
            started_at,
        )
    finally:
        release_project_lock(lock_path, lock_owner)


def artifact_path_map(
    dependency_graph: Mapping[str, object],
) -> dict[str, str]:
    """Project 상대 경로를 Artifact 이름에 대응한다."""
    return {
        cast(str, definition["path"]): artifact_name
        for artifact_name, definition in dependency_artifacts(dependency_graph).items()
        if isinstance(definition.get("path"), str)
    }


def artifact_gate_map(tasks: Mapping[str, RuntimeTask]) -> dict[str, str]:
    """각 Artifact가 처음 작성되는 Gate를 반환한다."""
    result: dict[str, str] = {}
    for task in tasks.values():
        for artifact_name in task["writes"]:
            current = result.get(artifact_name)
            if current is None or gate_index(task["target_gate"]) < gate_index(current):
                result[artifact_name] = task["target_gate"]
    return result


def classify_changed_paths(
    changed_paths: Sequence[str],
    gate_id: str,
    allowed_writes: Sequence[str],
    gate_tasks: Mapping[str, RuntimeTask],
    catalog: Mapping[str, RuntimeTask],
    dependency_graph: Mapping[str, object],
) -> dict[str, str]:
    """변경 경로의 Future Gate, Allowlist, Agent 소유권을 검증한다."""
    path_map = artifact_path_map(dependency_graph)
    gate_map = artifact_gate_map(catalog)
    definitions = dependency_artifacts(dependency_graph)
    changed_artifacts: dict[str, str] = {}
    for path in changed_paths:
        artifact_name = path_map.get(path)
        if artifact_name is None:
            raise GateTransactionError(
                "UNAUTHORIZED_TASK_WRITE",
                "Task writes에 없는 Project 경로가 변경되었습니다.",
                {"gate_id": gate_id, "path": path},
            )
        target_gate = gate_map.get(artifact_name)
        if target_gate is not None and gate_index(target_gate) > gate_index(gate_id):
            raise GateTransactionError(
                "FUTURE_GATE_ARTIFACT_MODIFIED",
                "현재 Gate보다 뒤의 Artifact가 변경되었습니다.",
                {
                    "gate_id": gate_id,
                    "artifact": artifact_name,
                    "artifact_gate": target_gate,
                    "path": path,
                },
            )
        if artifact_name not in allowed_writes:
            raise GateTransactionError(
                "UNAUTHORIZED_TASK_WRITE",
                "변경 Artifact가 현재 Task writes Allowlist에 없습니다.",
                {"gate_id": gate_id, "artifact": artifact_name, "path": path},
            )
        owner = definitions[artifact_name].get("owner_agent")
        authorized_agents = {
            task["agent_id"]
            for task in gate_tasks.values()
            if artifact_name in task["writes"]
        }
        if owner not in authorized_agents:
            raise GateTransactionError(
                "UNAUTHORIZED_TASK_WRITE",
                "Artifact Owner Agent와 현재 Task Agent가 일치하지 않습니다.",
                {
                    "gate_id": gate_id,
                    "artifact": artifact_name,
                    "owner_agent": owner,
                    "task_agents": sorted(authorized_agents),
                },
            )
        changed_artifacts[path] = artifact_name
    return changed_artifacts


def verify_canonical_snapshot(
    record: Mapping[str, object],
    project_path: Path,
    dependency_graph: Mapping[str, object],
    catalog: Mapping[str, RuntimeTask],
) -> None:
    """Task가 열린 뒤 Canonical Project의 직접 수정을 차단한다."""
    baseline = record.get("canonical_hashes")
    if not isinstance(baseline, Mapping):
        raise GateTransactionError(
            "GATE_TRANSACTION_RECORD_INVALID",
            "Canonical Hash Snapshot이 없습니다.",
            {"transaction_id": record.get("transaction_id")},
        )
    changed = changed_file_paths(
        cast(Mapping[str, str], baseline),
        project_file_hashes(project_path),
    )
    if not changed:
        return
    path_map = artifact_path_map(dependency_graph)
    gate_map = artifact_gate_map(catalog)
    gate_id = cast(str, record["gate_id"])
    input_names = set(cast(Mapping[str, str], record["input_hashes"]))
    for path in changed:
        artifact_name = path_map.get(path)
        target_gate = None if artifact_name is None else gate_map.get(artifact_name)
        if target_gate is not None and gate_index(target_gate) > gate_index(gate_id):
            raise GateTransactionError(
                "FUTURE_GATE_ARTIFACT_MODIFIED",
                "Canonical Project의 Future Gate Artifact가 직접 변경되었습니다.",
                {"gate_id": gate_id, "artifact": artifact_name, "path": path},
            )
        if artifact_name in input_names:
            raise GateTransactionError(
                "GATE_TRANSACTION_INPUT_DRIFT",
                "Task Open 뒤 Canonical 입력 Artifact가 변경되었습니다.",
                {"gate_id": gate_id, "artifact": artifact_name, "path": path},
            )
    raise GateTransactionError(
        "UNAUTHORIZED_TASK_WRITE",
        "Task Workspace 밖의 Canonical Project가 직접 변경되었습니다.",
        {"gate_id": gate_id, "paths": changed},
    )


def read_workspace_outputs(
    repository_root: Path,
    workspace: Path,
    allowed_writes: Sequence[str],
    tasks: Mapping[str, RuntimeTask],
    dependency_graph: Mapping[str, object],
) -> dict[str, object]:
    """Workspace의 전체 Task 출력에 Artifact Contract를 적용한다."""
    definitions = dependency_artifacts(dependency_graph)
    contracts = load_artifact_contracts(repository_root)
    outputs: dict[str, object] = {}
    for artifact_name in allowed_writes:
        definition = definitions.get(artifact_name)
        contract = contracts.get(artifact_name)
        if definition is None or contract is None:
            raise ConfigurationError(
                f"Artifact 정의 또는 Contract가 없습니다: artifact={artifact_name}"
            )
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            raise ConfigurationError(
                f"Artifact path 문자열이 필요합니다: artifact={artifact_name}"
            )
        path = workspace / relative_path
        if contract["media_type"] == "application/json":
            content: object = load_json_object(path)
        else:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as error:
                raise ConfigurationError(
                    f"Task 출력 Text를 읽지 못했습니다: path={path}, detail={error}"
                ) from error
        task_id = next(
            task_id
            for task_id, task in tasks.items()
            if artifact_name in task["writes"]
        )
        validate_artifact_content(
            repository_root,
            task_id,
            artifact_name,
            contract["media_type"],
            content,
            contract,
        )
        outputs[artifact_name] = content
    return outputs


def generate_core_outputs(
    repository_root: Path,
    project_path: Path,
    workspace: Path,
    tasks: Mapping[str, RuntimeTask],
    outputs: dict[str, object],
    dependency_graph: Mapping[str, object],
    reference_source: Path | None,
) -> dict[str, str]:
    """CORE Task를 계약 순서로 실행하고 검증된 출력을 Workspace에 기록한다."""
    definitions = dependency_artifacts(dependency_graph)
    contracts = load_artifact_contracts(repository_root)
    generated_paths: dict[str, str] = {}
    for task_id, task in tasks.items():
        if task["executor"] != "CORE":
            continue
        generated = core_task_outputs(
            task_id,
            repository_root,
            project_path,
            outputs,
            dependency_graph,
            reference_source,
            False,
        )
        validate_core_outputs(
            repository_root,
            task_id,
            task,
            generated,
            contracts,
        )
        for artifact_name, content in generated.items():
            definition = definitions.get(artifact_name)
            relative_path = None if definition is None else definition.get("path")
            if not isinstance(relative_path, str):
                raise ConfigurationError(
                    f"CORE Artifact path 문자열이 필요합니다: artifact={artifact_name}"
                )
            write_artifact(workspace / relative_path, content)
            outputs[artifact_name] = content
            generated_paths[relative_path] = artifact_name
    return generated_paths


def trace_records(
    repository_root: Path,
    project_path: Path,
) -> list[dict[str, object]]:
    """Process Trace JSONL을 Schema 검증해 반환한다."""
    path = project_path / PROCESS_TRACE_PATH
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ConfigurationError(
            f"Process Trace를 읽지 못했습니다: path={path}, detail={error}"
        ) from error
    schema = process_trace_schema(repository_root)
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise GateTransactionError(
                "PROCESS_TRACE_INVALID",
                "Process Trace JSON 문법이 올바르지 않습니다.",
                {"line": line_number, "detail": error.msg},
            ) from error
        if not isinstance(value, Mapping):
            raise GateTransactionError(
                "PROCESS_TRACE_INVALID",
                "Process Trace 한 줄은 JSON 객체여야 합니다.",
                {"line": line_number},
            )
        record = dict(value)
        errors = collect_schema_errors(record, schema, f"{path}:{line_number}")
        if errors:
            raise GateTransactionError(
                "PROCESS_TRACE_INVALID",
                "Process Trace Schema가 올바르지 않습니다.",
                {"line": line_number, "errors": errors},
            )
        records.append(record)
    return records


def process_conformance(
    records: Sequence[Mapping[str, object]],
    start_gate: str,
    through_gate: str,
    process_revision: int,
) -> tuple[bool, list[str]]:
    """요구 범위의 모든 Gate가 순서대로 Trace됐는지 판정한다."""
    start_index = gate_index(start_gate)
    end_index = gate_index(through_gate)
    required = [f"GATE-{index:02d}" for index in range(start_index, end_index + 1)]
    seen = {
        cast(str, record["gate_id"])
        for record in records
        if record.get("gate_result") == "PASS"
        and record.get("process_revision") == process_revision
    }
    missing = [gate_id for gate_id in required if gate_id not in seen]
    ordered_gate_indices = [
        gate_index(cast(str, record["gate_id"]))
        for record in records
        if record.get("process_revision") == process_revision
        and start_index <= gate_index(cast(str, record["gate_id"])) <= end_index
    ]
    ordered = ordered_gate_indices == sorted(ordered_gate_indices)
    if not ordered:
        missing.append("OUT_OF_ORDER")
    return not missing, missing


def gate_commit_sha(
    outputs: Mapping[str, object],
    contracts: Mapping[str, ArtifactContract],
) -> str:
    """Gate 출력 전체를 대표하는 결정론적 SHA-256을 반환한다."""
    hashes = {
        artifact_name: artifact_hash(
            encoded_artifact(content, contracts[artifact_name]["media_type"])
        )
        for artifact_name, content in sorted(outputs.items())
    }
    payload = json.dumps(hashes, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return artifact_hash(payload)


def build_gate_traces(
    record: Mapping[str, object],
    tasks: Mapping[str, RuntimeTask],
    changed_artifacts: Mapping[str, str],
    commit_sha: str,
    completed_at: str,
) -> list[dict[str, object]]:
    """Gate Bundle의 각 Runtime Task에 대한 Process Trace를 만든다."""
    input_hashes = cast(Mapping[str, str], record["input_hashes"])
    traces: list[dict[str, object]] = []
    for task_id, task in tasks.items():
        task_changes = sorted(
            path
            for path, artifact_name in changed_artifacts.items()
            if artifact_name in task["writes"]
        )
        traces.append(
            {
                "trace_id": f"TRACE-{uuid4().hex[:16].upper()}",
                "project_id": record["project_id"],
                "task_id": task_id,
                "agent_id": task["agent_id"],
                "gate_id": record["gate_id"],
                "process_revision": record["process_revision"],
                "input_hashes": {
                    artifact_name: input_hashes[artifact_name]
                    for artifact_name in task["reads"]
                    if artifact_name in input_hashes
                },
                "changed_paths": task_changes,
                "validator_version": VALIDATOR_VERSION,
                "gate_result": "PASS",
                "commit_sha": commit_sha,
                "started_at": record["started_at"],
                "completed_at": completed_at,
            }
        )
    return traces


def process_trace_bytes(
    project_path: Path,
    traces: Sequence[Mapping[str, object]],
) -> bytes:
    """기존 Trace 뒤에 새 Trace를 추가한 전체 JSONL Byte를 반환한다."""
    path = project_path / PROCESS_TRACE_PATH
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(
            f"Process Trace를 읽지 못했습니다: path={path}, detail={error}"
        ) from error
    prefix = existing if not existing or existing.endswith("\n") else existing + "\n"
    appended = "".join(
        json.dumps(dict(trace), ensure_ascii=False, sort_keys=True) + "\n"
        for trace in traces
    )
    return (prefix + appended).encode("utf-8")


def validate_gate_overlay(
    repository_root: Path,
    workspace: Path,
    gate_id: str,
    dependency_graph: Mapping[str, object],
    reference_source: Path | None,
) -> None:
    """Workspace에서 현재 Gate Validator만 실행한다."""
    catalog = load_task_catalog(repository_root)
    required_artifacts: set[str] = set()
    for task in catalog.values():
        if gate_index(task["target_gate"]) > gate_index(gate_id):
            continue
        if not task_condition_matches(task["condition"], source_mode(workspace)):
            continue
        required_artifacts.update(task["reads"])
        required_artifacts.update(task["writes"])
    artifacts = load_selected_project_artifacts(
        workspace,
        dependency_graph,
        sorted(required_artifacts),
    )
    (
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        policy,
        thresholds,
    ) = runtime_validation_inputs(repository_root)
    reference_material = (
        load_json_object(reference_source) if reference_source is not None else None
    )
    issues = validate_gate(
        gate_id,
        artifacts,
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        policy,
        thresholds,
        story_history(repository_root),
        reference_material,
    )
    if issues:
        raise GateTransactionError(
            "GATE_REJECTED",
            "Task Workspace가 현재 Gate Validator를 통과하지 못했습니다.",
            {"gate_id": gate_id, "issues": issues},
        )


def task_submit(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    completed_at: str,
    reference_source: Path | None,
) -> dict[str, object]:
    """현재 Gate Workspace를 검증하고 Canonical Project에 원자 Commit한다."""
    active = open_task_record(repository_root, project_path)
    if active is None:
        committed = committed_gate_record(repository_root, project_path, gate_id)
        code = (
            "GATE_TRANSACTION_ALREADY_COMMITTED"
            if committed is not None
            else "GATE_TRANSACTION_NOT_OPEN"
        )
        raise GateTransactionError(
            code,
            "제출할 OPEN Gate Transaction이 없습니다.",
            {"gate_id": gate_id},
        )
    if active["gate_id"] != gate_id:
        raise GateTransactionError(
            "GATE_TRANSACTION_GATE_MISMATCH",
            "OPEN Transaction Gate와 제출 Gate가 다릅니다.",
            {"open_gate": active["gate_id"], "submit_gate": gate_id},
        )
    state = project_state(project_path)
    expected = expected_gate(state)["gate_id"]
    if expected != gate_id:
        raise GateTransactionError(
            "GATE_TRANSACTION_GATE_MISMATCH",
            "현재 Project Gate와 제출 Gate가 일치하지 않습니다.",
            {"current_gate": state["current_gate"], "expected": expected, "actual": gate_id},
        )
    transaction_id = cast(str, active["transaction_id"])
    lock_path = acquire_project_lock(project_path, transaction_id)
    try:
        current_record = load_task_record(
            repository_root,
            task_record_path(project_path, transaction_id),
        )
        if current_record["status"] != "OPEN":
            code = (
                "GATE_TRANSACTION_ALREADY_COMMITTED"
                if current_record["status"] == "COMMITTED"
                else "GATE_TRANSACTION_NOT_OPEN"
            )
            raise GateTransactionError(
                code,
                "Lock 획득 전에 Gate Transaction 상태가 변경되었습니다.",
                {
                    "transaction_id": transaction_id,
                    "status": current_record["status"],
                },
            )
        active = current_record
        recover_prepared_transactions(project_path)
        dependency_graph = load_json_object(
            repository_root / "STANDARD" / "dependency_graph.json"
        )
        catalog = load_task_catalog(repository_root)
        gate_tasks = tasks_for_gate(repository_root, project_path, gate_id)
        verify_canonical_snapshot(active, project_path, dependency_graph, catalog)
        workspace = Path(cast(str, active["workspace"]))
        baseline_hashes = cast(Mapping[str, str], active["workspace_hashes"])
        changed_paths = changed_file_paths(
            baseline_hashes,
            project_file_hashes(workspace),
        )
        allowed_writes = cast(list[str], active["allowed_writes"])
        changed_artifacts = classify_changed_paths(
            changed_paths,
            gate_id,
            allowed_writes,
            gate_tasks,
            catalog,
            dependency_graph,
        )
        outputs = read_workspace_outputs(
            repository_root,
            workspace,
            allowed_writes,
            gate_tasks,
            dependency_graph,
        )
        changed_artifacts.update(
            generate_core_outputs(
                repository_root,
                project_path,
                workspace,
                gate_tasks,
                outputs,
                dependency_graph,
                reference_source,
            )
        )
        validate_gate_overlay(
            repository_root,
            workspace,
            gate_id,
            dependency_graph,
            reference_source,
        )
        input_hashes = cast(Mapping[str, str], active["input_hashes"])
        next_state = next_project_state(
            state,
            gate_id,
            input_hashes,
            outputs,
            dependency_graph,
            completed_at,
        )
        contracts = load_artifact_contracts(repository_root)
        commit_sha = gate_commit_sha(outputs, contracts)
        traces = build_gate_traces(
            active,
            gate_tasks,
            changed_artifacts,
            commit_sha,
            completed_at,
        )
        trace_schema = process_trace_schema(repository_root)
        for trace in traces:
            errors = collect_schema_errors(trace, trace_schema, PROCESS_TRACE_PATH)
            if errors:
                raise GateTransactionError(
                    "PROCESS_TRACE_INVALID",
                    "생성된 Process Trace가 Schema를 통과하지 못했습니다.",
                    {"errors": errors},
                )
        existing_traces = trace_records(repository_root, project_path)
        conformant, missing = process_conformance(
            [*existing_traces, *traces],
            next_state["readiness"]["process_start_gate"],
            gate_id,
            next_state["readiness"]["process_revision"],
        )
        if not conformant:
            raise GateTransactionError(
                "PROCESS_TRACE_MISSING",
                "현재 Gate까지의 Process Trace가 완전하지 않습니다.",
                {
                    "process_start_gate": next_state["readiness"]["process_start_gate"],
                    "through_gate": gate_id,
                    "missing_gate_traces": missing,
                },
            )
        next_state["readiness"]["process_status"] = (
            "PROCESS_CONFORMANT"
            if conformant and gate_id == "GATE-13"
            else "NONCONFORMANT"
        )
        runtime_transaction_id = commit_gate_transaction(
            project_path,
            transaction_id,
            gate_id,
            workspace,
            outputs,
            dependency_graph,
            next_state,
            {PROCESS_TRACE_PATH: process_trace_bytes(project_path, traces)},
        )
        committed = deepcopy(active)
        committed["status"] = "COMMITTED"
        committed["changed_paths"] = changed_paths
        committed["commit_sha"] = commit_sha
        committed["completed_at"] = completed_at
        validate_task_record(repository_root, committed, transaction_id)
        write_json_object(task_record_path(project_path, transaction_id), committed)
        return {
            **committed,
            "runtime_transaction_id": runtime_transaction_id,
            "trace_count": len(traces),
            "process_conformant": next_state["readiness"]["process_status"]
            == "PROCESS_CONFORMANT",
            "project_state": next_state["state"],
            "current_gate": next_state["current_gate"],
        }
    except RuntimeExecutionError as error:
        code = (
            "GATE_TRANSACTION_INPUT_DRIFT"
            if error.code == "INPUT_HASH_CHANGED"
            else error.code
        )
        raise GateTransactionError(code, str(error), error.safe_context) from error
    finally:
        release_project_lock(lock_path, transaction_id)


def task_abort_unlocked(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    completed_at: str,
) -> dict[str, object]:
    """Project Lock 안에서 OPEN Gate Transaction을 중단한다."""
    active = open_task_record(repository_root, project_path)
    if active is None:
        raise GateTransactionError(
            "GATE_TRANSACTION_NOT_OPEN",
            "중단할 OPEN Gate Transaction이 없습니다.",
            {"gate_id": gate_id},
        )
    if active["gate_id"] != gate_id:
        raise GateTransactionError(
            "GATE_TRANSACTION_GATE_MISMATCH",
            "OPEN Transaction Gate와 중단 Gate가 다릅니다.",
            {"open_gate": active["gate_id"], "abort_gate": gate_id},
        )
    aborted = deepcopy(active)
    aborted["status"] = "ABORTED"
    aborted["completed_at"] = completed_at
    validate_task_record(
        repository_root,
        aborted,
        cast(str, aborted["transaction_id"]),
    )
    write_json_object(
        task_record_path(project_path, cast(str, aborted["transaction_id"])),
        aborted,
    )
    return aborted


def task_abort(
    repository_root: Path,
    project_path: Path,
    gate_id: str,
    completed_at: str,
) -> dict[str, object]:
    """단일 Writer Lock으로 Gate Transaction을 안전하게 중단한다."""
    lock_owner = f"CODEX-ABORT-{uuid4().hex[:16].upper()}"
    lock_path = acquire_project_lock(project_path, lock_owner)
    try:
        return task_abort_unlocked(
            repository_root,
            project_path,
            gate_id,
            completed_at,
        )
    finally:
        release_project_lock(lock_path, lock_owner)


def owner_revision_gate(
    catalog: Mapping[str, RuntimeTask],
    owner_agent: str,
    through_gate: str,
) -> str:
    """Owner Agent가 다시 작성해야 할 가장 최근 LLM Gate를 반환한다."""
    candidates = [
        task["target_gate"]
        for task in catalog.values()
        if task["executor"] == "LLM"
        and task["agent_id"] == owner_agent
        and gate_index(task["target_gate"]) <= gate_index(through_gate)
    ]
    if not candidates:
        raise GateTransactionError(
            "OWNER_AGENT_TASK_NOT_FOUND",
            "현재 범위에 Owner Agent가 다시 수행할 LLM Task가 없습니다.",
            {"owner_agent": owner_agent, "through_gate": through_gate},
        )
    return max(candidates, key=gate_index)


def revision_state(
    state: ProjectState,
    target_gate: str,
    catalog: Mapping[str, RuntimeTask],
    updated_at: str,
) -> ProjectState:
    """Owner 재작업을 위해 목표 Gate 이후 상태를 무효화한다."""
    target_index = gate_index(target_gate)
    next_state = deepcopy(state)
    next_state["schema_version"] = "1.2.0"
    next_state["current_gate"] = (
        "NONE" if target_index == 0 else GATES[target_index - 1]["gate_id"]
    )
    next_state["state"] = (
        "INITIALIZED" if target_index == 0 else GATES[target_index - 1]["target_state"]
    )
    next_state["updated_at"] = updated_at
    next_state["readiness"] = {
        "artifact_status": "INCOMPLETE",
        "contract_status": "UNVALIDATED",
        "process_status": "NONCONFORMANT",
        "editorial_status": "NOT_REVIEWED",
        "process_start_gate": target_gate,
        "process_revision": state["readiness"]["process_revision"] + 1,
    }
    gate_map = artifact_gate_map(catalog)
    affected = {
        artifact_name
        for artifact_name, artifact_gate in gate_map.items()
        if gate_index(artifact_gate) >= target_index
    }
    target_artifacts = sorted(
        artifact_name
        for artifact_name, artifact_gate in gate_map.items()
        if artifact_gate == target_gate
    )
    for artifact_name in affected:
        artifact_state = next_state["artifacts"].get(artifact_name)
        if artifact_state is None:
            continue
        artifact_state["status"] = "DIRTY"
        artifact_state["invalidated_by"] = [
            target_artifact
            for target_artifact in target_artifacts
            if target_artifact != artifact_name
        ]
    return next_state


def return_task_to_owner_unlocked(
    repository_root: Path,
    project_path: Path,
    owner_agent: str,
    actor: str,
    reason: str,
    returned_at: str,
) -> dict[str, object]:
    """Critic Issue를 Owner Agent의 Gate로 되돌리고 새 Process Revision을 연다."""
    if not owner_agent.strip() or not actor.strip() or not reason.strip():
        raise GateTransactionError(
            "OWNER_RETURN_CONTEXT_MISSING",
            "Owner 반환에는 owner_agent, actor, reason이 모두 필요합니다.",
            {"owner_agent": owner_agent, "actor": actor, "reason": reason},
        )
    state = project_state(project_path)
    if state["state"] in {"EDITORIAL_APPROVED", "PRODUCTION_READY"}:
        raise GateTransactionError(
            "OWNER_RETURN_STATE_INVALID",
            "Editorial 승인 또는 Production 확정 뒤에는 Task를 되돌릴 수 없습니다.",
            {"state": state["state"]},
        )
    catalog = load_task_catalog(repository_root)
    active = open_task_record(repository_root, project_path)
    through_gate = (
        cast(str, active["gate_id"])
        if active is not None
        else state["current_gate"]
    )
    if through_gate == "NONE":
        raise GateTransactionError(
            "OWNER_RETURN_STATE_INVALID",
            "통과한 Gate가 없는 Project는 Owner Task로 되돌릴 수 없습니다.",
            {"current_gate": through_gate},
        )
    target_gate = owner_revision_gate(catalog, owner_agent, through_gate)
    if active is not None:
        aborted = deepcopy(active)
        aborted["status"] = "ABORTED"
        aborted["completed_at"] = returned_at
        validate_task_record(
            repository_root,
            aborted,
            cast(str, aborted["transaction_id"]),
        )
        write_json_object(
            task_record_path(project_path, cast(str, aborted["transaction_id"])),
            aborted,
        )
    next_state = revision_state(state, target_gate, catalog, returned_at)
    write_json_object(
        project_path / "00_PROJECT" / "project_state.json",
        next_state,
    )
    return {
        "project_id": state["project_id"],
        "owner_agent": owner_agent,
        "actor": actor,
        "reason": reason,
        "target_gate": target_gate,
        "current_gate": next_state["current_gate"],
        "process_revision": next_state["readiness"]["process_revision"],
        "aborted_transaction_id": (
            None if active is None else active["transaction_id"]
        ),
        "returned_at": returned_at,
    }


def return_task_to_owner(
    repository_root: Path,
    project_path: Path,
    owner_agent: str,
    actor: str,
    reason: str,
    returned_at: str,
) -> dict[str, object]:
    """단일 Writer Lock 안에서 Critic Issue를 Owner Agent에게 반환한다."""
    lock_owner = f"OWNER-RETURN-{uuid4().hex[:16].upper()}"
    lock_path = acquire_project_lock(project_path, lock_owner)
    try:
        return return_task_to_owner_unlocked(
            repository_root,
            project_path,
            owner_agent,
            actor,
            reason,
            returned_at,
        )
    finally:
        release_project_lock(lock_path, lock_owner)


def task_status(
    repository_root: Path,
    project_path: Path,
) -> dict[str, object]:
    """현재 OPEN Task 또는 가장 최근 Task와 Project Gate를 반환한다."""
    records = all_task_records(repository_root, project_path)
    active = next(
        (record for record in reversed(records) if record["status"] == "OPEN"),
        None,
    )
    latest = records[-1] if records else None
    state = project_state(project_path)
    return {
        "project_id": state["project_id"],
        "current_gate": state["current_gate"],
        "project_state": state["state"],
        "readiness": state["readiness"],
        "active_task": active,
        "latest_task": latest,
    }


def full_validation_report(
    repository_root: Path,
    project_path: Path,
    reference_source: Path | None,
    channel_path: Path | None,
) -> ProductionValidationReport:
    """Canonical 파일 집합을 상태 변경 없이 전체 검증한다."""
    dependency_graph = load_json_object(
        repository_root / "STANDARD" / "dependency_graph.json"
    )
    artifacts = load_project_artifacts(project_path, dependency_graph)
    (
        default_channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        policy,
        thresholds,
    ) = runtime_validation_inputs(repository_root)
    channel = (
        load_json_object(channel_path)
        if channel_path is not None
        else default_channel
    )
    reference_material = (
        load_json_object(reference_source) if reference_source is not None else None
    )
    return run_production_validation(
        artifacts,
        channel,
        story_schema,
        fingerprint_schema,
        presentation_schemas,
        policy,
        thresholds,
        story_history(repository_root),
        reference_material,
    )


def audit_project(
    repository_root: Path,
    project_path: Path,
    reference_source: Path | None,
    channel_path: Path | None,
    audited_at: str,
) -> dict[str, object]:
    """Artifact 정합성과 Process Conformance를 Project State와 분리해 판정한다."""
    state = project_state(project_path)
    dependency_graph = load_json_object(
        repository_root / "STANDARD" / "dependency_graph.json"
    )
    drift = canonical_artifact_drift(
        project_path,
        dependency_graph,
        state,
        sorted(dependency_artifacts(dependency_graph)),
    )
    validation = full_validation_report(
        repository_root,
        project_path,
        reference_source,
        channel_path,
    )
    traces = trace_records(repository_root, project_path)
    trace_conformant, missing_traces = process_conformance(
        traces,
        state["readiness"]["process_start_gate"],
        "GATE-13",
        state["readiness"]["process_revision"],
    )
    timestamp_issues = process_timestamp_issues(project_path, traces)
    conformant = trace_conformant and not drift and not timestamp_issues
    artifact_complete = (
        validation["gate_results"].get("GATE-13") == "PASS" and not drift
    )
    contract_validated = validation["result"] == "PASS" and not drift
    editorial_approved = (
        state["readiness"]["editorial_status"] == "EDITORIAL_APPROVED"
    )
    production_ready = (
        artifact_complete
        and contract_validated
        and conformant
        and editorial_approved
        and state["state"] == "PRODUCTION_READY"
    )
    technical_pass = artifact_complete and contract_validated and conformant
    process_issues: list[dict[str, object]] = []
    process_issues.extend(timestamp_issues)
    if not trace_conformant:
        process_issues.append(
            {
                "code": "PROCESS_TRACE_MISSING",
                "message": "요구 Gate 범위의 PASS Process Trace가 완전하지 않습니다.",
                "missing_gate_traces": missing_traces,
            }
        )
    if drift:
        process_issues.append(
            {
                "code": "CANONICAL_ARTIFACT_DRIFT",
                "message": "Project State와 Canonical Artifact Hash가 일치하지 않습니다.",
                "artifacts": drift,
            }
        )
    return {
        "schema_family": "process-audit",
        "schema_version": "1.0.0",
        "project_id": state["project_id"],
        "audited_at": audited_at,
        "result": "PASS" if technical_pass else "FAIL",
        "state_unchanged": True,
        "current_gate": state["current_gate"],
        "project_state": state["state"],
        "artifact_complete": artifact_complete,
        "contract_validated": contract_validated,
        "process_conformant": conformant,
        "editorial_approved": editorial_approved,
        "production_ready": production_ready,
        "missing_gate_traces": missing_traces,
        "process_revision": state["readiness"]["process_revision"],
        "process_issues": process_issues,
        "trace_count": len(traces),
        "validation": validation,
    }

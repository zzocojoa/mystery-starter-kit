"""Runtime Run, Event, Attempt, Provenance의 Append-only 감사 저장소."""

import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import RunStatus, RuntimeRun, RuntimeTaskState, TaskStatus
from VALIDATORS.io import load_json_object, write_json_object
from VALIDATORS.schema_validation import collect_schema_errors


def utc_now() -> str:
    """감사 기록에 사용할 UTC ISO 시각을 반환한다."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_run_id() -> str:
    """시각과 무작위 Suffix를 결합한 충돌 방지 Run ID를 만든다."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"RUN-{timestamp}-{uuid4().hex[:8].upper()}"


def run_root(project_path: Path, run_id: str) -> Path:
    """Project 내부 Run 감사 디렉터리를 반환한다."""
    return project_path / ".runtime" / "runs" / run_id


def run_path(project_path: Path, run_id: str) -> Path:
    """Run 상태 JSON 경로를 반환한다."""
    return run_root(project_path, run_id) / "run.json"


def initial_task_state() -> RuntimeTaskState:
    """실행 전 Task 상태를 생성한다."""
    return RuntimeTaskState(
        status="PENDING",
        attempt=0,
        provider_id=None,
        model_resolved=None,
        input_hashes={},
        prompt_hash=None,
        error=None,
    )


def create_run(
    project_path: Path,
    project_id: str,
    from_gate: str,
    to_gate: str,
    route_profile: str,
    reference_source: Path | None,
    task_ids: list[str],
) -> RuntimeRun:
    """Project State와 분리된 Runtime Run을 생성하고 기록한다."""
    run_id = new_run_id()
    now = utc_now()
    run = RuntimeRun(
        schema_family="runtime-run",
        schema_version="1.0.0",
        run_id=run_id,
        project_id=project_id,
        project_path=str(project_path.resolve()),
        status="CREATED",
        from_gate=from_gate,
        to_gate=to_gate,
        route_profile=route_profile,
        reference_source=str(reference_source.resolve()) if reference_source is not None else None,
        current_task_id=None,
        tasks={task_id: initial_task_state() for task_id in task_ids},
        created_at=now,
        updated_at=now,
        cancel_requested=False,
        error=None,
    )
    save_run(project_path, run)
    append_event(project_path, run_id, "RUN_CREATED", None, {"project_id": project_id})
    return run


def save_run(project_path: Path, run: RuntimeRun) -> None:
    """Run 상태를 Schema 검증 후 기록한다."""
    schema_path = Path(__file__).resolve().parent / "schemas" / "runtime_run.schema.json"
    schema = load_json_object(schema_path)
    errors = collect_schema_errors(run, schema, "runtime_run")
    if errors:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Runtime Run 상태 Schema 검증에 실패했습니다.",
            run.get("current_task_id"),
            None,
            {"errors": errors},
        )
    write_json_object(run_path(project_path, run["run_id"]), run)


def load_run(project_path: Path, run_id: str) -> RuntimeRun:
    """저장된 Runtime Run 상태를 읽고 Schema를 검증한다."""
    document = load_json_object(run_path(project_path, run_id))
    schema = load_json_object(
        Path(__file__).resolve().parent / "schemas" / "runtime_run.schema.json"
    )
    errors = collect_schema_errors(document, schema, "runtime_run")
    if errors:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "저장된 Runtime Run 상태가 손상되었습니다.",
            None,
            None,
            {"run_id": run_id, "errors": errors},
        )
    return cast(RuntimeRun, document)


def update_run_status(
    project_path: Path,
    run: RuntimeRun,
    status: RunStatus,
    current_task_id: str | None,
    error: dict[str, object] | None,
) -> RuntimeRun:
    """Run 입력을 수정하지 않고 새 운영 상태를 기록한다."""
    next_run = deepcopy(run)
    next_run["status"] = status
    next_run["current_task_id"] = current_task_id
    next_run["error"] = deepcopy(error)
    next_run["updated_at"] = utc_now()
    save_run(project_path, next_run)
    return next_run


def update_task_state(
    project_path: Path,
    run: RuntimeRun,
    task_id: str,
    status: TaskStatus,
    attempt: int,
    provider_id: str | None,
    model_resolved: str | None,
    input_hashes: Mapping[str, str],
    prompt_hash: str | None,
    error: dict[str, object] | None,
) -> RuntimeRun:
    """Task 입력을 수정하지 않고 새 Task 상태를 Run에 반영한다."""
    if task_id not in run["tasks"]:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Run에 등록되지 않은 Task 상태 변경입니다.",
            task_id,
            None,
            {},
        )
    next_run = deepcopy(run)
    next_run["tasks"][task_id] = RuntimeTaskState(
        status=status,
        attempt=attempt,
        provider_id=provider_id,
        model_resolved=model_resolved,
        input_hashes=dict(input_hashes),
        prompt_hash=prompt_hash,
        error=deepcopy(error),
    )
    next_run["current_task_id"] = task_id
    next_run["updated_at"] = utc_now()
    save_run(project_path, next_run)
    return next_run


def append_event(
    project_path: Path,
    run_id: str,
    event_type: str,
    task_id: str | None,
    safe_context: Mapping[str, object],
) -> None:
    """검증된 Runtime Event를 JSONL에 Append-only로 기록한다."""
    event = {
        "schema_family": "runtime-event",
        "schema_version": "1.0.0",
        "event_id": f"EVT-{uuid4().hex[:16].upper()}",
        "run_id": run_id,
        "event_type": event_type,
        "occurred_at": utc_now(),
        "task_id": task_id,
        "safe_context": dict(safe_context),
    }
    schema = load_json_object(
        Path(__file__).resolve().parent / "schemas" / "runtime_event.schema.json"
    )
    errors = collect_schema_errors(event, schema, "runtime_event")
    if errors:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Runtime Event Schema 검증에 실패했습니다.",
            task_id,
            None,
            {"errors": errors},
        )
    path = run_root(project_path, run_id) / "events.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as error:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Runtime Event를 기록하지 못했습니다.",
            task_id,
            None,
            {"path": str(path)},
        ) from error


def write_attempt_document(
    project_path: Path,
    run_id: str,
    task_id: str,
    attempt: int,
    file_name: str,
    document: Mapping[str, object],
) -> Path:
    """Provider Request/Response와 Context Manifest를 Attempt별로 기록한다."""
    path = run_root(project_path, run_id) / "tasks" / task_id / f"attempt-{attempt:03d}" / file_name
    write_json_object(path, document)
    return path


def write_provenance(
    project_path: Path,
    artifact_name: str,
    provenance: Mapping[str, object],
) -> None:
    """최종 Artifact의 생성·입력·Provider Hash를 기록한다."""
    path = project_path / ".runtime" / "provenance" / f"{artifact_name}.json"
    write_json_object(path, provenance)


def find_run(repository_root: Path, run_id: str) -> tuple[Path, RuntimeRun]:
    """Repository Projects에서 고유한 Run ID를 찾아 반환한다."""
    matches = sorted((repository_root / "PROJECTS").glob(f"*/.runtime/runs/{run_id}/run.json"))
    if len(matches) != 1:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Run ID를 정확히 하나 찾을 수 없습니다.",
            None,
            None,
            {"run_id": run_id, "match_count": len(matches)},
        )
    project_path = matches[0].parents[3]
    return project_path, load_run(project_path, run_id)

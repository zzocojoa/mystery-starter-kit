"""Agent Manifest와 Task Catalog, 현재 Gate로 실행 계획 생성."""

from collections.abc import Mapping
from pathlib import Path

from RUNTIME.contracts import load_task_catalog
from RUNTIME.errors import RuntimeExecutionError
from RUNTIME.models import ExecutionPlan, PlannedTask, RuntimeTask
from VALIDATORS.channel_registry import resolve_project_channel
from VALIDATORS.io import load_json_object
from VALIDATORS.pipeline import load_existing_project_artifacts
from VALIDATORS.state_machine import gate_index


def next_gate_id(current_gate: str) -> str:
    """현재 Gate 직후의 실행 가능 Gate를 반환한다."""
    if current_gate == "NONE":
        return "GATE-00"
    index = gate_index(current_gate) + 1
    if index > gate_index("GATE-13"):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Project가 이미 PRODUCTION_READY 상태입니다.",
            None,
            None,
            {"current_gate": current_gate},
        )
    return f"GATE-{index:02d}"


def task_condition_matches(
    condition: str,
    source_mode: str,
    channel: Mapping[str, object],
    artifacts: Mapping[str, object],
) -> bool:
    """Source, Capability와 선행 Artifact 상태로 Task 실행 여부를 판정한다."""
    if condition == "ALWAYS":
        return True
    if condition == "REFERENCE_ONLY":
        return source_mode == "REFERENCE_INSPIRED"
    if condition == "TRUE_STORY_ONLY":
        return source_mode in {"TRUE_STORY", "INSPIRED_BY_TRUE_EVENTS"}
    if condition.startswith("FACT_BASED_OR_CAPABILITY_ENABLED:"):
        if source_mode in {"TRUE_STORY", "INSPIRED_BY_TRUE_EVENTS"}:
            return True
        capability_id = condition.removeprefix(
            "FACT_BASED_OR_CAPABILITY_ENABLED:"
        )
        capabilities = channel.get("capabilities")
        capability = (
            capabilities.get(capability_id)
            if isinstance(capabilities, Mapping)
            else None
        )
        return isinstance(capability, Mapping) and capability.get("enabled") is True
    if condition.startswith("CAPABILITY_ENABLED:"):
        capability_id = condition.removeprefix("CAPABILITY_ENABLED:")
        capabilities = channel.get("capabilities")
        capability = (
            capabilities.get(capability_id)
            if isinstance(capabilities, Mapping)
            else None
        )
        return isinstance(capability, Mapping) and capability.get("enabled") is True
    if condition.startswith("ARTIFACT_STATUS:"):
        _prefix, artifact_name, expected_status = condition.split(":", 2)
        artifact = artifacts.get(artifact_name)
        return isinstance(artifact, Mapping) and artifact.get("status") == expected_status
    if condition.startswith("ARTIFACT_EXISTS:"):
        artifact_name = condition.removeprefix("ARTIFACT_EXISTS:")
        return artifact_name in artifacts
    raise RuntimeExecutionError(
        "RUNTIME_CONFIGURATION_ERROR",
        False,
        "RUN",
        "알 수 없는 Runtime Task Condition입니다.",
        None,
        None,
        {"condition": condition},
    )


def tasks_in_gate_range(
    tasks: Mapping[str, RuntimeTask],
    from_gate: str,
    to_gate: str,
) -> dict[str, RuntimeTask]:
    """지정 Gate 범위의 Task만 원래 계약 순서로 반환한다."""
    start = gate_index(from_gate)
    end = gate_index(to_gate)
    return {
        task_id: task
        for task_id, task in tasks.items()
        if start <= gate_index(task["target_gate"]) <= end
    }


def topological_task_ids(tasks: Mapping[str, RuntimeTask]) -> list[str]:
    """Gate와 Task 의존성을 보존하는 안정적인 실행 순서를 계산한다."""
    pending = list(tasks)
    completed: set[str] = set()
    ordered: list[str] = []
    while pending:
        ready = [
            task_id
            for task_id in pending
            if all(
                dependency not in tasks or dependency in completed
                for dependency in tasks[task_id]["depends_on_tasks"]
            )
        ]
        if not ready:
            raise RuntimeExecutionError(
                "RUNTIME_CONFIGURATION_ERROR",
                False,
                "RUN",
                "Runtime Task 의존성에 순환이 있습니다.",
                None,
                None,
                {"tasks": pending},
            )
        ready.sort(
            key=lambda task_id: (gate_index(tasks[task_id]["target_gate"]), pending.index(task_id))
        )
        for task_id in ready:
            pending.remove(task_id)
            completed.add(task_id)
            ordered.append(task_id)
    return ordered


def build_execution_plan(
    repository_root: Path,
    project_path: Path,
    from_gate: str,
    to_gate: str,
) -> ExecutionPlan:
    """현재 Gate에서 건너뛰지 않는 Runtime 실행 계획을 생성한다."""
    state = load_json_object(project_path / "00_PROJECT" / "project_state.json")
    production_config = load_json_object(project_path / "00_PROJECT" / "production_config.json")
    project_id = state.get("project_id")
    current_gate = state.get("current_gate")
    source_mode = production_config.get("story_source_mode")
    if (
        not isinstance(project_id, str)
        or not isinstance(current_gate, str)
        or not isinstance(source_mode, str)
    ):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Project State 또는 Production Config 식별 필드가 올바르지 않습니다.",
            None,
            None,
            {},
        )
    expected_from = next_gate_id(current_gate)
    if from_gate != expected_from:
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Runtime은 Gate를 건너뛰거나 이미 통과한 Gate를 다시 실행할 수 없습니다.",
            None,
            None,
            {
                "expected_from": expected_from,
                "actual_from": from_gate,
                "current_gate": current_gate,
            },
        )
    if gate_index(to_gate) < gate_index(from_gate):
        raise RuntimeExecutionError(
            "RUNTIME_CONFIGURATION_ERROR",
            False,
            "RUN",
            "Runtime 종료 Gate가 시작 Gate보다 앞설 수 없습니다.",
            None,
            None,
            {"from_gate": from_gate, "to_gate": to_gate},
        )
    catalog = load_task_catalog(repository_root)
    dependency_graph = load_json_object(repository_root / "STANDARD/dependency_graph.json")
    channel, _manifest, _channel_path = resolve_project_channel(
        repository_root,
        production_config,
        None,
    )
    artifacts = load_existing_project_artifacts(project_path, dependency_graph)
    ranged = tasks_in_gate_range(catalog, from_gate, to_gate)
    ordered = topological_task_ids(ranged)
    planned = [
        PlannedTask(
            task_id=task_id,
            target_gate=ranged[task_id]["target_gate"],
            executor=ranged[task_id]["executor"],
            status="PLANNED"
            if task_condition_matches(
                ranged[task_id]["condition"],
                source_mode,
                channel,
                artifacts,
            )
            else "SKIPPED",
        )
        for task_id in ordered
    ]
    return ExecutionPlan(
        project_id=project_id,
        current_gate=current_gate,
        from_gate=from_gate,
        to_gate=to_gate,
        tasks=planned,
    )

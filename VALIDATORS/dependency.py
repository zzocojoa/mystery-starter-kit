"""Artifact Dependency Graph와 변경 무효화 규칙."""

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from typing import cast

from VALIDATORS.exceptions import ConfigurationError
from VALIDATORS.models import ArtifactState, ProjectState


def dependency_artifacts(graph: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Dependency Graph의 Artifact 정의를 엄격하게 읽는다."""
    artifacts = graph.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ConfigurationError("dependency_graph.artifacts 객체가 필요합니다.")
    normalized: dict[str, dict[str, object]] = {}
    for artifact_name, artifact_definition in artifacts.items():
        if not isinstance(artifact_name, str) or not isinstance(artifact_definition, Mapping):
            raise ConfigurationError(
                f"Artifact 정의 형식이 올바르지 않습니다: artifact={artifact_name!r}"
            )
        normalized[artifact_name] = cast(dict[str, object], dict(artifact_definition))
    return normalized


def dependency_names(definition: Mapping[str, object], artifact_name: str) -> list[str]:
    """Artifact가 참조하는 상위 Artifact 이름을 읽는다."""
    depends_on = definition.get("depends_on")
    if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
        raise ConfigurationError(
            f"depends_on은 문자열 배열이어야 합니다: artifact={artifact_name}"
        )
    return cast(list[str], depends_on.copy())


def validate_dependency_graph(graph: Mapping[str, object]) -> None:
    """알 수 없는 참조와 순환 의존성을 발견하면 명시적으로 실패한다."""
    artifacts = dependency_artifacts(graph)
    for artifact_name, definition in artifacts.items():
        unknown = sorted(set(dependency_names(definition, artifact_name)) - set(artifacts))
        if unknown:
            raise ConfigurationError(
                "Dependency Graph에 알 수 없는 참조가 있습니다: "
                f"artifact={artifact_name}, unknown={unknown}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_name: str) -> None:
        if artifact_name in visiting:
            raise ConfigurationError(
                f"Dependency Graph에 순환이 있습니다: artifact={artifact_name}"
            )
        if artifact_name in visited:
            return
        visiting.add(artifact_name)
        for dependency_name in dependency_names(artifacts[artifact_name], artifact_name):
            visit(dependency_name)
        visiting.remove(artifact_name)
        visited.add(artifact_name)

    for artifact_name in artifacts:
        visit(artifact_name)


def build_initial_project_state(
    graph: Mapping[str, object],
    project_id: str,
    updated_at: str,
) -> ProjectState:
    """모든 Artifact가 MISSING인 초기 프로젝트 상태를 생성한다."""
    validate_dependency_graph(graph)
    artifacts = {
        artifact_name: ArtifactState(
            status="MISSING",
            content_hash=None,
            invalidated_by=[],
        )
        for artifact_name in dependency_artifacts(graph)
    }
    return ProjectState(
        schema_family="project-state",
        schema_version="1.2.0",
        project_id=project_id,
        state="INITIALIZED",
        current_gate="NONE",
        updated_at=updated_at,
        readiness={
            "artifact_status": "INCOMPLETE",
            "contract_status": "UNVALIDATED",
            "process_status": "NONCONFORMANT",
            "editorial_status": "NOT_REVIEWED",
            "process_start_gate": "GATE-00",
            "process_revision": 1,
        },
        artifacts=artifacts,
    )


def artifact_hash(content: bytes) -> str:
    """Artifact 변경 추적용 SHA-256을 계산한다."""
    return sha256(content).hexdigest()


def reverse_dependencies(graph: Mapping[str, object]) -> dict[str, set[str]]:
    """변경 전파에 사용할 역방향 Dependency Graph를 생성한다."""
    artifacts = dependency_artifacts(graph)
    reversed_graph: dict[str, set[str]] = {
        artifact_name: set() for artifact_name in artifacts
    }
    for artifact_name, definition in artifacts.items():
        for dependency_name in dependency_names(definition, artifact_name):
            reversed_graph[dependency_name].add(artifact_name)
    return reversed_graph


def transitive_dependents(graph: Mapping[str, object], artifact_name: str) -> set[str]:
    """변경 Artifact의 모든 하위 의존 Artifact를 반환한다."""
    reversed_graph = reverse_dependencies(graph)
    if artifact_name not in reversed_graph:
        raise ConfigurationError(f"알 수 없는 Artifact입니다: artifact={artifact_name}")
    pending = list(reversed_graph[artifact_name])
    dependents: set[str] = set()
    while pending:
        dependent = pending.pop()
        if dependent in dependents:
            continue
        dependents.add(dependent)
        pending.extend(reversed_graph[dependent])
    return dependents


def invalidate_artifact_dependents(
    graph: Mapping[str, object],
    state: ProjectState,
    changed_artifact: str,
    changed_hash: str,
    updated_at: str,
) -> ProjectState:
    """변경 Artifact와 모든 하위 산출물을 DIRTY로 표시한 새 상태를 반환한다."""
    if changed_artifact not in state["artifacts"]:
        raise ConfigurationError(
            f"Project State에 Artifact가 없습니다: artifact={changed_artifact}"
        )
    next_state = deepcopy(state)
    changed_state = next_state["artifacts"][changed_artifact]
    changed_state["status"] = "DIRTY"
    changed_state["content_hash"] = changed_hash
    changed_state["invalidated_by"] = []
    for dependent in transitive_dependents(graph, changed_artifact):
        dependent_state = next_state["artifacts"][dependent]
        dependent_state["status"] = "DIRTY"
        dependent_state["invalidated_by"] = sorted(
            set(dependent_state["invalidated_by"]) | {changed_artifact}
        )
    next_state["state"] = "BLOCKED"
    next_state["updated_at"] = updated_at
    return next_state


def mark_artifact_clean(
    state: ProjectState,
    artifact_name: str,
    content_hash: str,
    updated_at: str,
) -> ProjectState:
    """검증된 Artifact 하나를 CLEAN으로 표시한 새 상태를 반환한다."""
    if artifact_name not in state["artifacts"]:
        raise ConfigurationError(f"Project State에 Artifact가 없습니다: artifact={artifact_name}")
    next_state = deepcopy(state)
    next_state["artifacts"][artifact_name] = ArtifactState(
        status="CLEAN",
        content_hash=content_hash,
        invalidated_by=[],
    )
    next_state["updated_at"] = updated_at
    return next_state

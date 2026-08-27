"""Presentation Contract v1 Project의 명시적 v2 Migration 상태 전환."""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

from VALIDATORS.dependency import artifact_hash, dependency_artifacts
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ArtifactState, ProjectState
from VALIDATORS.presentation_validation import PRESENTATION_SCHEMA_VERSION
from VALIDATORS.state_machine import GATES, gate_index


def gate_five_and_later_artifacts() -> frozenset[str]:
    """GATE-05부터 재생성해야 하는 모든 필수 Artifact를 반환한다."""
    names: set[str] = set()
    for gate in GATES[gate_index("GATE-05") :]:
        names.update(gate["required_artifacts"])
    return frozenset(names)


def presentation_migration_required(project_path: Path) -> bool:
    """Project가 v2 Presentation Artifact를 모두 갖추었는지 판정한다."""
    required_paths = (
        project_path / "06_SCENE" / "panel_cast.json",
        project_path / "06_SCENE" / "reaction_segments.json",
        project_path / "07_SCRIPT" / "drama_script.md",
        project_path / "07_SCRIPT" / "narration_script.md",
        project_path / "07_SCRIPT" / "panel_reaction_script.md",
        project_path / "09_PRODUCTION" / "panel_reaction_script.md",
    )
    if any(not path.is_file() for path in required_paths):
        return True
    presentation_path = project_path / "06_SCENE" / "presentation_plan.json"
    if not presentation_path.is_file():
        return True
    presentation = load_json_object(presentation_path)
    return presentation.get("schema_version") != PRESENTATION_SCHEMA_VERSION


def missing_artifact_state() -> ArtifactState:
    """새 v2 Artifact의 초기 MISSING 상태를 반환한다."""
    return ArtifactState(status="MISSING", content_hash=None, invalidated_by=[])


def migration_current_gate(state: ProjectState) -> str:
    """Migration이 기존 Project의 마지막 통과 Gate를 앞당기지 않도록 제한한다."""
    current_gate = state["current_gate"]
    if current_gate == "NONE":
        return current_gate
    return current_gate if gate_index(current_gate) < gate_index("GATE-04") else "GATE-04"


def mark_presentation_migration_required(
    project_path: Path,
    dependency_graph: Mapping[str, object],
    state: ProjectState,
    updated_at: str,
) -> ProjectState:
    """기존 Artifact를 보존하며 GATE-05 이후를 재생성 대상으로 전환한다."""
    next_state = deepcopy(state)
    definitions = dependency_artifacts(dependency_graph)
    for artifact_name in definitions:
        if artifact_name not in next_state["artifacts"]:
            next_state["artifacts"][artifact_name] = missing_artifact_state()

    regeneration_names = gate_five_and_later_artifacts()
    for artifact_name in regeneration_names:
        definition = definitions[artifact_name]
        relative_path = definition.get("path")
        if not isinstance(relative_path, str):
            continue
        path = project_path / relative_path
        artifact_state = next_state["artifacts"][artifact_name]
        if not path.is_file():
            artifact_state["status"] = "MISSING"
            artifact_state["content_hash"] = None
            artifact_state["invalidated_by"] = []
            continue
        artifact_state["status"] = (
            "INVALID"
            if artifact_name in {"presentation_plan", "draft_script", "final_script"}
            else "DIRTY"
        )
        artifact_state["content_hash"] = artifact_hash(path.read_bytes())
        artifact_state["invalidated_by"] = ["presentation_plan"]

    next_state["state"] = "PRESENTATION_MIGRATION_REQUIRED"
    next_state["current_gate"] = migration_current_gate(state)
    next_state["updated_at"] = updated_at
    return next_state

"""Artifact Dependency Graph와 상태 무효화 검증."""

from pathlib import Path

from VALIDATORS.dependency import (
    artifact_hash,
    build_initial_project_state,
    invalidate_artifact_dependents,
    validate_dependency_graph,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.schema_validation import collect_schema_errors

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "STANDARD" / "dependency_graph.json"
GRAPH_SCHEMA_PATH = ROOT / "STANDARD" / "schemas" / "dependency_graph.schema.json"


def test_dependency_graph_is_schema_valid_and_acyclic() -> None:
    """기준 Dependency Graph는 구조적으로 유효하고 순환이 없어야 한다."""
    graph = load_json_object(GRAPH_PATH)
    schema = load_json_object(GRAPH_SCHEMA_PATH)

    assert collect_schema_errors(graph, schema, str(GRAPH_PATH)) == []
    validate_dependency_graph(graph)


def test_story_dna_change_invalidates_all_downstream_artifacts() -> None:
    """Story DNA 변경은 Script와 QA와 Production 산출물을 모두 DIRTY로 만들어야 한다."""
    graph = load_json_object(GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-001", "2026-08-25T00:00:00Z")

    changed_state = invalidate_artifact_dependents(
        graph,
        state,
        "story_dna",
        artifact_hash(b"changed-story-dna"),
        "2026-08-25T00:01:00Z",
    )

    assert changed_state["state"] == "BLOCKED"
    assert changed_state["artifacts"]["story_dna"]["status"] == "DIRTY"
    assert changed_state["artifacts"]["final_script"]["status"] == "DIRTY"
    assert changed_state["artifacts"]["validation_report"]["status"] == "DIRTY"
    assert changed_state["artifacts"]["edit_script"]["status"] == "DIRTY"
    assert state["artifacts"]["story_dna"]["status"] == "MISSING"

"""Artifact Dependency Graph와 상태 무효화 검증."""

from pathlib import Path

from VALIDATORS.dependency import (
    artifact_hash,
    artifact_required_for_project,
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


def test_v2_disabled_optional_capability_does_not_require_artifact() -> None:
    """v2 버전만으로 비활성 Optional Capability Artifact를 강제하지 않는다."""
    definition = {
        "required_when_capability_enabled": "EXPERT_ANALYSIS_POLICY",
        "required_when_source_truth": ["VERIFIED_TRUE_CASE"],
    }
    channel = {"capabilities": {"EXPERT_ANALYSIS_POLICY": {"enabled": False}}}
    config = {
        "channel_content_version": "2.0.0",
        "source_truth_classification": "VERIFIED_TRUE_CASE",
    }

    assert not artifact_required_for_project(definition, channel, config, {})


def test_expert_script_requires_enabled_policy_truth_and_planned_status() -> None:
    """Expert Script는 Capability, 사실성, 계획 상태가 모두 충족될 때만 필수다."""
    definition = {
        "required_when_capability_enabled": "EXPERT_ANALYSIS_POLICY",
        "required_when_source_truth": ["VERIFIED_TRUE_CASE"],
        "required_when_plan_status": {"artifact": "expert_segments", "status": "PLANNED"},
    }
    channel = {"capabilities": {"EXPERT_ANALYSIS_POLICY": {"enabled": True}}}
    config = {
        "channel_content_version": "2.0.0",
        "source_truth_classification": "VERIFIED_TRUE_CASE",
    }

    assert artifact_required_for_project(
        definition, channel, config, {"expert_segments": {"status": "PLANNED"}}
    )
    assert not artifact_required_for_project(
        definition, channel, config, {"expert_segments": {"status": "NOT_APPLICABLE"}}
    )

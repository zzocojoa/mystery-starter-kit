"""Artifact Dependency Graph와 상태 무효화 검증."""

from copy import deepcopy
from pathlib import Path

from VALIDATORS.dependency import (
    artifact_hash,
    artifact_required_for_project,
    build_initial_project_state,
    invalidate_artifact_dependents,
    reconcile_project_state_artifacts,
    validate_dependency_graph,
)
from VALIDATORS.io import load_json_object
from VALIDATORS.requirements import requirement_matches
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


def test_screenplay_change_invalidates_readable_trace_chain() -> None:
    """Unit 변경은 Readable 원본·QA·Validation·Production Copy를 모두 무효화한다."""
    graph = load_json_object(GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-006", "2026-09-02T00:00:00Z")

    changed = invalidate_artifact_dependents(
        graph,
        state,
        "screenplay_units",
        artifact_hash(b"changed-screenplay"),
        "2026-09-02T00:01:00Z",
    )

    for artifact_name in (
        "broadcast_readable_script",
        "broadcast_readable_report",
        "validation_report",
        "production_broadcast_readable_script",
        "editorial_review",
    ):
        assert changed["artifacts"][artifact_name]["status"] == "DIRTY"


def test_existing_state_registers_new_contract_artifacts_as_missing() -> None:
    """Contract 확장 시 기존 State는 새 Artifact를 자동 등록하되 입력을 바꾸지 않는다."""
    graph = load_json_object(GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-006", "2026-09-02T00:00:00Z")
    original = deepcopy(state)
    for artifact_name in (
        "broadcast_readable_script",
        "broadcast_readable_report",
        "production_broadcast_readable_script",
    ):
        original["artifacts"].pop(artifact_name)

    reconciled = reconcile_project_state_artifacts(graph, original)

    for artifact_name in (
        "broadcast_readable_script",
        "broadcast_readable_report",
        "production_broadcast_readable_script",
    ):
        assert reconciled["artifacts"][artifact_name] == {
            "status": "MISSING",
            "content_hash": None,
            "invalidated_by": [],
        }
    assert all(
        artifact_name not in original["artifacts"]
        for artifact_name in (
            "broadcast_readable_script",
            "broadcast_readable_report",
            "production_broadcast_readable_script",
        )
    )


def test_scene_change_invalidates_footprint_and_production_manifest() -> None:
    """Scene Card 변경은 CORE Footprint와 최종 Manifest를 모두 무효화한다."""
    graph = load_json_object(GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-001", "2026-08-25T00:00:00Z")

    changed = invalidate_artifact_dependents(
        graph,
        state,
        "scene_cards",
        artifact_hash(b"changed-scenes"),
        "2026-08-25T00:01:00Z",
    )

    assert changed["artifacts"]["production_footprint"]["status"] == "DIRTY"
    assert changed["artifacts"]["production_manifest"]["status"] == "DIRTY"


def test_evidence_change_invalidates_truth_contract_and_candidate_approval() -> None:
    """Evidence 변경은 Truth Contract와 그 이후 Human Candidate 승인을 무효화한다."""
    graph = load_json_object(GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-001", "2026-08-25T00:00:00Z")

    changed = invalidate_artifact_dependents(
        graph,
        state,
        "claim_evidence",
        artifact_hash(b"changed-claims"),
        "2026-08-25T00:01:00Z",
    )

    assert changed["artifacts"]["source_truth_contract"]["status"] == "DIRTY"
    assert changed["artifacts"]["candidate_approval"]["status"] == "DIRTY"


def test_v2_disabled_optional_capability_does_not_require_artifact() -> None:
    """v2 버전만으로 비활성 Optional Capability Artifact를 강제하지 않는다."""
    definition = {
        "required_when": {
            "all": [
                {"capability_enabled": "EXPERT_ANALYSIS_POLICY"},
                {"source_truth_in": ["VERIFIED_TRUE_CASE"]},
            ]
        },
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
        "required_when": {
            "all": [
                {"capability_enabled": "EXPERT_ANALYSIS_POLICY"},
                {"source_truth_in": ["VERIFIED_TRUE_CASE"]},
                {"artifact_status": ["expert_segments", "PLANNED"]},
            ]
        },
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


def test_fact_based_condition_uses_truth_classification_not_source_mode() -> None:
    """USER_CASE와 REFERENCE_INSPIRED도 사실성 분류가 맞으면 증거 Task 조건을 충족한다."""
    predicate = {
        "source_truth_in": ["VERIFIED_TRUE_CASE", "INSPIRED_BY_TRUE_EVENTS"]
    }
    channel: dict[str, object] = {"capabilities": {}}
    cases = (
        ("USER_CASE", "VERIFIED_TRUE_CASE"),
        ("REFERENCE_INSPIRED", "INSPIRED_BY_TRUE_EVENTS"),
    )
    for source_mode, source_truth in cases:
        config = {
            "story_source_mode": source_mode,
            "source_truth_classification": source_truth,
        }
        assert requirement_matches(predicate, config, channel, {})


def test_production_footprint_requirement_is_explicitly_opt_in() -> None:
    """Production Footprint는 Project Constraint가 true일 때만 필수다."""
    predicate = {"production_footprint_enforced": True}
    channel: dict[str, object] = {"capabilities": {}}
    config: dict[str, object] = {}
    disabled = {
        "project_constraints": {
            "production_limits": {"enforce_final_footprint": False}
        }
    }
    enabled = {
        "project_constraints": {
            "production_limits": {"enforce_final_footprint": True}
        }
    }

    assert not requirement_matches(predicate, config, channel, disabled)
    assert requirement_matches(predicate, config, channel, enabled)

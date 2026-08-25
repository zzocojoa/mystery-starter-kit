"""Project Gate 상태 머신 검증."""

from pathlib import Path

import pytest

from VALIDATORS.dependency import build_initial_project_state
from VALIDATORS.exceptions import StateTransitionError
from VALIDATORS.io import load_json_object
from VALIDATORS.models import ProjectState
from VALIDATORS.state_machine import GATES, advance_gate

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "STANDARD" / "dependency_graph.json"


def make_clean_state() -> ProjectState:
    """상태 머신 순서 검증용으로 모든 Artifact를 CLEAN 처리한다."""
    graph = load_json_object(GRAPH_PATH)
    state = build_initial_project_state(graph, "PRJ-001", "2026-08-25T00:00:00Z")
    for artifact_state in state["artifacts"].values():
        artifact_state["status"] = "CLEAN"
        artifact_state["content_hash"] = "a" * 64
    return state


def test_all_fourteen_gates_reach_production_ready() -> None:
    """GATE-00부터 GATE-13까지 순서대로 통과하면 Production Ready가 된다."""
    state = make_clean_state()
    for definition in GATES:
        state = advance_gate(
            state,
            definition["gate_id"],
            True,
            "2026-08-25T00:01:00Z",
        )

    assert state["state"] == "PRODUCTION_READY"
    assert state["current_gate"] == "GATE-13"


def test_out_of_order_gate_is_rejected() -> None:
    """앞 Gate를 건너뛴 상태 전이는 명시적으로 실패해야 한다."""
    state = make_clean_state()

    with pytest.raises(StateTransitionError, match="Gate 순서"):
        advance_gate(state, "GATE-01", True, "2026-08-25T00:01:00Z")


def test_dirty_required_artifact_blocks_transition() -> None:
    """필수 Artifact가 DIRTY이면 Gate를 통과할 수 없어야 한다."""
    state = make_clean_state()
    artifacts = state["artifacts"]
    assert isinstance(artifacts, dict)
    compatibility = artifacts["compatibility_report"]
    assert isinstance(compatibility, dict)
    compatibility["status"] = "DIRTY"

    with pytest.raises(StateTransitionError, match="CLEAN"):
        advance_gate(state, "GATE-00", True, "2026-08-25T00:01:00Z")


def test_failed_gate_preserves_last_passed_gate_for_retry() -> None:
    """실패한 Gate는 BLOCKED로 표시하되 같은 Gate를 다시 실행할 수 있어야 한다."""
    state = make_clean_state()

    blocked = advance_gate(state, "GATE-00", False, "2026-08-25T00:01:00Z")
    recovered = advance_gate(blocked, "GATE-00", True, "2026-08-25T00:02:00Z")

    assert blocked["state"] == "BLOCKED"
    assert blocked["current_gate"] == "NONE"
    assert recovered["state"] == "COMPATIBILITY_VALIDATED"
